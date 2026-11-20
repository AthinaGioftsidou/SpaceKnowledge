"""Tests for Broker.join: a new player gets a record, a torch and a place."""

import unittest

from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.inventory_repository import InMemoryInventoryRepository
from spaceknowledge.common.messages import Request, Response
from spaceknowledge.transport.channel import InMemoryChannel, UniverseChannel
from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.universe import Universe
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World


class LostChannel(UniverseChannel):
    def send(self, request: Request) -> Response:
        raise ConnectionError("lost")


def a_universe() -> Universe:
    earth, mars = Destination("earth", "Earth", "Home."), Destination("mars", "Mars", "Red.")
    return Universe(World({"earth": earth, "mars": mars}, "earth"),
                    Deposits({"earth": {"iron": 10}}))


class TestJoin(unittest.TestCase):
    def setUp(self) -> None:
        self.universe = a_universe()
        self.broker = Broker(InMemoryChannel(self.universe))

    def test_a_new_player_gets_a_record_a_torch_and_a_place(self) -> None:
        self.assertIsNone(self.broker.join("ada", "earth"))
        self.assertTrue(self.broker.has_player("ada"))
        self.assertIsNotNone(self.broker.inventory_of("ada").resolve("torch"))
        self.assertEqual("earth", self.universe.location_of("ada"))

    def test_joining_again_gives_no_second_torch_and_does_not_move_the_player(self) -> None:
        self.broker.join("ada", "earth")
        self.broker.drop("ada", "torch")
        self.assertIsNone(self.broker.join("ada", "mars"))
        self.assertEqual(0, self.broker.inventory_of("ada").count())
        self.assertEqual("earth", self.universe.location_of("ada"))

    def test_an_unknown_destination_is_refused_and_nothing_stays_pending(self) -> None:
        refusal = self.broker.join("ada", "nowhere")
        self.assertIn("nowhere", refusal.describe())
        self.assertEqual(0, self.broker.pending_count())

    def test_a_lost_join_is_finished_by_recovery(self) -> None:
        repository = InMemoryInventoryRepository()
        broker = Broker(LostChannel(), repository)
        with self.assertRaises(ConnectionError):
            broker.join("ada", "earth")
        self.assertEqual(1, broker.pending_count())
        again = Broker(InMemoryChannel(self.universe), repository)
        self.assertEqual(1, again.recover())
        self.assertEqual("earth", self.universe.location_of("ada"))
        self.assertIsNotNone(again.inventory_of("ada").resolve("torch"))

    def test_empty_arguments_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.broker.join("", "earth")
        with self.assertRaises(ValueError):
            self.broker.join("ada", "")


if __name__ == "__main__":
    unittest.main()