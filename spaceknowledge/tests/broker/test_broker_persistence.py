"""Tests that the Broker's players and inventories survive a restart."""

import shutil
import tempfile
import unittest
from pathlib import Path

from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.inventory_entry import InventoryEntry
from spaceknowledge.broker.inventory_repository import (
    InMemoryInventoryRepository,
    InventoryRepository,
    JsonInventoryRepository,
)
from spaceknowledge.common.messages import Request, Response
from spaceknowledge.transport.channel import InMemoryChannel, UniverseChannel
from spaceknowledge.universe.universe import Universe
from spaceknowledge.world.item import PlainItem
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World


class PeekingChannel(UniverseChannel):
    """Looks at the stored data while a request is in flight."""

    def __init__(self, inner: UniverseChannel, repository: InventoryRepository) -> None:
        self._inner = inner
        self._repository = repository
        self.peeked: dict[str, list[tuple[str, str]]] = {}

    def send(self, request: Request) -> Response:
        self.peeked = self._repository.load()
        return self._inner.send(request)


class TestRestart(unittest.TestCase):
    def setUp(self) -> None:
        self.hall = Destination("hall", "Hall", "Cold and tiled.")
        self.universe = Universe(World({"hall": self.hall}, "hall"))
        self.universe.place_player("ada", "hall")
        self.repository = InMemoryInventoryRepository()
        self.broker = self.restart()
        self.broker.add_player("ada")
        self.broker.give("ada", InventoryEntry("torch", "torch"))

    def restart(self) -> Broker:
        return Broker(InMemoryChannel(self.universe), self.repository)

    def test_a_broker_with_nothing_saved_starts_empty(self) -> None:
        fresh = Broker(InMemoryChannel(self.universe), InMemoryInventoryRepository())
        with self.assertRaises(KeyError):
            fresh.inventory_of("ada")

    def test_players_and_items_survive_a_restart(self) -> None:
        again = self.restart()
        self.assertIsNotNone(again.inventory_of("ada").find("torch"))

    def test_a_restored_item_is_usable(self) -> None:
        again = self.restart()
        self.assertIsNone(again.inventory_of("ada").check_usable("torch"))

    def test_a_confirmed_drop_stays_dropped_after_a_restart(self) -> None:
        self.broker.drop("ada", "torch")
        again = self.restart()
        self.assertEqual(0, again.inventory_of("ada").count())

    def test_a_refused_drop_keeps_the_item_after_a_restart(self) -> None:
        self.hall.add_item(PlainItem("torch", "torch", "a torch already here"))
        self.broker.drop("ada", "torch")
        again = self.restart()
        self.assertEqual(1, again.inventory_of("ada").count())

    def test_the_stored_copy_still_has_the_item_while_the_universe_decides(self) -> None:
        channel = PeekingChannel(InMemoryChannel(self.universe), self.repository)
        broker = Broker(channel, self.repository)
        broker.drop("ada", "torch")
        self.assertEqual([("torch", "torch")], channel.peeked["ada"])

    def test_a_string_is_refused_where_a_repository_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            Broker(InMemoryChannel(self.universe), "players.json")  # type: ignore[arg-type]


class TestRestartThroughARealFile(unittest.TestCase):
    def test_a_second_broker_reads_what_the_first_wrote(self) -> None:
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory)
        path = directory / "players.json"
        hall = Destination("hall", "Hall", "Cold and tiled.")
        universe = Universe(World({"hall": hall}, "hall"))

        first = Broker(InMemoryChannel(universe), JsonInventoryRepository(path))
        first.add_player("ada")
        first.give("ada", InventoryEntry("brass_key", "brass key"))

        second = Broker(InMemoryChannel(universe), JsonInventoryRepository(path))
        entry = second.inventory_of("ada").find("brass_key")
        self.assertEqual("brass key", entry.name)


if __name__ == "__main__":
    unittest.main()