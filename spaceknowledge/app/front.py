"""Front: the only door clients use. A login gives a token, and every line
must carry one."""

import logging

from spaceknowledge.broker.broker_server import BrokerServer
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.users.accounts import AccountRegistry
from spaceknowledge.users.credentials import normalise_username
from spaceknowledge.users.login_throttle import LoginThrottle
from spaceknowledge.users.session_book import SessionBook

# Where these lines go is decided once, by the program that opens the log.
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class Front:
    """Checks who is asking, then hands the line to the Broker thread.

    The player's name comes from the token, never from the text, so nobody can
    act as another player. Passwords are never logged. Too many wrong passwords
    for a name pause logins for that name. If `start` is given, a login also
    places the player in the world before a token is handed out.
    """

    def __init__(
        self,
        accounts: AccountRegistry,
        sessions: SessionBook,
        server: BrokerServer,
        start: str | None = None,
        throttle: LoginThrottle | None = None,
    ) -> None:
        if not isinstance(accounts, AccountRegistry):
            raise TypeError(f"accounts must be an AccountRegistry, not {type(accounts).__name__}")
        if not isinstance(sessions, SessionBook):
            raise TypeError(f"sessions must be a SessionBook, not {type(sessions).__name__}")
        if not isinstance(server, BrokerServer):
            raise TypeError(f"server must be a BrokerServer, not {type(server).__name__}")
        if start is not None and not start:
            raise ValueError("start must not be empty")
        if throttle is not None and not isinstance(throttle, LoginThrottle):
            raise TypeError(f"throttle must be a LoginThrottle, not {type(throttle).__name__}")
        self._accounts = accounts
        self._sessions = sessions
        self._server = server
        self._start = start
        self._throttle = throttle if throttle is not None else LoginThrottle()

    def register(self, username: str, password: str) -> Refusal | None:
        """None if the account was created, otherwise why not."""
        refusal = self._accounts.register(username, password)
        if refusal is None:
            log.info("%s registered", normalise_username(username)[:40])
        return refusal

    def login(self, username: str, password: str) -> str | Refusal:
        """A session token, or the reason the login was refused."""
        name = normalise_username(username)
        if self._throttle.is_locked(name):
            # Not even checked: a locked name gets no chance to guess more.
            log.warning("login for %r refused: locked", name[:40])
            return self._paused()
        refusal = self._accounts.authenticate(username, password)
        if refusal is not None:
            self._throttle.record_failure(name)
            log.warning("failed login for %r", name[:40])
            return refusal
        self._throttle.record_success(name)
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

    def command(self, token: str, line: str, timeout: float = 5.0) -> str | Refusal:
        """The reply text, or a Refusal if the token is not (or no longer) valid."""
        player = self._sessions.player_for(token)
        if player is None:
            return Refusal(
                "send a command",
                "you are not logged in",
                "log in first, then send your command with the token you were given",
            )
        return self._server.submit(player, line, timeout)

    def submit(self, token: str, line: str, timeout: float = 5.0) -> str:
        """Like `command`, but always text: a refusal is described."""
        result = self.command(token, line, timeout)
        return result.describe() if isinstance(result, Refusal) else result

    @staticmethod
    def _paused() -> Refusal:
        """The same wording for every locked name, known or not."""
        return Refusal(
            "log in",
            "too many failed attempts, so logging in is paused for a while",
            "wait a few minutes, then try again",
        )