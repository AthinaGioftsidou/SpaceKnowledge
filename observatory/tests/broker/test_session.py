"""Tests for Session: one player's text in, text out."""

import unittest

from observatory.broker.broker import Broker
from observatory.broker.inventory_entry import InventoryEntry
from observatory.broker.parser import Parser
from observatory.broker.session import Session
from observatory.transport.channel import InMemoryChannel
from observatory.universe.universe import Universe
from observatory.world.room import Room
from observatory.world.world import World
from observatory.universe.deposits import Deposits


def a_session() -> tuple[Session, Room]:
    hall = Room("hall", "Hall", "Cold and tiled.")
    universe = Universe(World({"hall": hall}, "hall"))
    universe.place_player("ada", "hall")
    broker = Broker(InMemoryChannel(universe))
    broker.add_player("ada")
    broker.give("ada", InventoryEntry("torch", "torch"))
    return Session(broker, Parser(), "ada"), hall


class TestSession(unittest.TestCase):
    def test_a_typed_drop_works_from_text_to_world(self) -> None:
        session, hall = a_session()
        self.assertEqual("You drop the torch.", session.submit("drop the torch"))
        self.assertIsNotNone(hall.find_item("torch"))

    def test_the_inventory_changes_after_a_drop(self) -> None:
        session, _ = a_session()
        session.submit("drop torch")
        self.assertIn("nothing", session.submit("inventory"))

    def test_nonsense_is_answered_with_a_three_part_refusal(self) -> None:
        session, _ = a_session()
        text = session.submit("juggle torch")
        self.assertIn("juggle torch", text)
        self.assertIn("Why:", text)
        self.assertIn("Next:", text)

    def test_a_blank_line_is_answered_too(self) -> None:
        session, _ = a_session()
        self.assertIn("Refused", session.submit("   "))

    def test_help_lists_the_verbs(self) -> None:
        session, _ = a_session()
        self.assertIn("drop", session.submit("help"))

    def test_a_string_is_refused_where_a_class_is_expected(self) -> None:
        session, _ = a_session()
        broker = Broker(InMemoryChannel(Universe(World({"h": Room("h", "H", "d")}, "h"))))
        calls = [
            ("Session broker", lambda: Session("x", Parser(), "ada")),
            ("Session parser", lambda: Session(broker, "x", "ada")),
        ]
        for label, call in calls:
            with self.subTest(label):
                with self.assertRaisesRegex(TypeError, "must be"):
                    call()

class TestSessionMining(unittest.TestCase):
    def test_a_typed_mine_works_from_text_to_the_bag(self) -> None:
        earth = Room("earth", "Earth", "Home.")
        universe = Universe(World({"earth": earth}, "earth"), Deposits({"earth": {"iron": 10}}))
        universe.place_player("ada", "earth")
        broker = Broker(InMemoryChannel(universe))
        broker.add_player("ada")
        session = Session(broker, Parser(), "ada")
        self.assertEqual("You mine 3 iron.", session.submit("mine iron 3"))
        self.assertIn("iron 3", session.submit("inventory"))
        self.assertIn("mine", session.submit("help"))

if __name__ == "__main__":
    unittest.main()