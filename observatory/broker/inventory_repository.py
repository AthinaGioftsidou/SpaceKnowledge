"""REPOSITORY. Where the Broker keeps what players carry between runs."""

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

# player id -> [(item id, item name), ...]
Records = dict[str, list[tuple[str, str]]]


class CorruptStoreError(ValueError):
    """Stored data that cannot be trusted, so it was not used."""


class InventoryRepository(ABC):
    """What the Broker needs from storage: save everything, load everything.

    The Broker knows only this contract, so a different store can replace the
    JSON file without changing the Broker's rules.
    """

    @abstractmethod
    def load(self) -> Records:
        """Return what was saved, or an empty dict if nothing was."""

    @abstractmethod
    def save(self, records: Records) -> None:
        """Replace what is stored with `records`."""


def _copy(records: Records) -> Records:
    copy: Records = {}
    for player_id, items in records.items():
        copy[player_id] = list(items)
    return copy


class InMemoryInventoryRepository(InventoryRepository):
    """Keeps the data in memory. For tests, and for a Broker with no file."""

    def __init__(self) -> None:
        self._records: Records = {}

    def load(self) -> Records:
        return _copy(self._records)

    def save(self, records: Records) -> None:
        self._records = _copy(records)


class JsonInventoryRepository(InventoryRepository):
    """Stores the data in one JSON file, written so it is never half written."""

    VERSION = 1

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError(f"path must be a Path, not {type(path).__name__}")
        self._path = path

    def load(self) -> Records:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as problem:
            raise self._corrupt(f"is not valid JSON ({problem})") from None
        return self._check(raw)

    def save(self, records: Records) -> None:
        players: dict[str, list[dict[str, str]]] = {}
        for player_id, items in records.items():
            players[player_id] = [{"id": item_id, "name": name} for item_id, name in items]
        document = {"version": self.VERSION, "players": players}

        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_name(self._path.name + ".tmp")
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(document, indent=2))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise

    def _corrupt(self, why: str) -> CorruptStoreError:
        return CorruptStoreError(f"{self._path.name} {why}")

    def _check(self, raw: Any) -> Records:
        """Data read back from disk is checked before anything uses it."""
        if not isinstance(raw, dict) or raw.get("version") != self.VERSION:
            raise self._corrupt(f"is not a version {self.VERSION} inventory file")
        players = raw.get("players")
        if not isinstance(players, dict):
            raise self._corrupt("has no players object")
        records: Records = {}
        for player_id, items in players.items():
            records[player_id] = self._check_player(player_id, items)
        return records

    def _check_player(self, player_id: str, items: Any) -> list[tuple[str, str]]:
        if not player_id:
            raise self._corrupt("has a player with an empty name")
        if not isinstance(items, list):
            raise self._corrupt(f"has a bad item list for {player_id}")
        seen: set[str] = set()
        entries: list[tuple[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                raise self._corrupt(f"has a bad item for {player_id}")
            item_id, name = item.get("id"), item.get("name")
            if not isinstance(item_id, str) or not item_id:
                raise self._corrupt(f"has an item without an id for {player_id}")
            if not isinstance(name, str) or not name:
                raise self._corrupt(f"has an item without a name for {player_id}")
            if item_id in seen:
                raise self._corrupt(f"holds {item_id} twice for {player_id}")
            seen.add(item_id)
            entries.append((item_id, name))
        return entries