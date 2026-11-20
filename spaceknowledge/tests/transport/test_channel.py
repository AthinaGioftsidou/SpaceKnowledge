"""Tests for the channel between the Broker and the Universe."""

import unittest

from spaceknowledge.common.messages import Request
from spaceknowledge.transport.channel import InMemoryChannel, UniverseChannel
from spaceknowledge.universe.universe import Universe
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World


class TestInMemoryChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.hall = Destination("hall", "Hall", "Cold and tiled.")
        self.universe = Universe(World({"hall": self.hall}, "hall"))
        self.universe.place_player("ada", "hall")
        self.channel = InMemoryChannel(self.universe)

    def test_it_is_a_universe_channel(self) -> None:
        self.assertIsInstance(self.channel, UniverseChannel)

    def test_a_request_reaches_the_universe_and_the_answer_comes_back(self) -> None:
        response = self.channel.send(Request("op1", "add_item", "ada", "torch"))
        self.assertTrue(response.ok)
        self.assertEqual("op1", response.op_id)
        self.assertIsNotNone(self.hall.find_item("torch"))

    def test_a_string_is_refused_where_a_class_is_expected(self) -> None:
        bad = "not an object"
        calls = [
            ("InMemoryChannel universe", lambda: InMemoryChannel(bad)),
            ("send request", lambda: self.channel.send(bad)),
        ]
        for label, call in calls:
            with self.subTest(label):
                with self.assertRaisesRegex(TypeError, "must be"):
                    call()

    def test_the_abstract_channel_cannot_be_built(self) -> None:
        with self.assertRaises(TypeError):
            UniverseChannel()  # type: ignore[abstract]


if __name__ == "__main__":
    unittest.main()