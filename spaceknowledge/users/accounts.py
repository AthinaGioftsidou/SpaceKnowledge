"""AccountRegistry: who may log in."""

import threading

from spaceknowledge.common.refusal import Refusal
from spaceknowledge.users.account_repository import AccountRepository, InMemoryAccountRepository
from spaceknowledge.users.credentials import (
    DEFAULT_ITERATIONS,
    MAX_PASSWORD,
    MAX_USERNAME,
    MIN_PASSWORD,
    MIN_USERNAME,
    PasswordHash,
    check_password,
    check_username,
    make_hash,
    normalise_username,
    verify_password,
)


class AccountRegistry:
    """Registers accounts and checks passwords. Keeps hashes, never passwords.

    Safe to call from several threads: one lock guards the accounts.
    """

    def __init__(
        self, repository: AccountRepository | None = None, iterations: int = DEFAULT_ITERATIONS
    ) -> None:
        if repository is not None and not isinstance(repository, AccountRepository):
            raise TypeError(
                f"repository must be an AccountRepository, not {type(repository).__name__}"
            )
        self._repository = repository if repository is not None else InMemoryAccountRepository()
        self._iterations = iterations
        self._lock = threading.Lock()
        self._accounts: dict[str, PasswordHash] = self._repository.load()
        # Checked against when a name is unknown, so an unknown name takes as
        # long to refuse as a wrong password. Also validates `iterations`.
        self._decoy = make_hash("decoy password", iterations)

    def has_account(self, username: str) -> bool:
        with self._lock:
            return normalise_username(username) in self._accounts

    def names(self) -> list[str]:
        """The registered names, sorted."""
        with self._lock:
            return sorted(self._accounts)

    def register(self, username: str, password: str) -> Refusal | None:
        """None if the account was created, otherwise why not."""
        name = normalise_username(username)
        problem = check_username(name)
        if problem is not None:
            return Refusal(
                f"register {name[:MAX_USERNAME] or 'an empty name'}",
                problem,
                f"use {MIN_USERNAME} to {MAX_USERNAME} letters, digits or underscores",
            )
        problem = check_password(password)
        if problem is not None:
            return Refusal(
                f"register {name}",
                problem,
                f"choose a password of {MIN_PASSWORD} to {MAX_PASSWORD} characters",
            )
        with self._lock:
            if name in self._accounts:
                return Refusal(
                    f"register {name}",
                    "that name is already taken",
                    "choose another name, or log in if it is yours",
                )
            updated = dict(self._accounts)
            updated[name] = make_hash(password, self._iterations)
            # Saved first: if this fails, nothing in memory has changed.
            self._repository.save(updated)
            self._accounts = updated
        return None

    def authenticate(self, username: str, password: str) -> Refusal | None:
        """None if the name and password match, otherwise a refusal. The same
        refusal for an unknown name and a wrong password."""
        name = normalise_username(username)
        if not isinstance(password, str):
            raise TypeError(f"password must be a str, not {type(password).__name__}")
        with self._lock:
            stored = self._accounts.get(name)
        if len(password) > MAX_PASSWORD:
            return self._refused()
        matches = verify_password(password, stored if stored is not None else self._decoy)
        if stored is None or not matches:
            return self._refused()
        return None

    @staticmethod
    def _refused() -> Refusal:
        return Refusal(
            "log in",
            "the name or the password is wrong",
            "check both and try again, or register if you have no account",
        )