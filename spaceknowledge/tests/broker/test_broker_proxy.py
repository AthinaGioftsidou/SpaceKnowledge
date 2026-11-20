"""Tests for the whole drop and pick cycle through the proxies."""

import unittest
from collections.abc import Callable

from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.inventory_entry import InventoryEntry
from spaceknowledge.broker.inventory_repository import InMemoryInventoryRepository
from spaceknowledge.broker.item_proxy import ItemProxy
from spaceknowledge.common.messages import Request, Response
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.transport.channel import InMemoryChannel, UniverseChannel
from spaceknowledge.universe.universe import Universe
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World


class SpyChannel(UniverseChannel):
    """Passes requests on, records their actions, can watch during a pick,
    and can lose the answer to a pick after the Universe has acted."""

    def __init__(self, inner: UniverseChannel) -> None:
        self._inner = inner
        self.actions: list[str] = []
        self.watch: Callable[[], object] | None = None
        self.seen: list[object] = []
        self.lose_pick_answers = False

    def send(self, request: Request) -> Response:
        self.actions.append(request.action)
        if request.action == "pick" and self.watch is not None:
            self.seen.append(self.watch())
        response = self._inner.send(request)
        if request.action == "pick" and self.lose_pick_answers:
            raise ConnectionError("answer lost")
        return response


class Setup:
    def __init__(self) -> None:
        self.hall = Destination("hall", "Hall", "Cold and tiled.")
        self.universe = Universe(World({"hall": self.hall}, "hall"))
        self.universe.place_player("ada", "hall")
        self.universe.place_player("bob", "hall")
        self.repository = InMemoryInventoryRepository()
        self.channel = SpyChannel(InMemoryChannel(self.universe))
        self.broker = Broker(self.channel, self.repository)
        self.broker.add_player("ada")
        self.broker.add_player("bob")
        self.broker.give("ada", InventoryEntry("torch", "torch"))


class TestTheWholeCycle(unittest.TestCase):
    def setUp(self) -> None:
        self.s = Setup()

    def test_what_one_player_drops_another_can_pick_up(self) -> None:
        self.assertIsNone(self.s.broker.drop("ada", "torch"))
        self.assertIsNone(self.s.broker.pick("bob", "torch"))
        entry = self.s.broker.inventory_of("bob").find("torch")
        self.assertEqual(("owned", "broker", True),
                         (entry.state(), entry.holder(), entry.is_usable()))
        self.assertIsNone(self.s.hall.find_item("torch"))
        self.assertEqual(0, self.s.broker.inventory_of("ada").count())

    def test_look_gives_proxies_and_changes_nothing(self) -> None:
        self.s.broker.drop("ada", "torch")
        proxies = self.s.broker.look("bob")
        self.assertEqual(["torch"], [p.name for p in proxies])
        self.assertIsInstance(proxies[0], ItemProxy)
        self.assertEqual(0, self.s.broker.inventory_of("bob").count())
        self.assertIsNotNone(self.s.hall.find_item("torch"))

    def test_the_proxy_is_in_flight_while_the_universe_decides_and_gone_after(self) -> None:
        self.s.broker.drop("ada", "torch")
        self.s.channel.watch = self.s.broker.picks_in_flight
        self.s.broker.pick("bob", "torch")
        self.assertEqual([["flight"]], self.s.channel.seen)
        self.assertEqual([], self.s.broker.picks_in_flight())

    def test_a_player_who_already_carries_that_item_is_refused_and_nothing_is_sent(self) -> None:
        self.s.broker.drop("ada", "torch")
        self.s.broker.give("bob", InventoryEntry("torch", "torch"))
        self.s.channel.actions.clear()
        refusal = self.s.broker.pick("bob", "torch")
        self.assertIn("already carry", refusal.describe())
        self.assertNotIn("pick", self.s.channel.actions)
        self.assertIsNotNone(self.s.hall.find_item("torch"))

    def test_something_that_is_not_there_is_refused_with_advice(self) -> None:
        refusal = self.s.broker.pick("bob", "rope")
        self.assertIn("type look", refusal.describe())

    def test_a_stranger_cannot_look_or_pick(self) -> None:
        self.assertIsInstance(self.s.broker.look("eve"), Refusal)
        self.assertIsInstance(self.s.broker.pick("eve", "torch"), Refusal)

    def test_a_stale_proxy_is_refused_by_the_universe_and_goes_back_on_the_ground(self) -> None:
        self.s.broker.drop("ada", "torch")
        proxies = self.s.broker.look("bob")
        self.assertIsNone(self.s.broker.pick("ada", "torch"))  # ada was first
        refusal = proxies[0].pick("bob")
        self.assertIsNotNone(refusal)
        self.assertEqual("owned", proxies[0].state())
        self.assertEqual(0, self.s.broker.inventory_of("bob").count())
        self.assertEqual([], self.s.broker.picks_in_flight())

    def test_a_picked_item_survives_a_broker_restart(self) -> None:
        self.s.broker.drop("ada", "torch")
        self.s.broker.pick("bob", "torch")
        again = Broker(InMemoryChannel(self.s.universe), self.s.repository)
        self.assertIsNotNone(again.inventory_of("bob").find("torch"))


class TestACrashDuringAPick(unittest.TestCase):
    def test_a_pick_whose_answer_was_lost_is_finished_once_by_recovery(self) -> None:
        s = Setup()
        s.broker.drop("ada", "torch")
        s.channel.lose_pick_answers = True
        with self.assertRaises(ConnectionError):
            s.broker.pick("bob", "torch")
        self.assertEqual(1, s.broker.pending_count())
        self.assertIsNone(s.hall.find_item("torch"))  # the Universe already did it

        again = Broker(InMemoryChannel(s.universe), s.repository)
        self.assertEqual(1, again.recover())
        self.assertIsNotNone(again.inventory_of("bob").find("torch"))
        self.assertEqual(0, again.pending_count())
        self.assertEqual([], again.picks_in_flight())


if __name__ == "__main__":
    unittest.main()