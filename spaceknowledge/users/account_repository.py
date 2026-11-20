"""REPOSITORY. Where accounts are kept between runs."""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from spaceknowledge.common.atomic_json import write_json_atomically
from spaceknowledge.users.credentials import PasswordHash, check_username

Accounts = dict[str, PasswordHash]


class CorruptAccountsError(ValueError):
    """Saved accounts that cannot be trusted, so they were not used."""


class AccountRepository(ABC):
    """Save everything, load everything."""

    @abstractmethod
    def load(self) -> Accounts:
        """The saved accounts, or an empty dict if there are none."""

    @abstractmethod
    def save(self, accounts: Accounts) -> None:
        """Replace what is stored with `accounts`."""


class InMemoryAccountRepository(AccountRepository):
    def __init__(self) -> None:
        self._accounts: Accounts = {}

    def load(self) -> Accounts:
        return dict(self._accounts)  # PasswordHash is read-only, so sharing is safe

    def save(self, accounts: Accounts) -> None:
        self._accounts = dict(accounts)


class JsonAccountRepository(AccountRepository):
    """One JSON file, written atomically. Holds salts and digests only."""

    VERSION = 1

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError(f"path must be a Path, not {type(path).__name__}")
        self._path = path

    def save(self, accounts: Accounts) -> None:
        body = {
            name: {"salt": h.salt, "iterations": h.iterations, "hash": h.digest}
            for name, h in accounts.items()
        }
        write_json_atomically(self._path, {"version": self.VERSION, "accounts": body})

    def load(self) -> Accounts:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as problem:
            raise self._corrupt(f"is not valid JSON ({problem})") from None
        return self._check(raw)

    def _corrupt(self, why: str) -> CorruptAccountsError:
        return CorruptAccountsError(f"{self._path.name} {why}")

    def _check(self, raw: Any) -> Accounts:
        """Data read back from disk is checked before anything uses it."""
        version = raw.get("version") if isinstance(raw, dict) else None
        if isinstance(version, bool) or version != self.VERSION:
            raise self._corrupt(f"is not a version {self.VERSION} accounts file")
        body = raw.get("accounts")
        if not isinstance(body, dict):
            raise self._corrupt("has no accounts object")
        accounts: Accounts = {}
        for name, record in body.items():
            if check_username(name) is not None:
                raise self._corrupt(f"has an invalid account name {name!r}")
            if not isinstance(record, dict):
                raise self._corrupt(f"has a bad record for {name}")
            try:
                accounts[name] = PasswordHash(
                    record.get("salt"), record.get("iterations"), record.get("hash")
                )
            except ValueError as problem:
                raise self._corrupt(f"has a bad password hash for {name} ({problem})") from None
        return accounts