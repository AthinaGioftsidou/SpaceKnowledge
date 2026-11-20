"""Tests for ThreadedChannel, and for the Broker working over it."""

import unittest

from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.inventory_entry import InventoryEntry
from spaceknowledge.broker.inventory_repository import InMemoryInventoryRepository
from spaceknowledge.tests.transport.helpers import (
    WAIT,
    GatedUniverse,
    a_universe,
    add,
    in_thread,
    started,
)
from spaceknowledge.transport.call_queue import ServerStoppedError
from spaceknowledge.transport.channel import UniverseChannel
from spaceknowledge.transport.threaded_channel import ThreadedChannel
from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.universe import Universe
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World


def an_earth() -> tuple[Universe, Deposits]:
    earth = Destination("earth", "Earth", "Home.")
    deposits = Deposits({"earth": {"iron": 10}})
    universe = Universe(World({"earth": earth}, "earth"), deposits)
    universe.place_player("ada", "earth")
    return universe, deposits


class TestThreadedChannel(unittest.TestCase):
    def test_it_is_a_universe_channel(self) -> None:
        universe, _ = a_universe(Universe)
        channel = ThreadedChannel(started(self, universe))
        self.assertIsInstance(channel, UniverseChannel)

    def test_a_request_reaches_the_universe_thread_and_the_answer_returns(self) -> None:
        universe, hall = a_universe(Universe)
        channel = ThreadedChannel(started(self, universe))
        response = channel.send(add())
        self.assertTrue(response.ok)
        self.assertEqual("op1", response.op_id)
        self.assertIsNotNone(hall.find_item("torch"))

    def test_an_unanswered_request_times_out(self) -> None:
        universe, _ = a_universe(GatedUniverse)
        server = started(self, universe)
        self.addCleanup(universe.release.set)  # runs before the stop above
        with self.assertRaises(TimeoutError):
            ThreadedChannel(server, timeout=0.05).send(add())

    def test_a_stopped_server_refuses(self) -> None:
        universe, _ = a_universe(Universe)
        server = started(self, universe)
        server.stop()
        with self.assertRaises(ServerStoppedError):
            ThreadedChannel(server).send(add())

    def test_bad_arguments_are_refused(self) -> None:
        universe, _ = a_universe(Universe)
        server = started(self, universe)
        with self.assertRaisesRegex(TypeError, "must be"):
            ThreadedChannel("server")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            ThreadedChannel(server).send("request")  # type: ignore[arg-type]
        for timeout in (0, -1):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    ThreadedChannel(server, timeout=timeout)


class TestTheBrokerOverThreads(unittest.TestCase):
    def test_the_item_is_unusable_while_the_universe_thread_is_working(self) -> None:
        # The professor's example, for real: the Broker's thread is waiting,
        # the Universe thread is busy, and the torch is neither yours nor gone.
        universe, hall = a_universe(GatedUniverse)
        server = started(self, universe)
        self.addCleanup(universe.release.set)  # runs before the stop above
        broker = Broker(ThreadedChannel(server))
        broker.add_player("ada")
        broker.give("ada", InventoryEntry("torch", "torch"))
        outcome: list[object] = []
        player = in_thread(lambda: outcome.append(broker.drop("ada", "torch")))

        self.assertTrue(universe.entered.wait(WAIT))
        self.assertFalse(broker.inventory_of("ada").find("torch").is_usable())

        universe.release.set()
        player.join(WAIT)
        self.assertEqual([None], outcome)
        self.assertEqual(0, broker.inventory_of("ada").count())
        self.assertIsNotNone(hall.find_item("torch"))

    def test_mining_works_across_the_two_threads(self) -> None:
        universe, deposits = an_earth()
        broker = Broker(ThreadedChannel(started(self, universe)))
        broker.add_player("ada")
        self.assertIsNone(broker.mine("ada", "iron", 3))
        self.assertEqual(3, broker.resources_of("ada").amount_of("iron"))
        self.assertEqual(7, deposits.available("earth", "iron"))

    def test_a_refusal_crosses_the_threads_with_its_three_parts(self) -> None:
        universe, deposits = an_earth()
        broker = Broker(ThreadedChannel(started(self, universe)))
        broker.add_player("ada")
        refusal = broker.mine("ada", "iron", 11)
        self.assertIn("only 10", refusal.describe())
        self.assertTrue(broker.resources_of("ada").is_empty())
        self.assertEqual(10, deposits.available("earth", "iron"))

    def test_a_universe_thread_that_stopped_mid_game_is_recovered_from(self) -> None:
        universe, deposits = an_earth()
        repository = InMemoryInventoryRepository()
        first = started(self, universe)
        broker = Broker(ThreadedChannel(first), repository)
        broker.add_player("ada")
        first.stop()
        with self.assertRaises(ServerStoppedError):
            broker.mine("ada", "iron", 3)
        self.assertEqual(1, broker.pending_count())

        second = started(self, universe)
        again = Broker(ThreadedChannel(second), repository)
        self.assertEqual(1, again.recover())
        self.assertEqual(3, again.resources_of("ada").amount_of("iron"))
        self.assertEqual(7, deposits.available("earth", "iron"))


if __name__ == "__main__":
    unittest.main()