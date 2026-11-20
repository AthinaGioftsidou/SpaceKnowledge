"""The wire format between the Broker and the Universe: one JSON object per line.

JSON escapes newlines inside strings, so one line is always one message. Every
message that arrives is checked here, field by field, before anything else sees
it: a wire is not type-checked by the language, so this is the boundary.
"""

import json
from collections.abc import Callable
from typing import Any, BinaryIO

from spaceknowledge.common.messages import ItemInfo, Request, Response
from spaceknowledge.common.refusal import Refusal

# The longest line accepted. Reading is capped so one client cannot make the
# server buffer an unbounded amount of memory.
MAX_LINE = 64 * 1024


class WireError(ValueError):
    """A message that does not follow the wire format."""


def write_message(send: Callable[[bytes], object], message: dict[str, Any]) -> None:
    """Send one message as one line."""
    send((json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8"))


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    """The next message, or None at the end of the stream."""
    line = stream.readline(MAX_LINE + 1)
    if not line:
        return None
    if len(line) > MAX_LINE or not line.endswith(b"\n"):
        raise WireError("a line was too long or was cut off")
    try:
        message = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise WireError("a line was not valid JSON") from None
    if not isinstance(message, dict):
        raise WireError("a message must be a JSON object")
    return message


def text_field(body: dict[str, Any], key: str, what: str) -> str:
    """A required field that must be non-empty text."""
    value = body.get(key)
    if not isinstance(value, str) or not value:
        raise WireError(f"{what} needs {key} as non-empty text")
    return value


def _object(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WireError(f"{what} must be an object")
    return value


def _check_fields(body: dict[str, Any], what: str, required: set[str], optional: set[str]) -> None:
    """Unknown fields are an error, not ignored extras, so a typo or a hopeful
    extra field is never silently accepted."""
    unknown = set(body) - required - optional
    if unknown:
        raise WireError(f"{what} has an unexpected field {sorted(unknown)[0]}")
    missing = required - set(body)
    if missing:
        raise WireError(f"{what} is missing the field {sorted(missing)[0]}")


def request_to_wire(request: Request) -> dict[str, Any]:
    body: dict[str, Any] = {
        "op_id": request.op_id,
        "action": request.action,
        "player_id": request.player_id,
        "item_id": request.item_id,
        "amount": request.amount,
    }
    if request.name is not None:
        body["name"] = request.name
    return body


def request_from_wire(body: Any) -> Request:
    body = _object(body, "a request")
    _check_fields(body, "a request", {"op_id", "action", "player_id", "item_id"},
                  {"amount", "name"})
    amount = body.get("amount", 1)
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
        raise WireError("a request needs amount as a whole number of at least 1")
    name = text_field(body, "name", "a request") if "name" in body else None
    return Request(
        text_field(body, "op_id", "a request"),
        text_field(body, "action", "a request"),
        text_field(body, "player_id", "a request"),
        text_field(body, "item_id", "a request"),
        amount,
        name,
    )


def response_to_wire(response: Response) -> dict[str, Any]:
    body: dict[str, Any] = {"op_id": response.op_id, "ok": response.ok}
    refusal = response.refusal
    if refusal is not None:
        body["refusal"] = {
            "what": refusal.what, "why": refusal.why, "next_step": refusal.next_step,
        }
    if response.items:
        body["items"] = [
            {"id": i.item_id, "name": i.name, "description": i.description}
            for i in response.items
        ]
    return body


def _item_from_wire(raw: Any) -> ItemInfo:
    raw = _object(raw, "an item")
    _check_fields(raw, "an item", {"id", "name", "description"}, set())
    return ItemInfo(
        text_field(raw, "id", "an item"),
        text_field(raw, "name", "an item"),
        text_field(raw, "description", "an item"),
    )


def response_from_wire(body: Any) -> Response:
    body = _object(body, "a response")
    _check_fields(body, "a response", {"op_id", "ok"}, {"refusal", "items"})
    op_id = text_field(body, "op_id", "a response")
    ok = body["ok"]
    if not isinstance(ok, bool):
        raise WireError("a response needs ok as true or false")
    refusal = None
    if "refusal" in body:
        raw = _object(body["refusal"], "a refusal")
        _check_fields(raw, "a refusal", {"what", "why", "next_step"}, set())
        refusal = Refusal(*(text_field(raw, key, "a refusal")
                            for key in ("what", "why", "next_step")))
    if ok == (refusal is not None):
        raise WireError("ok and refusal disagree")
    raw_items = body.get("items", [])
    if not isinstance(raw_items, list):
        raise WireError("items must be a list")
    try:
        return Response(op_id, refusal, tuple(_item_from_wire(i) for i in raw_items))
    except ValueError as problem:
        raise WireError(str(problem)) from None