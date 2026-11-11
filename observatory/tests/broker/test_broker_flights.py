"""Tests that every request the Broker sends is a Transition in flight."""

import unittest
from collections.abc import Callable

from observatory.broker.broker import Broker
from observatory.broker.inventory_entry import InventoryEntry
from observatory.broker.inventory_repository import InMemoryInventoryRepository
from observatory.common.messages import Request, Response
from observatory.transport.channel import InMemoryChannel, UniverseChannel
from observatory.universe.deposits import Deposits
from observatory.universe.universe import Universe
from observatory.world.room import Room
from observatory.world.world import World


class WatchingChannel(UniverseChannel):
    """Passes requests on, and looks at the Broker while each one is in flight."""

    def __init__(self, inner: UniverseChannel) -> None:
        self._inner = inner
        self.watch: Callable[[], list[str]] | None = None
        self.seen: list[list[str]] = []

    def send(self, request: Request) -> Response:
        if self.watch is not None:
            self.seen.append(self.watch())
        return self._inner.send(request)


class LostChannel(UniverseChannel):
    def send(self, request: Request) -> Response:
        raise ConnectionError("lost")


class FailingRepository(InMemoryInventoryRepository):
    def __init__(self) -> None:
        super().__init__()
        self.fail = False

    def save(self, records, resources=None, pending=None) -> None:  # type: ignore[no-untyped-def]
        if self.fail:
            raise OSError("disk full")
        super().save(records, resources, pending)


def an_earth() -> Universe:
    earth = Room("earth", "Earth", "Home.")
    universe = Universe(World({"earth": earth}, "earth"), Deposits({"earth": {"iron": 10}}))
    universe.place_player("ada", "earth")
    return universe


class TestFlightsWhileTheUniverseDecides(unittest.TestCase):
    def setUp(self) -> None:
        self.channel = WatchingChannel(InMemoryChannel(an_earth()))
        self.broker = Broker(self.channel)
        self.broker.add_player("ada")
        self.channel.watch = self.broker.in_flight_phases

    def test_nothing_is_in_flight_at_rest(self) -> None:
        self.assertEqual([], self.broker.in_flight_phases())

    def test_a_mine_is_being_mined_while_in_flight_and_gone_after(self) -> None:
        self.broker.mine("ada", "iron", 3)
        self.assertEqual([["being_mined"]], self.channel.seen)
        self.assertEqual([], self.broker.in_flight_phases())

    def test_a_refused_mine_also_leaves_nothing_in_flight(self) -> None:
        self.broker.mine("ada", "iron", 11)
        self.assertEqual([["being_mined"]], self.channel.seen)
        self.assertEqual([], self.broker.in_flight_phases())

    def test_a_drop_is_being_dropped_while_in_flight_and_gone_after(self) -> None:
        self.broker.give("ada", InventoryEntry("torch", "torch"))
        self.broker.drop("ada", "torch")
        self.assertEqual([["being_dropped"]], self.channel.seen)
        self.assertEqual([], self.broker.in_flight_phases())


class TestFlightsAcrossACrash(unittest.TestCase):
    def test_a_lost_request_stays_in_flight_until_it_is_recovered(self) -> None:
        universe = an_earth()
        repository = InMemoryInventoryRepository()
        broker = Broker(LostChannel(), repository)
        broker.add_player("ada")
        with self.assertRaises(ConnectionError):
            broker.mine("ada", "iron", 3)
        self.assertEqual(["being_mined"], broker.in_flight_phases())

        again = Broker(InMemoryChannel(universe), repository)
        self.assertEqual(["being_mined"], again.in_flight_phases())
        again.recover()
        self.assertEqual([], again.in_flight_phases())
        self.assertEqual(3, again.resources_of("ada").amount_of("iron"))

    def test_a_request_that_could_not_be_saved_is_not_in_flight(self) -> None:
        repository = FailingRepository()
        broker = Broker(InMemoryChannel(an_earth()), repository)
        broker.add_player("ada")
        repository.fail = True
        with self.assertRaises(OSError):
            broker.mine("ada", "iron", 1)
        self.assertEqual([], broker.in_flight_phases())


if __name__ == "__main__":
    unittest.main()