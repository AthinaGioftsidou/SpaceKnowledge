"""LOGIN THROTTLE: too many wrong passwords lock a name for a while."""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from spaceknowledge.users.credentials import normalise_username

# Names are cut to this length before they are used as keys, so one request can
# never make the throttle store an enormous string.
MAX_KEY_LENGTH = 64


@dataclass
class _Record:
    failures: int
    forget_at: float


class LoginThrottle:
    """Counts wrong passwords per NAME and locks the name at the limit.

    The count is per name, not per what the client claims, so it cannot be
    dodged by changing anything else in the request. Unknown names are counted
    too, so the lock cannot be used to find out which names exist. The clock is
    a parameter so tests never sleep. Safe to call from several threads.
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        max_failures: int = 5,
        lockout: float = 300.0,
        max_tracked: int = 10_000,
    ) -> None:
        if max_failures < 1:
            raise ValueError("max_failures must be at least 1")
        if lockout <= 0:
            raise ValueError("lockout must be more than 0 seconds")
        if max_tracked < 1:
            raise ValueError("max_tracked must be at least 1")
        self._clock = clock
        self._max_failures = max_failures
        self._lockout = lockout
        self._max_tracked = max_tracked
        self._records: dict[str, _Record] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(name: str) -> str:
        return normalise_username(name)[:MAX_KEY_LENGTH]

    def is_locked(self, name: str) -> bool:
        key, now = self._key(name), self._clock()
        with self._lock:
            record = self._live(key, now)
            return record is not None and record.failures >= self._max_failures

    def record_failure(self, name: str) -> None:
        key, now = self._key(name), self._clock()
        with self._lock:
            record = self._live(key, now)
            if record is None:
                self._make_room(now)
                record = _Record(0, now)
                self._records[key] = record
            if record.failures >= self._max_failures:
                return  # already locked: more failures do not extend the lock
            record.failures += 1
            record.forget_at = now + self._lockout

    def record_success(self, name: str) -> None:
        key = self._key(name)
        with self._lock:
            self._records.pop(key, None)

    def tracked_count(self) -> int:
        with self._lock:
            return len(self._records)

    def _live(self, key: str, now: float) -> _Record | None:
        """The record, unless it has run out, in which case it is forgotten."""
        record = self._records.get(key)
        if record is not None and now >= record.forget_at:
            del self._records[key]
            return None
        return record

    def _make_room(self, now: float) -> None:
        """Forget the expired records, then the oldest, until one more fits."""
        for key in [k for k, r in self._records.items() if now >= r.forget_at]:
            del self._records[key]
        while len(self._records) >= self._max_tracked:
            del self._records[next(iter(self._records))]