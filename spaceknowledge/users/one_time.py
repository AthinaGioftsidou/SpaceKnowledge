"""ONE-TIME PASSWORDS for the admin. Requested, short lived, single use, and
delivered to a file that stands in for the mailbox. No real mail is sent."""

import hashlib
import hmac
import logging
import secrets
import threading
import time
from spaceknowledge.common.atomic_json import write_text_atomically
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from spaceknowledge.common.refusal import Refusal
from spaceknowledge.users.credentials import check_username, normalise_username

# Where these lines go is decided once, by the program that opens the log.
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

CODE_DIGITS = 8
MAX_CODE_LENGTH = 64


class Mailbox(ABC):
    """Where a code is delivered. Only this contract is known to the rest."""

    @abstractmethod
    def deliver(self, recipient: str, code: str, lifetime: float) -> None:
        """Make the code available to the recipient."""


class InMemoryMailbox(Mailbox):
    """Keeps the messages in a list. For tests."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def deliver(self, recipient: str, code: str, lifetime: float) -> None:
        self.messages.append((recipient, code))


class FileMailbox(Mailbox):
    """The stand-in mailbox: one text file that only its owner can read. A
    newer message replaces the old one."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError(f"path must be a Path, not {type(path).__name__}")
        self._path = path

    def deliver(self, recipient: str, code: str, lifetime: float) -> None:
        # The folder is private too: a file nobody can open in a folder anyone
        # can list is only half protected. (Both modes apply on POSIX systems.)
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_text_atomically(
            self._path,
            f"To: {recipient}\n"
            "Subject: your one-time admin code\n\n"
            f"Code: {code}\n"
            f"It can be used once, within {int(lifetime)} seconds.\n",
        )

@dataclass
class _Pending:
    digest: str
    expires_at: float
    attempts_left: int


def _digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


class OneTimePasswords:
    """Issues and redeems admin codes.

    A code is single use, expires, and dies after too many wrong guesses. Only
    a hash of it is kept in memory. The clock is a parameter so tests never
    have to sleep. Safe to call from several threads.
    """

    def __init__(
        self,
        admins: Iterable[str],
        mailbox: Mailbox,
        clock: Callable[[], float] = time.monotonic,
        lifetime: float = 300.0,
        max_attempts: int = 3,
    ) -> None:
        if not isinstance(mailbox, Mailbox):
            raise TypeError(f"mailbox must be a Mailbox, not {type(mailbox).__name__}")
        if lifetime <= 0:
            raise ValueError("lifetime must be more than 0 seconds")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._admins: set[str] = set()
        for admin in admins:
            name = normalise_username(admin)
            if check_username(name) is not None:
                raise ValueError(f"{admin!r} is not a valid admin name")
            self._admins.add(name)
        self._mailbox = mailbox
        self._clock = clock
        self._lifetime = lifetime
        self._max_attempts = max_attempts
        self._pending: dict[str, _Pending] = {}
        self._lock = threading.Lock()

    def request(self, admin: str) -> None:
        """Write a new code for a known admin. Says nothing either way, so the
        answer cannot be used to find out who the admins are."""
        name = normalise_username(admin)
        if name not in self._admins:
            log.warning("a code was requested for an unknown admin %r", name[:40])
            return
        code = f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"
        # Delivered first: if this fails, no code exists that nobody could read.
        self._mailbox.deliver(name, code, self._lifetime)
        with self._lock:
            self._pending[name] = _Pending(
                _digest(code), self._clock() + self._lifetime, self._max_attempts
            )
        log.info("a one-time code was written for %s", name)

    def redeem(self, admin: str, code: str) -> Refusal | None:
        """None if the code is right, unused and fresh. It is then used up.
        Every failure gives the same refusal."""
        name = normalise_username(admin)
        if not isinstance(code, str):
            raise TypeError(f"code must be a str, not {type(code).__name__}")
        if len(code) > MAX_CODE_LENGTH:
            return self._refused()
        with self._lock:
            pending = self._pending.get(name)
            if pending is not None and self._clock() >= pending.expires_at:
                del self._pending[name]
                pending = None
            if pending is None:
                return self._refused()
            if hmac.compare_digest(_digest(code), pending.digest):
                del self._pending[name]
                return None
            pending.attempts_left -= 1
            if pending.attempts_left <= 0:
                del self._pending[name]
        return self._refused()

    @staticmethod
    def _refused() -> Refusal:
        return Refusal(
            "admin login",
            "the code is wrong, expired or already used",
            "request a new code, then use it before it expires",
        )