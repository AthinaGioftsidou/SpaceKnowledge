"""REPOSITORY. Where the Broker keeps what players carry between runs."""

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

# player id -> [(item id, item name), ...]
Records = dict[str, list[tuple[str, str]]]
# player id -> {resource name: quantity}
Resources = dict[str, dict[str, int]]


class CorruptStoreError(ValueError):
    """Stored data that cannot be trusted, so it was not used."""


class InventoryRepository(ABC):
    """What the Broker needs from storage: save everything, load everything.

    Items and resources are saved in one call, so one is never stored
    without the other. The Broker knows only this contract, so a different
    store can replace the JSON file without changing the Broker's rules.
    """

    @abstractmethod
    def load(self) -> Records:
        """Return the saved items, or an empty dict if nothing was saved."""

    @abstractmethod
    def load_resources(self) -> Resources:
        """Return the saved resources, or an empty dict if nothing was saved."""

    @abstractmethod
    def save(self, records: Records, resources: Resources | None = None) -> None:
        """Replace everything stored with `records` and `resources`."""


def _copy(records: Records) -> Records:
    copy: Records = {}
    for player_id, items in records.items():
        copy[player_id] = list(items)
    return copy


def _resources_by_player(records: Records, resources: Resources | None) -> Resources:
    """One bag for every player in `records`. Raises ValueError if `resources`
    names a player who has no record, so nothing is saved for a stranger."""
    given = resources if resources is not None else {}
    for player_id in given:
        if player_id not in records:
            raise ValueError(f"resources given for unknown player {player_id}")
    return {player_id: dict(given.get(player_id, {})) for player_id in records}


class InMemoryInventoryRepository(InventoryRepository):
    """Keeps the data in memory. For tests, and for a Broker with no file."""

    def __init__(self) -> None:
        self._records: Records = {}
        self._resources: Resources = {}

    def load(self) -> Records:
        return _copy(self._records)

    def load_resources(self) -> Resources:
        return {player_id: dict(bag) for player_id, bag in self._resources.items()}

    def save(self, records: Records, resources: Resources | None = None) -> None:
        # Worked out first, so a refusal leaves the old data untouched.
        checked = _resources_by_player(records, resources)
        self._records = _copy(records)
        self._resources = checked


class JsonInventoryRepository(InventoryRepository):
    """Stores the data in one JSON file, written so it is never half written.

    Writes version 2. Reads versions 1 (items only) and 2.
    """

    VERSION = 2
    READABLE_VERSIONS = (1, 2)

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError(f"path must be a Path, not {type(path).__name__}")
        self._path = path

    def load(self) -> Records:
        return self._read()[0]

    def load_resources(self) -> Resources:
        return self._read()[1]

    def save(self, records: Records, resources: Resources | None = None) -> None:
        bags = _resources_by_player(records, resources)
        players: dict[str, Any] = {}
        for player_id, items in records.items():
            players[player_id] = {
                "items": [{"id": item_id, "name": name} for item_id, name in items],
                "resources": bags[player_id],
            }
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

    def _read(self) -> tuple[Records, Resources]:
        if not self._path.exists():
            return {}, {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as problem:
            raise self._corrupt(f"is not valid JSON ({problem})") from None
        return self._check(raw)

    def _corrupt(self, why: str) -> CorruptStoreError:
        return CorruptStoreError(f"{self._path.name} {why}")

    def _check(self, raw: Any) -> tuple[Records, Resources]:
        """Data read back from disk is checked before anything uses it."""
        version = raw.get("version") if isinstance(raw, dict) else None
        if isinstance(version, bool) or version not in self.READABLE_VERSIONS:
            raise self._corrupt("is not a version 1 or 2 inventory file")
        players = raw.get("players")
        if not isinstance(players, dict):
            raise self._corrupt("has no players object")
        records: Records = {}
        bags: Resources = {}
        for player_id, body in players.items():
            if not player_id:
                raise self._corrupt("has a player with an empty name")
            items, resources = self._split(player_id, body, version)
            records[player_id] = self._check_items(player_id, items)
            bags[player_id] = self._check_resources(player_id, resources)
        return records, bags

    def _split(self, player_id: str, body: Any, version: int) -> tuple[Any, Any]:
        """Version 1 stored a bare item list. Version 2 stores an object."""
        if version == 1:
            return body, {}
        if not isinstance(body, dict):
            raise self._corrupt(f"has a bad record for {player_id}")
        return body.get("items"), body.get("resources")

    def _check_items(self, player_id: str, items: Any) -> list[tuple[str, str]]:
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

    def _check_resources(self, player_id: str, resources: Any) -> dict[str, int]:
        if not isinstance(resources, dict):
            raise self._corrupt(f"has a bad resource list for {player_id}")
        checked: dict[str, int] = {}
        for name, quantity in resources.items():
            if not name:
                raise self._corrupt(f"has a resource without a name for {player_id}")
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
                raise self._corrupt(f"has a bad quantity of {name} for {player_id}")
            checked[name] = quantity
        return checked