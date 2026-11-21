"""Building a world from data (a JSON file) instead of from Python code.

`WorldLoader.make_item` is the Factory Method: `build` depends on it and never
names a concrete Item class.
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from spaceknowledge.world.builder import DestinationBuilder
from spaceknowledge.world.container import Container
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.door import Door
from spaceknowledge.world.item import Item, PlainItem
from spaceknowledge.world.world import World


def raw_exits(raw: dict[str, Any], destination_id: str) -> dict[str, str]:
    """The exits a destination declares in the file, to validate door sides."""
    for spec in raw["destinations"]:
        if spec["id"] == destination_id:
            return spec.get("exits", {})
    return {}


class WorldLoader(ABC):
    """The creator: knows how to assemble a world, not what items are made of."""

    def load(self, path: Path) -> World:
        return self.build(json.loads(path.read_text(encoding="utf-8")))

    def build(self, raw: dict[str, Any]) -> World:
        """Two passes, and the order is forced: no route can be wired until
        every destination it might point at exists."""
        destinations: dict[str, Destination] = {}
        for spec in raw["destinations"]:
            builder = DestinationBuilder(spec["id"]).named(spec["name"])
            builder.described(spec["description"])
            for item_spec in spec.get("items", []):
                builder.holding(self.make_item(item_spec))
            destination = builder.build()
            if destination.destination_id in destinations:
                raise ValueError(f"duplicate destination id {destination.destination_id}")
            destinations[destination.destination_id] = destination

        doors = self.build_doors(raw, destinations, self.item_ids(raw))

        for spec in raw["destinations"]:
            for direction, target in spec.get("exits", {}).items():
                if target not in destinations:
                    raise ValueError(
                        f"destination {spec['id']} exits {direction} "
                        f"to unknown destination {target}"
                    )
                destinations[spec["id"]].add_exit(
                    direction, destinations[target], doors.get((spec["id"], direction))
                )

        return World(destinations, raw["start"])

    def item_ids(self, raw: dict[str, Any]) -> set[str]:
        """Every item id in the file, including ones nested in containers."""
        found: set[str] = set()

        def walk(specs: list[dict[str, Any]]) -> None:
            for spec in specs:
                found.add(spec["id"])
                walk(spec.get("contains", []))

        for spec in raw["destinations"]:
            walk(spec.get("items", []))
        return found

    def build_doors(
        self, raw: dict[str, Any], destinations: dict[str, Destination], item_ids: set[str]
    ) -> dict[tuple[str, str], Door]:
        """One Door per spec, indexed by every (destination, direction) it
        sits on. Both sides get the SAME object, so unlocking from one side
        unlocks the other. A door whose key exists nowhere makes an
        unwinnable world, so that is refused here, at load time."""
        by_side: dict[tuple[str, str], Door] = {}
        for spec in raw.get("doors", []):
            if spec["key"] not in item_ids and not spec["key"].startswith("mission:"):
                raise ValueError(
                    f"door {spec['id']} needs key {spec['key']}, which no destination holds"
                )
            door = Door(spec["id"], spec["name"], spec["key"])
            for side in spec["sides"]:
                destination_id, direction = side["destination"], side["direction"]
                if destination_id not in destinations:
                    raise ValueError(
                        f"door {spec['id']} is in unknown destination {destination_id}"
                    )
                if direction not in raw_exits(raw, destination_id):
                    raise ValueError(
                        f"door {spec['id']} blocks {destination_id} {direction}, "
                        "which is not an exit"
                    )
                by_side[(destination_id, direction)] = door
        return by_side

    @abstractmethod
    def make_item(self, spec: dict[str, Any]) -> Item:
        """THE FACTORY METHOD: subclasses decide which concrete Item to build."""


class StandardWorldLoader(WorldLoader):
    """The concrete creator: the only place that names PlainItem."""

    def make_item(self, spec: dict[str, Any]) -> Item:
        # A missing kind is an error, not a default, so a typo is never hidden.
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