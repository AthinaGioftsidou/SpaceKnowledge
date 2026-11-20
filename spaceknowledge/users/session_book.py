"""SessionBook: login tokens, the players they stand for, and when they expire."""

import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_LIFETIME = 8 * 3600.0      # a token never works longer than this
DEFAULT_IDLE_TIMEOUT = 30 * 60.0   # ...or after this long without being used


@dataclass
class _Session:
    player_id: str
    expires_at: float
    idle_until: float


class SessionBook:
    """A token is random and unguessable, and means one player.

    A token ends in three ways: it is closed, it reaches its maximum lifetime,
    or it sits unused for the idle time (every use restarts the idle time but
    never the lifetime). Kept in memory only, so a restart logs everybody out.
    The clock is a parameter so tests never sleep. Safe to call from several
    threads.
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        lifetime: float = DEFAULT_LIFETIME,
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
    ) -> None:
        if lifetime <= 0:
            raise ValueError("lifetime must be more than 0 seconds")
        if idle_timeout <= 0:
            raise ValueError("idle_timeout must be more than 0 seconds")
        self._clock = clock
        self._lifetime = lifetime
        self._idle_timeout = idle_timeout
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()

    def open(self, player_id: str) -> str:
        if not player_id:
            raise ValueError("player_id must not be empty")
        token = secrets.token_urlsafe(32)
        now = self._clock()
        with self._lock:
            self._forget_expired(now)
            self._sessions[token] = _Session(
                player_id, now + self._lifetime, now + self._idle_timeout
            )
        return token

    def player_for(self, token: str) -> str | None:
        if not isinstance(token, str):
            raise TypeError(f"token must be a str, not {type(token).__name__}")
        now = self._clock()
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if self._is_expired(session, now):
                del self._sessions[token]
                return None
            session.idle_until = now + self._idle_timeout
            return session.player_id

    def close(self, token: str) -> bool:
        """True if there was a live session. An expired one counts as none."""
        now = self._clock()
        with self._lock:
            session = self._sessions.pop(token, None)
        return session is not None and not self._is_expired(session, now)

    def count(self) -> int:
        """How many sessions are stored, for tests and later the admin view."""
        with self._lock:
            return len(self._sessions)

    @staticmethod
    def _is_expired(session: _Session, now: float) -> bool:
        return now >= session.expires_at or now >= session.idle_until

    def _forget_expired(self, now: float) -> None:
        for token in [t for t, s in self._sessions.items() if self._is_expired(s, now)]:
            del self._sessions[token]