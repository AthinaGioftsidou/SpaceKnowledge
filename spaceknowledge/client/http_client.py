"""Shared HTTP plumbing for the clients: one short connection per request, and
every reply checked before it is used. A reply from the network is not trusted."""

import http.client
import json
import string
from typing import Any

from spaceknowledge.common.refusal import Refusal

MAX_REPLY = 64 * 1024   # bytes: a reply larger than this is treated as broken
MAX_TOKEN = 128
_TOKEN_CHARS = frozenset(string.ascii_letters + string.digits + "-_")


class SessionEnded(Exception):
    """The game says this session is not (or no longer) logged in. Carries the
    Refusal, so the user can be told why and what to do next."""

    def __init__(self, refusal: Refusal) -> None:
        super().__init__(refusal.why)
        self.refusal = refusal


def require_text(value: object, what: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{what} must be a str, not {type(value).__name__}")


def check_token(token: object) -> str:
    require_text(token, "token")
    assert isinstance(token, str)
    if not token or len(token) > MAX_TOKEN or not set(token) <= _TOKEN_CHARS:
        raise ValueError("token is not in the form the game hands out")
    return token


class HttpJsonClient:
    """A client of one Broker's DMZ. Failures to reach the game are
    ConnectionErrors, and so is any reply that cannot be used."""

    def __init__(self, host: str, port: int, timeout: float = 10.0) -> None:
        if not isinstance(host, str) or not host:
            raise ValueError("host must be non-empty text")
        if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
            raise ValueError("port must be a whole number from 1 to 65535")
        if timeout <= 0:
            raise ValueError("timeout must be more than 0 seconds")
        self._host = host
        self._port = port
        self._timeout = timeout

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None,
              token: str | None = None) -> tuple[int, dict[str, Any]]:
        headers: dict[str, str] = {}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        connection = http.client.HTTPConnection(self._host, self._port, timeout=self._timeout)
        try:
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            data = response.read(MAX_REPLY + 1)
            status = response.status
        except (OSError, http.client.HTTPException) as problem:
            raise ConnectionError(
                f"cannot reach the game at {self._host}:{self._port} ({type(problem).__name__})"
            ) from None
        finally:
            connection.close()
        if len(data) > MAX_REPLY:
            raise self._bad("the reply is too large")
        try:
            parsed = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise self._bad("the reply is not valid JSON") from None
        if not isinstance(parsed, dict):
            raise self._bad("the reply is not a JSON object")
        return status, parsed

    def _outcome(self, body: dict[str, Any]) -> Refusal | None:
        """None if the game said ok, otherwise its refusal."""
        ok = body.get("ok")
        if not isinstance(ok, bool):
            raise self._bad("the reply has no ok field")
        if ok:
            return None
        raw = body.get("refusal")
        if not isinstance(raw, dict):
            raise self._bad("a refusal came without details")
        parts: list[str] = []
        for key in ("what", "why", "next_step"):
            value = raw.get(key)
            if not isinstance(value, str) or not value:
                raise self._bad(f"a refusal has no {key}")
            parts.append(value)
        return Refusal(*parts)

    def _bad(self, why: str) -> ConnectionError:
        return ConnectionError(
            f"the game at {self._host}:{self._port} sent a reply that cannot be used ({why})")