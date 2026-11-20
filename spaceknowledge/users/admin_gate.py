"""AdminGate: the admin's door. A valid one-time code gives an admin token."""

import logging

from spaceknowledge.common.refusal import Refusal
from spaceknowledge.users.credentials import normalise_username
from spaceknowledge.users.one_time import OneTimePasswords
from spaceknowledge.users.session_book import SessionBook

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())
# An admin session is much shorter than a customer's: it can do more.
ADMIN_LIFETIME = 3600.0
ADMIN_IDLE_TIMEOUT = 600.0


class AdminGate:
    """Admin tokens live in their OWN SessionBook, so a customer token can
    never be taken for an admin token. Codes are never logged."""

    def __init__(self, codes: OneTimePasswords, sessions: SessionBook | None = None) -> None:
        if not isinstance(codes, OneTimePasswords):
            raise TypeError(f"codes must be OneTimePasswords, not {type(codes).__name__}")
        if sessions is not None and not isinstance(sessions, SessionBook):
            raise TypeError(f"sessions must be a SessionBook, not {type(sessions).__name__}")
        self._codes = codes
        self._sessions = (
            sessions
            if sessions is not None
            else SessionBook(lifetime=ADMIN_LIFETIME, idle_timeout=ADMIN_IDLE_TIMEOUT)
        )

    def request_code(self, admin: str) -> None:
        self._codes.request(admin)

    def login(self, admin: str, code: str) -> str | Refusal:
        """An admin token, or the reason the login was refused."""
        refusal = self._codes.redeem(admin, code)
        name = normalise_username(admin)
        if refusal is not None:
            log.warning("failed admin login for %r", name[:40])
            return refusal
        log.info("%s logged in as admin", name)
        return self._sessions.open(name)

    def admin_for(self, token: str) -> str | None:
        return self._sessions.player_for(token)

    def logout(self, token: str) -> bool:
        return self._sessions.close(token)