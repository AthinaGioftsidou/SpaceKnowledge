"""Tests for BrokerServer.join: joining happens on the Broker thread."""

import unittest

from observatory.broker.broker import Broker
from observatory.broker.broker_server import BrokerServer
from observatory.common.messages import Request, Response
from observatory.tests.transport.helpers import WAIT
from observatory.transport.channel import InMemoryChannel, UniverseChannel
from observatory.transport.work_queue import ServerStoppedError
from observatory.universe.universe import Universe
from observatory.world.room import Room
from observatory.world.world import World


class LostChannel(UniverseChannel):
    def send(self, request: Request) -> Response:
        raise ConnectionError("lost")


def a_universe() -> Universe:
    return Universe(World({"earth": Room("earth", "Earth", "Home.")}, "earth"))


def started(test: unittest.TestCase, channel: UniverseChannel) -> BrokerServer:
    server = BrokerServer(Broker(channel))
    server.start()
    test.addCleanup(server.stop)
    return server


class TestJoin(unittest.TestCase):
    def test_a_join_succeeds_with_an_empty_reply_and_the_player_can_then_play(self) -> None:
        server = started(self, InMemoryChannel(a_universe()))
        self.assertEqual("", server.join("ada", "earth", WAIT))
        self.assertEqual("You are carrying: torch", server.submit("ada", "inventory", WAIT))

    def test_an_unknown_destination_gives_a_refusal_text(self) -> None:
        server = started(self, InMemoryChannel(a_universe()))
        text = server.join("ada", "nowhere", WAIT)
        self.assertIn("Next:", text)

    def test_a_lost_universe_is_explained_and_the_thread_survives(self) -> None:
        server = started(self, LostChannel())
        self.assertIn("did not answer", server.join("ada", "earth", WAIT))
        self.assertTrue(server.is_running())

    def test_a_join_before_the_start_is_refused(self) -> None:
        server = BrokerServer(Broker(InMemoryChannel(a_universe())))
        with self.assertRaises(ServerStoppedError):
            server.join("ada", "earth", WAIT)

    def test_empty_arguments_are_refused(self) -> None:
        server = started(self, InMemoryChannel(a_universe()))
        with self.assertRaises(ValueError):
            server.join("", "earth", WAIT)
        with self.assertRaises(ValueError):
            server.join("ada", "", WAIT)


if __name__ == "__main__":
    unittest.main()