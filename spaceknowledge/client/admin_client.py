"""AdminClient: an administrator's only way into the game. It calls the same
DMZ as the players, on the /admin routes, with a token of its own."""

from typing import Any

from spaceknowledge.client.http_client import (
    HttpJsonClient,
    SessionEnded,
    check_token,
    require_text,
)
from spaceknowledge.common.refusal import Refusal

__all__ = ["AdminClient", "SessionEnded"]


def _plain(value: Any, depth: int = 0) -> bool:
    """Only numbers, text and booleans, in objects nested at most three deep."""
    if isinstance(value, dict):
        return (depth <= 2 and all(isinstance(key, str) for key in value)
                and all(_plain(item, depth + 1) for item in value.values()))
    return isinstance(value, (str, int, float, bool))


class AdminClient(HttpJsonClient):
    """Ask for a code, log in with it, then read the players and the numbers.
    Nothing here can change the game."""

    def request_code(self, admin: str) -> Refusal | None:
        """Ask for a one-time code to be written to the administrator's mailbox.
        The answer is the same for every name, so it reveals nothing."""
        require_text(admin, "admin")
        _, body = self._call("POST", "/admin/code", {"admin": admin})
        return self._outcome(body)

    def login(self, admin: str, code: str) -> str | Refusal:
        """An admin token, or the reason the login was refused."""
        require_text(admin, "admin")
        require_text(code, "code")
        _, body = self._call("POST", "/admin/login", {"admin": admin, "code": code})
        refusal = self._outcome(body)
        if refusal is not None:
            return refusal
        token = body.get("token")
        if not isinstance(token, str):
            raise self._bad("the login reply has no token")
        try:
            return check_token(token)
        except ValueError:
            raise self._bad("the login reply has a token in a form the game never hands out") from None

    def logout(self, token: str) -> bool:
        """True if there was a live admin session to end."""
        body = self._signed("/admin/logout", token)
        was_logged_in = body.get("was_logged_in")
        if not isinstance(was_logged_in, bool):
            raise self._bad("the logout reply is not in the expected form")
        return was_logged_in

    def players(self, token: str) -> list[str]:
        """The registered player names. Raises SessionEnded if the token is dead."""
        players = self._signed("/admin/players", token).get("players")
        if not isinstance(players, list) or not all(
                isinstance(name, str) and name for name in players):
            raise self._bad("the players reply is not a list of names")
        return players

    def stats(self, token: str) -> dict[str, Any]:
        """How the Broker is doing. Raises SessionEnded if the token is dead."""
        stats = self._signed("/admin/stats", token).get("stats")
        if not isinstance(stats, dict) or not _plain(stats):
            raise self._bad("the statistics reply is not in the expected form")
        return stats

    def _signed(self, path: str, token: str) -> dict[str, Any]:
        status, body = self._call("POST", path, {}, check_token(token))
        refusal = self._outcome(body)
        if refusal is not None:
            if status == 401:
                raise SessionEnded(refusal)
            raise self._bad("the game refused a request it should accept")
        return body