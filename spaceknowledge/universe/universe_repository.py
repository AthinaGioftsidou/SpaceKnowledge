"""REPOSITORY. Where the Universe keeps its state between runs."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from spaceknowledge.common.atomic_json import write_json_atomically
from spaceknowledge.common.messages import ItemInfo, Response
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.universe.deposits import Stock


class CorruptStateError(ValueError):
    """Saved state that cannot be trusted, so it was not used."""


@dataclass
class UniverseState:
    """Everything the Universe must remember, saved together in one file."""

    locations: dict[str, str]        # player id -> destination id
    stock: Stock                     # destination id -> resource -> quantity left
    dropped: dict[str, list[str]]    # destination id -> ids of items dropped there
    answers: dict[str, Response]     # op_id -> the answer already given
    # item id -> display name, for the items in `dropped`. Older files have none.
    names: dict[str, str] = field(default_factory=dict)
    # mission id -> {"collected": int, "complete": bool}. Older files have none.
    missions: dict[str, dict[str, Any]] = field(default_factory=dict)


class UniverseRepository(ABC):
    """What the Universe needs from storage: save everything, load everything."""

    @abstractmethod
    def load(self) -> UniverseState | None:
        """The saved state, or None if nothing was ever saved."""

    @abstractmethod
    def save(self, state: UniverseState) -> None:
        """Replace what is stored with `state`."""


def _copy_state(state: UniverseState) -> UniverseState:
    return UniverseState(
        dict(state.locations),
        {destination_id: dict(resources) for destination_id, resources in state.stock.items()},
        {destination_id: list(item_ids) for destination_id, item_ids in state.dropped.items()},
        dict(state.answers),  # Responses are read-only, so sharing them is safe
        dict(state.names),
        {mission_id: dict(record) for mission_id, record in state.missions.items()},
    )


def _require_state(state: object) -> None:
    if not isinstance(state, UniverseState):
        raise TypeError(f"state must be a UniverseState, not {type(state).__name__}")


class InMemoryUniverseRepository(UniverseRepository):
    """Keeps the state in memory. For tests, and for a Universe with no file."""

    def __init__(self) -> None:
        self._state: UniverseState | None = None

    def load(self) -> UniverseState | None:
        return None if self._state is None else _copy_state(self._state)

    def save(self, state: UniverseState) -> None:
        _require_state(state)
        self._state = _copy_state(state)


class JsonUniverseRepository(UniverseRepository):
    """Stores the state in one JSON file, written so it is never half written."""

    VERSION = 1

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError(f"path must be a Path, not {type(path).__name__}")
        self._path = path

    def save(self, state: UniverseState) -> None:
        _require_state(state)
        document = {
            "version": self.VERSION,
            "locations": state.locations,
            "stock": state.stock,
            "dropped": state.dropped,
            "answers": {op_id: self._encode(r) for op_id, r in state.answers.items()},
            "names": state.names,
            "missions": state.missions,
        }
        write_json_atomically(self._path, document)

    @staticmethod
    def _encode(response: Response) -> dict[str, Any]:
        if response.ok:
            body: dict[str, Any] = {"ok": True}
            if response.items:
                body["items"] = [
                    {"id": i.item_id, "name": i.name, "description": i.description}
                    for i in response.items
                ]
            return body
        refusal = response.refusal
        return {
            "ok": False,
            "refusal": {"what": refusal.what, "why": refusal.why, "next_step": refusal.next_step},
        }

    def load(self) -> UniverseState | None:
        if not self._path.exists():
            return None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as problem:
            raise self._corrupt(f"is not valid JSON ({problem})") from None
        return self._check(raw)

    def _corrupt(self, why: str) -> CorruptStateError:
        return CorruptStateError(f"{self._path.name} {why}")

    def _check(self, raw: Any) -> UniverseState:
        """Data read back from disk is checked before anything uses it."""
        version = raw.get("version") if isinstance(raw, dict) else None
        if isinstance(version, bool) or version != self.VERSION:
            raise self._corrupt(f"is not a version {self.VERSION} universe file")
        return UniverseState(
            self._check_locations(raw.get("locations")),
            self._check_stock(raw.get("stock")),
            self._check_dropped(raw.get("dropped")),
            self._check_answers(raw.get("answers")),
            self._check_names(raw.get("names", {})),
            self._check_missions(raw.get("missions", {})),
        )

    def _check_missions(self, raw: Any) -> dict[str, dict[str, Any]]:
        missions: dict[str, dict[str, Any]] = {}
        for mission_id, record in self._object(raw, "missions").items():
            key = self._text(mission_id, "a mission id")
            if not isinstance(record, dict) or set(record) != {"collected", "complete"}:
                raise self._corrupt(f"has a bad record for the mission {key}")
            collected, complete = record["collected"], record["complete"]
            if isinstance(collected, bool) or not isinstance(collected, int) or collected < 0:
                raise self._corrupt(f"has a bad collected amount for the mission {key}")
            if not isinstance(complete, bool):
                raise self._corrupt(f"has a bad complete flag for the mission {key}")
            missions[key] = {"collected": collected, "complete": complete}
        return missions

    def _check_names(self, raw: Any) -> dict[str, str]:
        names: dict[str, str] = {}
        for item_id, name in self._object(raw, "names").items():
            key = self._text(item_id, "an item id in names")
            names[key] = self._text(name, f"a display name for {key}")
        return names

    def _object(self, value: Any, section: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise self._corrupt(f"has no {section} object")
        return value

    def _text(self, value: Any, what: str) -> str:
        if not isinstance(value, str) or not value:
            raise self._corrupt(f"has {what} that is not text")
        return value

    def _check_locations(self, raw: Any) -> dict[str, str]:
        locations: dict[str, str] = {}
        for player_id, destination_id in self._object(raw, "locations").items():
            name = self._text(player_id, "a player name")
            locations[name] = self._text(destination_id, f"a location for {player_id}")
        return locations

    def _check_stock(self, raw: Any) -> Stock:
        stock: Stock = {}
        for destination_id, resources in self._object(raw, "stock").items():
            self._text(destination_id, "a destination name")
            if not isinstance(resources, dict):
                raise self._corrupt(f"has bad stock for {destination_id}")
            stock[destination_id] = {}
            for resource, quantity in resources.items():
                self._text(resource, f"a resource name in {destination_id}")
                if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
                    raise self._corrupt(f"has a bad quantity of {resource} in {destination_id}")
                stock[destination_id][resource] = quantity
        return stock

    def _check_dropped(self, raw: Any) -> dict[str, list[str]]:
        dropped: dict[str, list[str]] = {}
        for destination_id, item_ids in self._object(raw, "dropped").items():
            self._text(destination_id, "a destination name")
            if not isinstance(item_ids, list):
                raise self._corrupt(f"has a bad item list for {destination_id}")
            seen: set[str] = set()
            for item_id in item_ids:
                self._text(item_id, f"an item id in {destination_id}")
                if item_id in seen:
                    raise self._corrupt(f"drops {item_id} twice in {destination_id}")
                seen.add(item_id)
            dropped[destination_id] = list(item_ids)
        return dropped

    def _check_answers(self, raw: Any) -> dict[str, Response]:
        answers: dict[str, Response] = {}
        for op_id, body in self._object(raw, "answers").items():
            name = self._text(op_id, "an operation id")
            answers[name] = self._decode(name, body)
        return answers

    def _decode(self, op_id: str, body: Any) -> Response:
        if not isinstance(body, dict) or not isinstance(body.get("ok"), bool):
            raise self._corrupt(f"has a bad answer for {op_id}")
        if body["ok"]:
            return Response(op_id, items=self._decode_items(op_id, body.get("items", [])))
        refusal = body.get("refusal")
        if not isinstance(refusal, dict):
            raise self._corrupt(f"has a refusal without details for {op_id}")
        parts = [
            self._text(refusal.get(key), f"a refusal {key} for {op_id}")
            for key in ("what", "why", "next_step")
        ]
        return Response(op_id, Refusal(*parts))

    def _decode_items(self, op_id: str, raw: Any) -> tuple[ItemInfo, ...]:
        if not isinstance(raw, list):
            raise self._corrupt(f"has a bad item list in the answer {op_id}")
        items: list[ItemInfo] = []
        for entry in raw:
            if not isinstance(entry, dict):
                raise self._corrupt(f"has a bad item in the answer {op_id}")
            items.append(ItemInfo(
                self._text(entry.get("id"), f"an item id in the answer {op_id}"),
                self._text(entry.get("name"), f"an item name in the answer {op_id}"),
                self._text(entry.get("description"), f"an item description in the answer {op_id}"),
            ))
        return tuple(items)