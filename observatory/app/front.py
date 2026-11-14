"""Front: the only door clients use. A login gives a token, and every line
must carry one."""

import logging

from observatory.broker.broker_server import BrokerServer
from observatory.common.refusal import Refusal
from observatory.users.accounts import AccountRegistry
from observatory.users.credentials import normalise_username
from observatory.users.session_book import SessionBook

# Where these lines go is decided once, by the program that opens the log.
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class Front:
    """Checks who is asking, then hands the line to the Broker thread.

    The player's name comes from the token, never from the text, so nobody can
    act as another player. Passwords are never logged. If `start` is given, a
    login also places the player in the world before a token is handed out.
    """

    def __init__(
        self,
        accounts: AccountRegistry,
        sessions: SessionBook,
        server: BrokerServer,
        start: str | None = None,
    ) -> None:
        if not isinstance(accounts, AccountRegistry):
            raise TypeError(f"accounts must be an AccountRegistry, not {type(accounts).__name__}")
        if not isinstance(sessions, SessionBook):
            raise TypeError(f"sessions must be a SessionBook, not {type(sessions).__name__}")
        if not isinstance(server, BrokerServer):
            raise TypeError(f"server must be a BrokerServer, not {type(server).__name__}")
        if start is not None and not start:
            raise ValueError("start must not be empty")
        self._accounts = accounts
        self._sessions = sessions
        self._server = server
        self._start = start

    def register(self, username: str, password: str) -> Refusal | None:
        """None if the account was created, otherwise why not."""
        refusal = self._accounts.register(username, password)
        if refusal is None:
            log.info("%s registered", normalise_username(username)[:40])
        return refusal

    def login(self, username: str, password: str) -> str | Refusal:
        """A session token, or the reason the login was refused."""
        refusal = self._accounts.authenticate(username, password)
        name = normalise_username(username)
        if refusal is not None:
            log.warning("failed login for %r", name[:40])
            return refusal
        if self._start is not None:
            problem = self._server.join(name, self._start)
            if problem:
                log.warning("%s could not be placed in the world", name)
                return Refusal(
                    "log in",
                    "the game could not place you in the world",
                    "try again in a moment, or ask the administrator",
                )
        log.info("%s logged in", name)
        return self._sessions.open(name)

    def logout(self, token: str) -> bool:
        return self._sessions.close(token)

    def submit(self, token: str, line: str, timeout: float = 5.0) -> str:
        player = self._sessions.player_for(token)
        if player is None:
            return Refusal(
                "send a command",
                "you are not logged in",
                "log in first, then send your command with the token you were given",
            ).describe()
        return self._server.submit(player, line, timeout)