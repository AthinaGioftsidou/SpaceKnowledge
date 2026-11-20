"""Tests for BrokerServer: the Broker on its own thread."""

import threading
import unittest

from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.broker_server import BrokerServer
from spaceknowledge.common.messages import Request, Response
from spaceknowledge.tests.transport.helpers import WAIT, in_thread, started
from spaceknowledge.transport.channel import InMemoryChannel, UniverseChannel
from spaceknowledge.transport.threaded_channel import ThreadedChannel
from spaceknowledge.transport.work_queue import ServerStoppedError
from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.universe import Universe
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World

LOGGER = "spaceknowledge.broker.broker_server"


def an_earth() -> tuple[Universe, Deposits]:
    earth = Destination("earth", "Earth", "Home.")
    deposits = Deposits({"earth": {"iron": 10}})
    universe = Universe(World({"earth": earth}, "earth"), deposits)
    universe.place_player("ada", "earth")
    universe.place_player("bob", "earth")
    return universe, deposits


class RecordingChannel(UniverseChannel):
    """Remembers which thread each request was sent from."""

    def __init__(self, inner: UniverseChannel) -> None:
        self._inner = inner
        self.threads: list[str] = []

    def send(self, request: Request) -> Response:
        self.threads.append(threading.current_thread().name)
        return self._inner.send(request)


class LostChannel(UniverseChannel):
    def send(self, request: Request) -> Response:
        raise ConnectionError("lost")


class FlakyChannel(UniverseChannel):
    """Fails once, with an error nobody planned for."""

    def __init__(self, inner: UniverseChannel) -> None:
        self._inner = inner
        self.fail_next = True

    def send(self, request: Request) -> Response:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("boom")
        return self._inner.send(request)


class GatedChannel(UniverseChannel):
    """Stops inside `send` until the test lets it go."""

    def __init__(self, inner: UniverseChannel) -> None:
        self._inner = inner
        self.entered = threading.Event()
        self.release = threading.Event()

    def send(self, request: Request) -> Response:
        self.entered.set()
        self.release.wait(WAIT)
        return self._inner.send(request)


def serve(test: unittest.TestCase, channel: UniverseChannel) -> tuple[BrokerServer, Broker]:
    """Build a Broker with two players, start its thread, and promise to stop it."""
    broker = Broker(channel)
    broker.add_player("ada")
    broker.add_player("bob")
    server = BrokerServer(broker)
    server.start()
    test.addCleanup(server.stop)
    return server, broker


class TestServing(unittest.TestCase):
    def test_a_typed_line_is_answered_and_the_world_changes(self) -> None:
        universe, deposits = an_earth()
        server, _ = serve(self, InMemoryChannel(universe))
        self.assertEqual("You mine 3 iron.", server.submit("ada", "mine iron 3", WAIT))
        self.assertEqual(7, deposits.available("earth", "iron"))

    def test_the_broker_runs_on_its_own_thread(self) -> None:
        universe, _ = an_earth()
        channel = RecordingChannel(InMemoryChannel(universe))
        server, _ = serve(self, channel)
        server.submit("ada", "mine iron 1", WAIT)
        self.assertEqual(["broker"], channel.threads)
        self.assertTrue(server.is_running())

    def test_many_players_at_once_are_all_answered_by_the_one_thread(self) -> None:
        universe, deposits = an_earth()
        channel = RecordingChannel(InMemoryChannel(universe))
        server, _ = serve(self, channel)
        replies: list[str] = []

        def ask(player: str) -> None:
            replies.append(server.submit(player, "mine iron 1", WAIT))

        callers = [in_thread(lambda p=p: ask(p)) for p in ("ada", "bob", "ada", "bob", "ada")]
        for caller in callers:
            caller.join(WAIT)
        self.assertEqual(["You mine 1 iron."] * 5, replies)
        self.assertEqual(5, deposits.available("earth", "iron"))
        self.assertEqual(["broker"] * 5, channel.threads)

    def test_players_have_separate_inventories(self) -> None:
        universe, _ = an_earth()
        server, _ = serve(self, InMemoryChannel(universe))
        server.submit("ada", "mine iron 3", WAIT)
        self.assertIn("iron 3", server.submit("ada", "inventory", WAIT))
        self.assertEqual("You are carrying nothing.", server.submit("bob", "inventory", WAIT))

    def test_nonsense_gets_a_three_part_refusal(self) -> None:
        universe, _ = an_earth()
        server, _ = serve(self, InMemoryChannel(universe))
        text = server.submit("ada", "juggle", WAIT)
        self.assertIn("Why:", text)
        self.assertIn("Next:", text)

    def test_help_is_answered(self) -> None:
        universe, _ = an_earth()
        server, _ = serve(self, InMemoryChannel(universe))
        self.assertIn("mine", server.submit("ada", "help", WAIT))

    def test_an_unknown_player_is_answered_with_a_refusal_text(self) -> None:
        universe, _ = an_earth()
        server, _ = serve(self, InMemoryChannel(universe))
        self.assertIn("eve", server.submit("eve", "inventory", WAIT))

    def test_every_line_is_logged_by_the_broker_thread(self) -> None:
        universe, _ = an_earth()
        server, _ = serve(self, InMemoryChannel(universe))
        with self.assertLogs(LOGGER, level="INFO") as logs:
            server.submit("ada", "mine iron 1", WAIT)
        self.assertTrue(any("ada" in line and "mine iron 1" in line for line in logs.output))


class TestTheTwoThreadsTogether(unittest.TestCase):
    def test_a_line_crosses_the_broker_thread_then_the_universe_thread(self) -> None:
        universe, deposits = an_earth()
        universe_server = started(self, universe)  # registered first, so stopped last
        server, _ = serve(self, ThreadedChannel(universe_server))
        self.assertEqual("You mine 3 iron.", server.submit("ada", "mine iron 3", WAIT))
        self.assertEqual(7, deposits.available("earth", "iron"))


class TestFailures(unittest.TestCase):
    def test_a_lost_universe_is_explained_and_the_operation_stays_pending(self) -> None:
        server, broker = serve(self, LostChannel())
        text = server.submit("ada", "mine iron 1", WAIT)
        self.assertIn("did not answer", text)
        self.assertIn("Next:", text)
        self.assertEqual(1, broker.pending_count())
        self.assertTrue(server.is_running())

    def test_an_unexpected_error_reaches_the_caller_and_the_thread_survives(self) -> None:
        universe, _ = an_earth()
        server, _ = serve(self, FlakyChannel(InMemoryChannel(universe)))
        with self.assertLogs(LOGGER, level="ERROR") as logs:
            with self.assertRaisesRegex(RuntimeError, "boom"):
                server.submit("ada", "mine iron 1", WAIT)
        self.assertIn("ada", logs.output[0])
        self.assertTrue(server.is_running())
        self.assertEqual("You mine 1 iron.", server.submit("ada", "mine iron 1", WAIT))

    def test_an_unanswered_line_times_out(self) -> None:
        universe, _ = an_earth()
        gate = GatedChannel(InMemoryChannel(universe))
        server, _ = serve(self, gate)
        self.addCleanup(gate.release.set)  # runs before the stop above
        with self.assertRaises(TimeoutError):
            server.submit("ada", "mine iron 1", 0.05)


class TestLifecycle(unittest.TestCase):
    def a_server(self) -> BrokerServer:
        universe, _ = an_earth()
        return BrokerServer(Broker(InMemoryChannel(universe)))

    def test_stopping_ends_the_thread_and_twice_is_harmless(self) -> None:
        server = self.a_server()
        server.start()
        server.stop()
        server.stop()
        self.assertFalse(server.is_running())

    def test_a_line_after_the_stop_is_refused(self) -> None:
        server = self.a_server()
        server.start()
        server.stop()
        with self.assertRaises(ServerStoppedError):
            server.submit("ada", "look", WAIT)

    def test_a_line_before_the_start_is_refused(self) -> None:
        with self.assertRaises(ServerStoppedError):
            self.a_server().submit("ada", "look", WAIT)

    def test_it_can_only_be_started_once(self) -> None:
        server = self.a_server()
        server.start()
        self.addCleanup(server.stop)
        with self.assertRaises(RuntimeError):
            server.start()

    def test_a_stopped_server_cannot_be_started_again(self) -> None:
        server = self.a_server()
        server.start()
        server.stop()
        with self.assertRaises(RuntimeError):
            server.start()

    def test_bad_arguments_are_refused(self) -> None:
        universe, _ = an_earth()
        broker = Broker(InMemoryChannel(universe))
        with self.assertRaisesRegex(TypeError, "must be"):
            BrokerServer("broker")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            BrokerServer(broker, "parser")  # type: ignore[arg-type]
        server = self.a_server()
        server.start()
        self.addCleanup(server.stop)
        with self.assertRaises(ValueError):
            server.submit("", "look", WAIT)
        with self.assertRaisesRegex(TypeError, "must be"):
            server.submit("ada", 5, WAIT)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()