"""Tests for the numbers a BrokerServer reports: queue depth, pending, latency."""

import time
import unittest

from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.broker_server import BrokerServer
from spaceknowledge.broker.metrics import BrokerMetrics
from spaceknowledge.common.messages import Request, Response
from spaceknowledge.tests.transport.helpers import WAIT, in_thread
from spaceknowledge.transport.channel import InMemoryChannel, UniverseChannel
from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.universe import Universe
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World

LOGGER = "spaceknowledge.broker.broker_server"


class GatedChannel(UniverseChannel):
    """Stops inside `send` until the test lets it go."""

    def __init__(self, inner: UniverseChannel) -> None:
        import threading
        self._inner = inner
        self.entered = threading.Event()
        self.release = threading.Event()

    def send(self, request: Request) -> Response:
        self.entered.set()
        self.release.wait(WAIT)
        return self._inner.send(request)


class LostChannel(UniverseChannel):
    def send(self, request: Request) -> Response:
        raise ConnectionError("lost")


class FlakyChannel(UniverseChannel):
    def send(self, request: Request) -> Response:
        raise RuntimeError("boom")


def an_earth() -> Universe:
    earth = Destination("earth", "Earth", "Home.")
    universe = Universe(World({"earth": earth}, "earth"), Deposits({"earth": {"iron": 100}}))
    universe.place_player("ada", "earth")
    return universe


def started(test: unittest.TestCase, channel: UniverseChannel,
            **kwargs) -> BrokerServer:  # type: ignore[no-untyped-def]
    broker = Broker(channel)
    broker.add_player("ada")
    server = BrokerServer(broker, **kwargs)
    server.start()
    test.addCleanup(server.stop)
    return server


class TestStats(unittest.TestCase):
    def test_a_fresh_server_reports_an_idle_broker(self) -> None:
        stats = started(self, InMemoryChannel(an_earth())).stats()
        self.assertEqual((0, True, 0), (stats["queue_depth"], stats["broker_thread_running"],
                                        stats["requests_served"]))

    def test_every_served_line_is_counted_and_timed_by_the_clock_given(self) -> None:
        times = iter([0.0, 0.010, 1.0, 1.030])
        server = started(self, InMemoryChannel(an_earth()), clock=lambda: next(times))
        server.submit("ada", "inventory", WAIT)
        server.submit("ada", "look", WAIT)
        stats = server.stats()
        self.assertEqual(2, stats["requests_served"])
        self.assertEqual({"count": 2, "mean": 20.0, "max": 30.0, "p95": 30.0}, stats["latency_ms"])

    def test_the_queue_depth_shows_lines_waiting_behind_a_slow_one(self) -> None:
        gate = GatedChannel(InMemoryChannel(an_earth()))
        self.addCleanup(gate.release.set)  # runs before the server stops
        server = started(self, gate)
        threads = [in_thread(lambda: server.submit("ada", "mine iron 1", WAIT))]
        self.assertTrue(gate.entered.wait(WAIT))
        threads += [in_thread(lambda: server.submit("ada", "inventory", WAIT)) for _ in range(2)]
        deadline = time.monotonic() + WAIT
        while server.stats()["queue_depth"] < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(2, server.stats()["queue_depth"])
        gate.release.set()
        for thread in threads:
            thread.join(WAIT)
        stats = server.stats()
        self.assertEqual((0, 3), (stats["queue_depth"], stats["requests_served"]))

    def test_a_lost_connection_is_counted_and_leaves_one_operation_pending(self) -> None:
        server = started(self, LostChannel())
        server.submit("ada", "mine iron 1", WAIT)
        stats = server.stats()
        self.assertEqual((1, 1, 0), (stats["requests_lost_connection"],
                                     stats["pending_operations"], stats["requests_served"]))

    def test_an_unexpected_error_is_counted_as_failed(self) -> None:
        server = started(self, FlakyChannel())
        with self.assertLogs(LOGGER, level="ERROR"):
            with self.assertRaises(RuntimeError):
                server.submit("ada", "mine iron 1", WAIT)
        self.assertEqual(1, server.stats()["requests_failed"])

    def test_a_shared_metrics_object_is_the_one_reported(self) -> None:
        metrics = BrokerMetrics()
        metrics.set_recovered(4)
        server = started(self, InMemoryChannel(an_earth()), metrics=metrics)
        self.assertEqual(4, server.stats()["recovered_at_start"])

    def test_bad_arguments_are_refused(self) -> None:
        broker = Broker(InMemoryChannel(an_earth()))
        with self.assertRaisesRegex(TypeError, "must be"):
            BrokerServer(broker, None, "metrics")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()