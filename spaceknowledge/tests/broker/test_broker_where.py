"""Tests for Broker.where and the where command."""

import unittest

from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.command import WhereCommand
from spaceknowledge.broker.parser import ParseError, Parser
from spaceknowledge.common.messages import Request, Response
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.transport.channel import InMemoryChannel, UniverseChannel
from spaceknowledge.universe.universe import Universe
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World


class LostChannel(UniverseChannel):
    def send(self, request: Request) -> Response:
        raise ConnectionError("lost")


def a_broker() -> Broker:
    earth, moon = Destination("earth", "Earth", "Home."), Destination("moon", "The Moon", "Grey.")
    broker = Broker(InMemoryChannel(Universe(World({"earth": earth, "moon": moon}, "earth"))))
    broker.join("ada", "earth")
    return broker


class TestWhere(unittest.TestCase):
    def test_a_player_is_told_where_they_are(self) -> None:
        self.assertEqual(("earth", "Earth"), a_broker().where("ada"))

    def test_a_stranger_is_refused(self) -> None:
        self.assertIsInstance(a_broker().where("eve"), Refusal)

    def test_asking_leaves_nothing_pending(self) -> None:
        broker = a_broker()
        broker.where("ada")
        self.assertEqual(0, broker.pending_count())

    def test_a_lost_universe_raises_and_leaves_nothing_pending(self) -> None:
        broker = Broker(LostChannel())
        broker.add_player("ada")
        with self.assertRaises(ConnectionError):
            broker.where("ada")
        self.assertEqual(0, broker.pending_count())


class TestWhereCommand(unittest.TestCase):
    def test_the_reply_names_the_place(self) -> None:
        self.assertEqual("You are at Earth.", WhereCommand().execute(a_broker(), "ada"))

    def test_a_refusal_is_described(self) -> None:
        self.assertIn("Next:", WhereCommand().execute(a_broker(), "eve"))

    def test_the_parser_knows_it(self) -> None:
        self.assertIsInstance(Parser().parse("where"), WhereCommand)
        self.assertIn("where", Parser().verbs())
        with self.assertRaises(ParseError):
            Parser().parse("where now")

    def test_a_string_is_refused_where_a_broker_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            WhereCommand().execute("broker", "ada")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()