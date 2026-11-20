"""The DMZ's boundary: everything a client sends is checked here, and
everything that leaves is cleaned here. Nothing behind the DMZ re-checks sizes,
types or content types, because nothing reaches it that did not pass through."""

import json
import re
from typing import Any

from spaceknowledge.common.refusal import Refusal

MAX_BODY = 4096      # bytes. Refused from the header alone, before reading.
MAX_LINE = 200       # characters in a typed command
MAX_NAME = 64        # characters in a username field (accounts judge the rest)
MAX_PASSWORD_FIELD = 256
MAX_TOKEN = 128

_INTERNAL = re.compile(r"universe", re.IGNORECASE)


class HttpProblem(Exception):
    """A request that must be answered with an error status and a Refusal."""

    def __init__(self, status: int, refusal: Refusal) -> None:
        super().__init__(refusal.why)
        self.status = status
        self.refusal = refusal


def problem(status: int, what: str, why: str, next_step: str) -> HttpProblem:
    return HttpProblem(status, Refusal(what, why, next_step))


def scrub(text: str) -> str:
    """Remove the name of the internal server from anything leaving the DMZ.
    Clients know the Broker side exists; they must not learn about the rest."""
    return _INTERNAL.sub("game world", text)


def refusal_body(refusal: Refusal) -> dict[str, Any]:
    return {
        "ok": False,
        "refusal": {
            "what": scrub(refusal.what),
            "why": scrub(refusal.why),
            "next_step": scrub(refusal.next_step),
        },
    }


def parse_json_body(raw: bytes, content_type: str) -> dict[str, Any]:
    """The body as a JSON object, or an HttpProblem."""
    if not content_type.lower().startswith("application/json"):
        raise problem(415, "read the request", "the body is not declared as JSON",
                      "send the header 'Content-Type: application/json'")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise problem(400, "read the request", "the body is not valid JSON",
                      "send a JSON object such as {\"line\": \"look\"}") from None
    if not isinstance(body, dict):
        raise problem(400, "read the request", "the body must be a JSON object",
                      "send a JSON object such as {\"line\": \"look\"}")
    return body


def only_fields(body: dict[str, Any], allowed: set[str]) -> None:
    """An unknown field is an error, not an ignored extra: a typo gets a
    message, and a hopeful extra field gets no encouragement."""
    unknown = set(body) - allowed
    if unknown:
        raise problem(400, "read the request", f"the field {sorted(unknown)[0]} is not allowed",
                      f"send only: {', '.join(sorted(allowed)) or 'an empty object'}")


def text_field(body: dict[str, Any], key: str, longest: int, allow_control: bool = False) -> str:
    """A required text field of at most `longest` characters. Control characters
    are refused rather than stripped, because silently changing what someone
    sent is worse than telling them."""
    value = body.get(key)
    if not isinstance(value, str):
        raise problem(400, "read the request", f"the field {key} must be text",
                      f"send {key} as a JSON string")
    if len(value) > longest:
        raise problem(400, "read the request", f"the field {key} is longer than {longest} characters",
                      f"send a shorter {key}")
    if not allow_control and any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise problem(400, "read the request", f"the field {key} contains control characters",
                      f"send {key} as plain text")
    return value


def bearer_token(header: str | None) -> str:
    """The token from 'Authorization: Bearer <token>', or a 401."""
    scheme, _, token = (header or "").partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > MAX_TOKEN:
        raise problem(401, "use this request", "no valid session token was sent",
                      "log in, then send 'Authorization: Bearer <token>'")
    return token