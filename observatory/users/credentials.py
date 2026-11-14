"""The rules for names and passwords, and the hashing. One home for all of it."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass

MIN_USERNAME = 3
MAX_USERNAME = 20
MIN_PASSWORD = 8
# A maximum is not about usability: it stops one request from forcing
# unbounded work on the server.
MAX_PASSWORD = 128
DEFAULT_ITERATIONS = 200_000

_USERNAME_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_")
_HEX = frozenset("0123456789abcdef")


def normalise_username(username: str) -> str:
    """Trimmed and lower case, so 'Ada' and 'ada' are one player."""
    if not isinstance(username, str):
        raise TypeError(f"username must be a str, not {type(username).__name__}")
    return username.strip().lower()


def check_username(name: str) -> str | None:
    """None if the (already normalised) name is allowed, else the reason."""
    if not isinstance(name, str):
        raise TypeError(f"name must be a str, not {type(name).__name__}")
    if not MIN_USERNAME <= len(name) <= MAX_USERNAME:
        return f"the name must be {MIN_USERNAME} to {MAX_USERNAME} characters long"
    if not set(name) <= _USERNAME_CHARACTERS:
        return "the name may contain only a to z, 0 to 9 and _"
    return None


def check_password(password: str) -> str | None:
    """None if the password is allowed, else the reason. Never trimmed or
    lower-cased: a password is exactly what the player chose."""
    if not isinstance(password, str):
        raise TypeError(f"password must be a str, not {type(password).__name__}")
    if len(password) < MIN_PASSWORD:
        return f"the password must be at least {MIN_PASSWORD} characters long"
    if len(password) > MAX_PASSWORD:
        return f"the password must be at most {MAX_PASSWORD} characters long"
    return None


def _is_hex(text: object, length: int) -> bool:
    return isinstance(text, str) and len(text) == length and set(text) <= _HEX


@dataclass(frozen=True)
class PasswordHash:
    """What is stored instead of a password: the salt, the number of rounds
    and the digest. Read-only."""

    salt: str
    iterations: int
    digest: str

    def __post_init__(self) -> None:
        if not _is_hex(self.salt, 32):
            raise ValueError("salt must be 32 lower-case hex characters")
        if isinstance(self.iterations, bool) or not isinstance(self.iterations, int) \
                or self.iterations < 1:
            raise ValueError("iterations must be a whole number of at least 1")
        if not _is_hex(self.digest, 64):
            raise ValueError("digest must be 64 lower-case hex characters")


def _digest(password: str, salt: str, iterations: int) -> str:
    raw = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return raw.hex()


def make_hash(password: str, iterations: int = DEFAULT_ITERATIONS) -> PasswordHash:
    """Hash a password with a fresh random salt."""
    if not isinstance(password, str):
        raise TypeError(f"password must be a str, not {type(password).__name__}")
    salt = secrets.token_hex(16)
    return PasswordHash(salt, iterations, _digest(password, salt, iterations))


def verify_password(password: str, stored: PasswordHash) -> bool:
    if not isinstance(password, str):
        raise TypeError(f"password must be a str, not {type(password).__name__}")
    if not isinstance(stored, PasswordHash):
        raise TypeError(f"stored must be a PasswordHash, not {type(stored).__name__}")
    attempt = _digest(password, stored.salt, stored.iterations)
    # compare_digest takes the same time wherever the two differ.
    return hmac.compare_digest(attempt, stored.digest)