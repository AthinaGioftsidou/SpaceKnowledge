"""Tests that every player has their own items, even when the names match."""

import unittest

from spaceknowledge.broker.broker import Broker
from spaceknowledge.transport.channel import InMemoryChannel
from spaceknowledge.universe.universe import Universe
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World


class TestEachPlayerHasTheirOwnTorch(unittest.TestCase):
    def setUp(self) -> None:
        self.hall = Destination("hall", "Hall", "Cold and tiled.")
        self.broker = Broker(InMemoryChannel(Universe(World({"hall": self.hall}, "hall"))))
        self.broker.join("ada", "hall")
        self.broker.join("bob", "hall")

    def torch_of(self, player: str):  # type: ignore[no-untyped-def]
        return self.broker.inventory_of(player).resolve("torch")

    def test_the_starting_torches_share_a_name_and_not_an_id(self) -> None:
        ada, bob = self.torch_of("ada"), self.torch_of("bob")
        self.assertEqual(ada.name, bob.name)
        self.assertNotEqual(ada.item_id, bob.item_id)

    def test_both_players_can_drop_theirs(self) -> None:
        self.assertIsNone(self.broker.drop("ada", "torch"))
        self.assertIsNone(self.broker.drop("bob", "torch"))
        self.assertEqual(2, self.hall.item_count())

    def test_picking_by_name_takes_one_and_a_carried_torch_does_not_block_another(self) -> None:
        self.broker.drop("ada", "torch")
        self.broker.drop("bob", "torch")
        self.assertIsNone(self.broker.pick("ada", "torch"))
        self.assertEqual(1, self.hall.item_count())
        self.assertIsNone(self.broker.pick("ada", "torch"))
        self.assertEqual(0, self.hall.item_count())
        self.assertEqual(2, self.broker.inventory_of("ada").count())


if __name__ == "__main__":
    unittest.main()