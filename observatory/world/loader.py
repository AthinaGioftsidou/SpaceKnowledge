"""Building a world from data instead of from Python.

`WorldLoader.make_item` is the Factory Method. `build` is the code that depends
on it and never names a concrete Item class.
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from observatory.world.builder import RoomBuilder
from observatory.world.container import Container
from observatory.world.door import Door
from observatory.world.item import Item, PlainItem
from observatory.world.room import Room
from observatory.world.world import World


def raw_exits(raw: dict[str, Any], room_id: str) -> dict[str, str]:
    """The exits declared for a room in the file. Used to validate door sides."""
    for spec in raw["rooms"]:
        if spec["id"] == room_id:
            return spec.get("exits", {})
    return {}


class WorldLoader(ABC):
    """The Creator. Knows how to assemble a world, not what items are made of."""

    def load(self, path: Path) -> World:
        return self.build(json.loads(path.read_text(encoding="utf-8")))

    def build(self, raw: dict[str, Any]) -> World:
        """Two passes, and the order is forced rather than stylistic.
        No exit can be wired until every room it might point at exists."""
        rooms: dict[str, Room] = {}
        for spec in raw["rooms"]:
            builder = RoomBuilder(spec["id"]).named(spec["name"])
            builder.described(spec["description"])
            for item_spec in spec.get("items", []):
                builder.holding(self.make_item(item_spec))
            room = builder.build()
            if room.room_id in rooms:
                raise ValueError(f"duplicate room id {room.room_id}")
            rooms[room.room_id] = room

        doors = self.build_doors(raw, rooms, self.item_ids(raw))

        for spec in raw["rooms"]:
            for direction, target in spec.get("exits", {}).items():
                if target not in rooms:
                    raise ValueError(
                        f"room {spec['id']} exits {direction} to unknown room {target}"
                    )
                rooms[spec["id"]].add_exit(
                    direction, rooms[target], doors.get((spec["id"], direction))
                )

        return World(rooms, raw["start"])

    def item_ids(self, raw: dict[str, Any]) -> set[str]:
        """Every item id in the file, including ones nested inside containers."""
        found: set[str] = set()

        def walk(specs: list[dict[str, Any]]) -> None:
            for spec in specs:
                found.add(spec["id"])
                walk(spec.get("contains", []))

        for room in raw["rooms"]:
            walk(room.get("items", []))
        return found

    def build_doors(
        self, raw: dict[str, Any], rooms: dict[str, Room], item_ids: set[str]
    ) -> dict[tuple[str, str], Door]:
        """One Door per spec, indexed by every (room, direction) it sits on.

        Both sides get the SAME object, so unlocking from the stairwell unlocks
        it from the dome. A door with a state per side is two doors wearing one
        name, and players find that out at the worst possible moment.

        No Factory Method here. There is one kind of door, and week 2 argued
        that an abstraction with one implementation is a liability. If a second
        kind ever arrives, `make_door` is the obvious place to put it.
        """
        by_side: dict[tuple[str, str], Door] = {}
        for spec in raw.get("doors", []):
            # A door whose key does not exist anywhere is an unwinnable world.
            # Caught here, at load, rather than by a player an hour later.
            if spec["key"] not in item_ids:
                raise ValueError(
                    f"door {spec['id']} needs key {spec['key']}, which no room holds"
                )
            door = Door(spec["id"], spec["name"], spec["key"])
            for side in spec["sides"]:
                room_id, direction = side["room"], side["direction"]
                if room_id not in rooms:
                    raise ValueError(f"door {spec['id']} is in unknown room {room_id}")
                if direction not in raw_exits(raw, room_id):
                    raise ValueError(
                        f"door {spec['id']} blocks {room_id} {direction},"
                        " which is not an exit"
                    )
                by_side[(room_id, direction)] = door
        return by_side

    @abstractmethod
    def make_item(self, spec: dict[str, Any]) -> Item:
        """THE FACTORY METHOD. Subclasses decide which concrete Item to build."""


class StandardWorldLoader(WorldLoader):
    """The Concrete Creator. The only place in the system that names PlainItem."""

    def make_item(self, spec: dict[str, Any]) -> Item:
        # Required, not defaulted: treating a missing kind as "plain" hides the
        # typo for ever. Raised explicitly so missing and unknown are one type.
        if "kind" not in spec:
            raise ValueError("item spec has no kind")
        kind = spec["kind"]
        if kind == "plain":
            return PlainItem(spec["id"], spec["name"], spec["description"])
        if kind == "container":
            container = Container(spec["id"], spec["name"], spec["description"])
            for inner in spec.get("contains", []):
                container.add(self.make_item(inner))
            return container
        raise ValueError(f"unknown item kind: {kind}")
