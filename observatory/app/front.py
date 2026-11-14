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
    act as another player. Passwords are never logged.
    """

    def __init__(self, accounts: AccountRegistry, sessions: SessionBook, server: BrokerServer) -> None:
        if not isinstance(accounts, AccountRegistry):
            raise TypeError(f"accounts must be an AccountRegistry, not {type(accounts).__name__}")
        if not isinstance(sessions, SessionBook):
            raise TypeError(f"sessions must be a SessionBook, not {type(sessions).__name__}")
        if not isinstance(server, BrokerServer):
            raise TypeError(f"server must be a BrokerServer, not {type(server).__name__}")
        self._accounts = accounts
        self._sessions = sessions
        self._server = server

    def login(self, username: str, password: str) -> str | Refusal:
        """A session token, or the reason the login was refused."""
        refusal = self._accounts.authenticate(username, password)
        name = normalise_username(username)
        if refusal is not None:
            log.warning("failed login for %r", name[:40])
            return refusal
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