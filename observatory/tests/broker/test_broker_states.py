"""Tests that a drop goes through the states and a mine does not."""

import unittest
from collections.abc import Callable

from observatory.broker.broker import Broker
from observatory.broker.inventory_entry import InventoryEntry
from observatory.broker.inventory_repository import InMemoryInventoryRepository
from observatory.common.messages import Request, Response
from observatory.transport.channel import InMemoryChannel, UniverseChannel
from observatory.universe.deposits import Deposits
from observatory.universe.universe import Universe
from observatory.world.item import PlainItem
from observatory.world.room import Room
from observatory.world.world import World


class WatchingChannel(UniverseChannel):
    """Passes requests on, and looks at the Broker while each one is in flight."""

    def __init__(self, inner: UniverseChannel) -> None:
        self._inner = inner
        self.watch: Callable[[], object] | None = None
        self.seen: list[object] = []

    def send(self, request: Request) -> Response:
        if self.watch is not None:
            self.seen.append(self.watch())
        return self._inner.send(request)


class LostChannel(UniverseChannel):
    def send(self, request: Request) -> Response:
        raise ConnectionError("lost")


def an_earth() -> tuple[Universe, Room]:
    earth = Room("earth", "Earth", "Home.")
    universe = Universe(World({"earth": earth}, "earth"), Deposits({"earth": {"iron": 10}}))
    universe.place_player("ada", "earth")
    return universe, earth


class TestDropStates(unittest.TestCase):
    def setUp(self) -> None:
        self.universe, self.earth = an_earth()
        self.channel = WatchingChannel(InMemoryChannel(self.universe))
        self.broker = Broker(self.channel)
        self.broker.add_player("ada")
        self.broker.give("ada", InventoryEntry("torch", "torch"))
        self.channel.watch = lambda: (
            self.broker.inventory_of("ada").find("torch").state(),
            self.broker.inventory_of("ada").find("torch").holder(),
        )

    def test_a_drop_is_in_flight_while_the_universe_decides(self) -> None:
        self.broker.drop("ada", "torch")
        self.assertEqual([("flight", "broker")], self.channel.seen)

    def test_a_confirmed_drop_leaves_the_inventory_and_lands_in_the_world(self) -> None:
        self.assertIsNone(self.broker.drop("ada", "torch"))
        self.assertEqual(0, self.broker.inventory_of("ada").count())
        self.assertIsNotNone(self.earth.find_item("torch"))

    def test_a_refused_drop_is_owned_again(self) -> None:
        self.earth.add_item(PlainItem("torch", "torch", "a torch already here"))
        self.assertIsNotNone(self.broker.drop("ada", "torch"))
        self.assertEqual("owned", self.broker.inventory_of("ada").find("torch").state())


class TestMiningHasNoStates(unittest.TestCase):
    def test_a_mine_is_a_request_and_a_pending_note_while_it_waits(self) -> None:
        universe, _ = an_earth()
        channel = WatchingChannel(InMemoryChannel(universe))
        broker = Broker(channel)
        broker.add_player("ada")
        broker.give("ada", InventoryEntry("torch", "torch"))
        channel.watch = lambda: (broker.pending_count(),
                                 broker.inventory_of("ada").find("torch").state())
        broker.mine("ada", "iron", 3)
        self.assertEqual([(1, "owned")], channel.seen)
        self.assertEqual(0, broker.pending_count())
        self.assertEqual(3, broker.resources_of("ada").amount_of("iron"))


class TestAcrossACrash(unittest.TestCase):
    def test_a_lost_drop_is_in_flight_after_a_restart_until_recovered(self) -> None:
        universe, earth = an_earth()
        repository = InMemoryInventoryRepository()
        broker = Broker(LostChannel(), repository)
        broker.add_player("ada")
        broker.give("ada", InventoryEntry("torch", "torch"))
        with self.assertRaises(ConnectionError):
            broker.drop("ada", "torch")

        again = Broker(InMemoryChannel(universe), repository)
        self.assertEqual("flight", again.inventory_of("ada").find("torch").state())
        self.assertEqual(1, again.recover())
        self.assertEqual(0, again.inventory_of("ada").count())
        self.assertIsNotNone(earth.find_item("torch"))

    def test_a_lost_mine_is_finished_by_recovery(self) -> None:
        universe, _ = an_earth()
        repository = InMemoryInventoryRepository()
        broker = Broker(LostChannel(), repository)
        broker.add_player("ada")
        with self.assertRaises(ConnectionError):
            broker.mine("ada", "iron", 3)
        again = Broker(InMemoryChannel(universe), repository)
        self.assertEqual(1, again.pending_count())
        again.recover()
        self.assertEqual(3, again.resources_of("ada").amount_of("iron"))


if __name__ == "__main__":
    unittest.main()