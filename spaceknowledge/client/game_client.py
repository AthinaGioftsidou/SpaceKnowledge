"""GameClient: a customer's only way into the game.

It speaks HTTP to one Broker's DMZ and knows nothing else about the system: no
other server, no game rules, no storage.
"""

from spaceknowledge.client.http_client import (
    MAX_REPLY,
    HttpJsonClient,
    SessionEnded,
    check_token,
    require_text,
)
from spaceknowledge.common.refusal import Refusal

__all__ = ["GameClient", "MAX_REPLY", "SessionEnded"]


class GameClient(HttpJsonClient):
    """Register, log in, send commands, log out. A refusal by the game is a
    Refusal or reply text, never an exception, except SessionEnded, which means
    the player must log in."""

    def register(self, username: str, password: str) -> Refusal | None:
        """None if the account was created, otherwise why not."""
        require_text(username, "username")
        require_text(password, "password")
        _, body = self._call("POST", "/register", {"username": username, "password": password})
        return self._outcome(body)

    def login(self, username: str, password: str) -> str | Refusal:
        """A session token, or the reason the login was refused."""
        require_text(username, "username")
        require_text(password, "password")
        _, body = self._call("POST", "/login", {"username": username, "password": password})
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

    def command(self, token: str, line: str) -> str:
        """The game's reply text. A refusal by the game is part of that text.
        Raises SessionEnded if the token is no longer valid."""
        require_text(line, "line")
        status, body = self._call("POST", "/command", {"line": line}, check_token(token))
        refusal = self._outcome(body)
        if refusal is not None:
            if status == 401:
                raise SessionEnded(refusal)
            return refusal.describe()
        reply = body.get("reply")
        if not isinstance(reply, str):
            raise self._bad("the reply has no text")
        return reply

    def logout(self, token: str) -> bool:
        """True if there was a live session to end."""
        _, body = self._call("POST", "/logout", {}, check_token(token))
        if self._outcome(body) is not None:
            return False
        was_logged_in = body.get("was_logged_in")
        if not isinstance(was_logged_in, bool):
            raise self._bad("the logout reply is not in the expected form")
        return was_logged_in