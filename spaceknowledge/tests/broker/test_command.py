"""Tests for the Broker's commands."""

import unittest

from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.command import Command, DropCommand, InventoryCommand, LookCommand, PickCommand
from spaceknowledge.broker.inventory_entry import InventoryEntry
from spaceknowledge.transport.channel import InMemoryChannel
from spaceknowledge.universe.universe import Universe
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World
from spaceknowledge.broker.command import Command, DropCommand, InventoryCommand, MineCommand
from spaceknowledge.universe.deposits import Deposits


def a_setup() -> tuple[Broker, Destination]:
    hall = Destination("hall", "Hall", "Cold and tiled.")
    universe = Universe(World({"hall": hall}, "hall"))
    universe.place_player("ada", "hall")
    broker = Broker(InMemoryChannel(universe))
    broker.add_player("ada")
    broker.give("ada", InventoryEntry("torch", "torch"))
    return broker, hall


class TestInventoryCommand(unittest.TestCase):
    def test_it_lists_what_the_player_carries(self) -> None:
        broker, _ = a_setup()
        self.assertEqual("You are carrying: torch", InventoryCommand().execute(broker, "ada"))

    def test_an_empty_inventory_says_so(self) -> None:
        broker, _ = a_setup()
        broker.drop("ada", "torch")
        self.assertIn("nothing", InventoryCommand().execute(broker, "ada"))

    def test_an_unknown_player_gets_a_refusal_text(self) -> None:
        broker, _ = a_setup()
        self.assertIn("bob", InventoryCommand().execute(broker, "bob"))


class TestDropCommand(unittest.TestCase):
    def test_a_successful_drop_is_reported_and_the_world_changes(self) -> None:
        broker, hall = a_setup()
        self.assertEqual("You drop the torch.", DropCommand("torch").execute(broker, "ada"))
        self.assertIsNotNone(hall.find_item("torch"))

    def test_a_refused_drop_explains_itself(self) -> None:
        broker, _ = a_setup()
        text = DropCommand("lantern").execute(broker, "ada")
        self.assertIn("not carrying lantern", text)
        self.assertIn("Next:", text)

    def test_an_empty_target_is_refused_at_construction(self) -> None:
        with self.assertRaises(ValueError):
            DropCommand("")


class TestTheInterface(unittest.TestCase):
    def test_a_command_cannot_be_built_without_execute(self) -> None:
        with self.assertRaises(TypeError):
            Command()  # type: ignore[abstract]


class TestArgumentTypes(unittest.TestCase):
    def test_a_string_is_refused_where_a_broker_is_expected(self) -> None:
        bad = "not an object"
        calls = [
            ("InventoryCommand.execute broker", lambda: InventoryCommand().execute(bad, "ada")),
            ("DropCommand.execute broker", lambda: DropCommand("torch").execute(bad, "ada")),
        ]
        for label, call in calls:
            with self.subTest(label):
                with self.assertRaisesRegex(TypeError, "must be"):
                    call()


def a_mining_broker() -> Broker:
    earth = Destination("earth", "Earth", "Home.")
    universe = Universe(World({"earth": earth}, "earth"), Deposits({"earth": {"iron": 10}}))
    universe.place_player("ada", "earth")
    broker = Broker(InMemoryChannel(universe))
    broker.add_player("ada")
    return broker


class TestMineCommand(unittest.TestCase):
    def test_a_successful_mine_is_reported(self) -> None:
        broker = a_mining_broker()
        self.assertEqual("You mine 3 iron.", MineCommand("iron", 3).execute(broker, "ada"))

    def test_a_refused_mine_explains_itself(self) -> None:
        text = MineCommand("iron", 11).execute(a_mining_broker(), "ada")
        self.assertIn("only 10", text)
        self.assertIn("Next:", text)

    def test_the_inventory_shows_resources(self) -> None:
        broker = a_mining_broker()
        MineCommand("iron", 3).execute(broker, "ada")
        self.assertEqual("Resources: iron 3", InventoryCommand().execute(broker, "ada"))

    def test_the_inventory_shows_items_and_resources(self) -> None:
        broker = a_mining_broker()
        broker.give("ada", InventoryEntry("torch", "torch"))
        MineCommand("iron", 3).execute(broker, "ada")
        self.assertEqual(
            "You are carrying: torch\nResources: iron 3",
            InventoryCommand().execute(broker, "ada"),
        )

    def test_a_bad_construction_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            MineCommand("")
        with self.assertRaises(ValueError):
            MineCommand("iron", 0)
        with self.assertRaisesRegex(TypeError, "must be"):
            MineCommand("iron", 2.5)  # type: ignore[arg-type]

    def test_a_string_is_refused_where_a_broker_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            MineCommand("iron").execute("not an object", "ada")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()