"""Tests for the Broker's mine flow and for resources surviving a restart."""

import unittest

from observatory.broker.broker import Broker
from observatory.broker.inventory_entry import InventoryEntry
from observatory.broker.inventory_repository import InMemoryInventoryRepository
from observatory.common.messages import Request, Response
from observatory.transport.channel import InMemoryChannel, UniverseChannel
from observatory.universe.deposits import Deposits
from observatory.universe.universe import Universe
from observatory.world.room import Room
from observatory.world.world import World


class CountingChannel(UniverseChannel):
    """Passes everything on and counts how many requests were sent."""

    def __init__(self, inner: UniverseChannel) -> None:
        self._inner = inner
        self.sent = 0

    def send(self, request: Request) -> Response:
        self.sent += 1
        return self._inner.send(request)


class TestMining(unittest.TestCase):
    def setUp(self) -> None:
        earth = Room("earth", "Earth", "Home.")
        self.deposits = Deposits({"earth": {"iron": 10}})
        universe = Universe(World({"earth": earth}, "earth"), self.deposits)
        universe.place_player("ada", "earth")
        self.channel = CountingChannel(InMemoryChannel(universe))
        self.repository = InMemoryInventoryRepository()
        self.broker = self.restart()
        self.broker.add_player("ada")

    def restart(self) -> Broker:
        return Broker(self.channel, self.repository)

    def test_a_new_player_has_an_empty_bag(self) -> None:
        self.assertTrue(self.broker.resources_of("ada").is_empty())

    def test_a_successful_mine_fills_the_bag_and_empties_the_deposit(self) -> None:
        self.assertIsNone(self.broker.mine("ada", "iron", 3))
        self.assertEqual(3, self.broker.resources_of("ada").amount_of("iron"))
        self.assertEqual(7, self.deposits.available("earth", "iron"))

    def test_every_mine_gets_its_own_op_id(self) -> None:
        # If two mines shared an op_id, the Universe would answer the second
        # from memory and the deposit would only go down once.
        self.broker.mine("ada", "iron", 3)
        self.broker.mine("ada", "iron", 3)
        self.assertEqual(6, self.broker.resources_of("ada").amount_of("iron"))
        self.assertEqual(4, self.deposits.available("earth", "iron"))

    def test_a_refusal_from_the_universe_leaves_the_bag_unchanged(self) -> None:
        refusal = self.broker.mine("ada", "iron", 11)
        self.assertIn("only 10", refusal.describe())
        self.assertTrue(self.broker.resources_of("ada").is_empty())
        self.assertEqual(10, self.deposits.available("earth", "iron"))

    def test_an_unknown_player_is_refused_and_nothing_is_sent(self) -> None:
        refusal = self.broker.mine("bob", "iron", 1)
        self.assertIn("bob", refusal.describe())
        self.assertEqual(0, self.channel.sent)

    def test_an_amount_below_one_is_refused_and_nothing_is_sent(self) -> None:
        refusal = self.broker.mine("ada", "iron", 0)
        self.assertIn("at least 1", refusal.describe())
        self.assertEqual(0, self.channel.sent)

    def test_an_amount_that_is_not_a_whole_number_is_refused(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            self.broker.mine("ada", "iron", 2.5)  # type: ignore[arg-type]

    def test_resources_of_an_unknown_player_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.broker.resources_of("bob")


class TestRestart(unittest.TestCase):
    def setUp(self) -> None:
        earth = Room("earth", "Earth", "Home.")
        universe = Universe(
            World({"earth": earth}, "earth"), Deposits({"earth": {"iron": 10}})
        )
        universe.place_player("ada", "earth")
        self.universe = universe
        self.repository = InMemoryInventoryRepository()
        self.broker = self.restart()
        self.broker.add_player("ada")

    def restart(self) -> Broker:
        return Broker(InMemoryChannel(self.universe), self.repository)

    def test_mined_resources_survive_a_restart(self) -> None:
        self.broker.mine("ada", "iron", 3)
        self.assertEqual(3, self.restart().resources_of("ada").amount_of("iron"))

    def test_a_refused_mine_leaves_nothing_saved(self) -> None:
        self.broker.mine("ada", "iron", 11)
        self.assertTrue(self.restart().resources_of("ada").is_empty())

    def test_items_and_resources_both_survive(self) -> None:
        self.broker.give("ada", InventoryEntry("torch", "torch"))
        self.broker.mine("ada", "iron", 2)
        again = self.restart()
        self.assertIsNotNone(again.inventory_of("ada").find("torch"))
        self.assertEqual(2, again.resources_of("ada").amount_of("iron"))

class TestOpIdsAcrossRuns(unittest.TestCase):
    def test_a_restarted_broker_does_not_reuse_old_operation_ids(self) -> None:
        # The Universe remembers answers by op_id. If a new run started again
        # at op1, its first mine would get the old run's answer and mine nothing.
        earth = Room("earth", "Earth", "Home.")
        deposits = Deposits({"earth": {"iron": 10}})
        universe = Universe(World({"earth": earth}, "earth"), deposits)
        universe.place_player("ada", "earth")
        repository = InMemoryInventoryRepository()

        first = Broker(InMemoryChannel(universe), repository)
        first.add_player("ada")
        first.mine("ada", "iron", 3)

        second = Broker(InMemoryChannel(universe), repository)
        second.mine("ada", "iron", 3)

        self.assertEqual(4, deposits.available("earth", "iron"))
        self.assertEqual(6, second.resources_of("ada").amount_of("iron"))

if __name__ == "__main__":
    unittest.main()