"""Tests for Front with a start destination: register, login, and joining."""

import unittest

from observatory.app.front import Front
from observatory.broker.broker import Broker
from observatory.broker.broker_server import BrokerServer
from observatory.common.refusal import Refusal
from observatory.transport.channel import InMemoryChannel
from observatory.universe.deposits import Deposits
from observatory.universe.universe import Universe
from observatory.users.accounts import AccountRegistry
from observatory.users.session_book import SessionBook
from observatory.world.room import Room
from observatory.world.world import World

PASSWORD = "correct horse"


def a_front(test: unittest.TestCase, start: str | None = "earth") -> Front:
    earth = Room("earth", "Earth", "Home.")
    universe = Universe(World({"earth": earth}, "earth"), Deposits({"earth": {"iron": 10}}))
    server = BrokerServer(Broker(InMemoryChannel(universe)))
    server.start()
    test.addCleanup(server.stop)
    return Front(AccountRegistry(iterations=1), SessionBook(), server, start)


class TestRegister(unittest.TestCase):
    def test_a_registered_player_can_log_in_and_play(self) -> None:
        front = a_front(self)
        self.assertIsNone(front.register("ada", PASSWORD))
        token = front.login("ada", PASSWORD)
        self.assertEqual("You mine 2 iron.", front.submit(token, "mine iron 2"))

    def test_a_taken_name_or_a_bad_password_is_refused(self) -> None:
        front = a_front(self)
        front.register("ada", PASSWORD)
        self.assertIn("taken", front.register("ada", PASSWORD).describe())
        self.assertIsInstance(front.register("bob", "short"), Refusal)


class TestLoginJoins(unittest.TestCase):
    def test_a_login_places_the_player_and_gives_the_torch(self) -> None:
        front = a_front(self)
        front.register("ada", PASSWORD)
        token = front.login("ada", PASSWORD)
        self.assertEqual("You are carrying: torch", front.submit(token, "inventory"))

    def test_a_player_who_cannot_be_placed_gets_a_refusal_and_no_token(self) -> None:
        front = a_front(self, start="nowhere")
        front.register("ada", PASSWORD)
        refusal = front.login("ada", PASSWORD)
        self.assertIsInstance(refusal, Refusal)
        self.assertIn("Next:", refusal.describe())

    def test_a_wrong_password_never_reaches_the_join(self) -> None:
        front = a_front(self)
        front.register("ada", PASSWORD)
        self.assertIsInstance(front.login("ada", "wrong password"), Refusal)

    def test_an_empty_start_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            a_front(self, start="")


if __name__ == "__main__":
    unittest.main() 