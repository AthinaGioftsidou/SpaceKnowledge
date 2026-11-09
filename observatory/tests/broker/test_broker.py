"""Tests for Broker, which owns players and their inventories."""

import unittest
from collections.abc import Callable

from observatory.broker.broker import Broker
from observatory.broker.inventory_entry import InventoryEntry
from observatory.common.messages import Request, Response
from observatory.common.refusal import Refusal
from observatory.transport.channel import InMemoryChannel, UniverseChannel
from observatory.universe.universe import Universe
from observatory.world.item import PlainItem
from observatory.world.room import Room
from observatory.world.world import World


class RecordingChannel(UniverseChannel):
    """A channel that passes everything on, but writes down what it saw.

    `watch` is called while a request is in flight, which is the only moment
    the item is BeingDropped.
    """

    def __init__(self, inner: UniverseChannel) -> None:
        self._inner = inner
        self.requests: list[Request] = []
        self.watch: Callable[[], bool] | None = None
        self.seen: list[bool] = []

    def send(self, request: Request) -> Response:
        self.requests.append(request)
        if self.watch is not None:
            self.seen.append(self.watch())
        return self._inner.send(request)


def a_setup() -> tuple[Broker, RecordingChannel, Room]:
    hall = Room("hall", "Hall", "Cold and tiled.")
    universe = Universe(World({"hall": hall}, "hall"))
    universe.place_player("ada", "hall")
    channel = RecordingChannel(InMemoryChannel(universe))
    broker = Broker(channel)
    broker.add_player("ada")
    broker.give("ada", InventoryEntry("torch", "torch"))
    return broker, channel, hall


class TestPlayers(unittest.TestCase):
    def test_an_empty_player_id_is_refused(self) -> None:
        broker, _, _ = a_setup()
        with self.assertRaises(ValueError):
            broker.add_player("")

    def test_a_duplicate_player_is_refused(self) -> None:
        broker, _, _ = a_setup()
        with self.assertRaises(ValueError):
            broker.add_player("ada")

    def test_giving_to_an_unknown_player_is_refused(self) -> None:
        broker, _, _ = a_setup()
        with self.assertRaises(KeyError):
            broker.give("bob", InventoryEntry("rope", "rope"))


class TestDrop(unittest.TestCase):
    def test_a_successful_drop_moves_the_item_from_inventory_to_the_world(self) -> None:
        broker, _, hall = a_setup()
        self.assertIsNone(broker.drop("ada", "torch"))
        self.assertEqual(0, broker.inventory_of("ada").count())
        self.assertIsNotNone(hall.find_item("torch"))

    def test_an_item_not_carried_is_refused_and_nothing_is_sent(self) -> None:
        broker, channel, hall = a_setup()
        refusal = broker.drop("ada", "lantern")
        self.assertIsInstance(refusal, Refusal)
        self.assertEqual([], channel.requests)
        self.assertEqual(0, hall.item_count())

    def test_an_unknown_player_is_refused_and_nothing_is_sent(self) -> None:
        broker, channel, _ = a_setup()
        refusal = broker.drop("bob", "torch")
        self.assertIsInstance(refusal, Refusal)
        self.assertIn("bob", refusal.describe())
        self.assertEqual([], channel.requests)

    def test_when_the_universe_refuses_the_player_keeps_the_item_and_can_use_it(self) -> None:
        broker, _, hall = a_setup()
        hall.add_item(PlainItem("torch", "torch", "a torch already here"))
        refusal = broker.drop("ada", "torch")
        self.assertIsInstance(refusal, Refusal)
        self.assertEqual(1, broker.inventory_of("ada").count())
        self.assertIsNone(broker.inventory_of("ada").check_usable("torch"))

    def test_the_item_cannot_be_used_while_the_universe_is_deciding(self) -> None:
        broker, channel, _ = a_setup()
        channel.watch = lambda: broker.inventory_of("ada").find("torch").is_usable()
        broker.drop("ada", "torch")
        self.assertEqual([False], channel.seen)

    def test_the_request_names_the_player_the_item_and_the_action(self) -> None:
        broker, channel, _ = a_setup()
        broker.drop("ada", "torch")
        request = channel.requests[0]
        self.assertEqual("add_item", request.action)
        self.assertEqual("ada", request.player_id)
        self.assertEqual("torch", request.item_id)

    def test_every_drop_gets_its_own_op_id(self) -> None:
        broker, channel, _ = a_setup()
        broker.give("ada", InventoryEntry("rope", "rope"))
        broker.drop("ada", "torch")
        broker.drop("ada", "rope")
        self.assertNotEqual(channel.requests[0].op_id, channel.requests[1].op_id)


class TestArgumentTypes(unittest.TestCase):
    def test_a_string_is_refused_where_a_class_is_expected(self) -> None:
        broker, _, _ = a_setup()
        bad = "not an object"
        calls = [
            ("Broker channel", lambda: Broker(bad)),
            ("give entry", lambda: broker.give("ada", bad)),
        ]
        for label, call in calls:
            with self.subTest(label):
                with self.assertRaisesRegex(TypeError, "must be"):
                    call()


if __name__ == "__main__":
    unittest.main()