"""Tests for login lockout and session expiry, through Front."""

import unittest

from spaceknowledge.app.front import Front
from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.broker_server import BrokerServer
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.transport.channel import InMemoryChannel
from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.universe import Universe
from spaceknowledge.users.accounts import AccountRegistry
from spaceknowledge.users.login_throttle import LoginThrottle
from spaceknowledge.users.session_book import SessionBook
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World

PASSWORD = "correct horse"
LOGGER = "spaceknowledge.app.front"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def a_front(test: unittest.TestCase, clock: Clock) -> Front:
    earth = Destination("earth", "Earth", "Home.")
    universe = Universe(World({"earth": earth}, "earth"), Deposits({"earth": {"iron": 10}}))
    server = BrokerServer(Broker(InMemoryChannel(universe)))
    server.start()
    test.addCleanup(server.stop)
    accounts = AccountRegistry(iterations=1)
    accounts.register("ada", PASSWORD)
    accounts.register("bob", PASSWORD)
    throttle = LoginThrottle(clock, max_failures=3, lockout=60.0)
    sessions = SessionBook(clock, lifetime=100.0, idle_timeout=50.0)
    return Front(accounts, sessions, server, "earth", throttle)


def fail(front: Front, name: str = "ada", times: int = 3) -> None:
    for _ in range(times):
        assert isinstance(front.login(name, "wrong password"), Refusal)


class TestLockout(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self.front = a_front(self, self.clock)

    def test_three_wrong_passwords_lock_the_name_even_against_the_right_one(self) -> None:
        fail(self.front)
        refusal = self.front.login("ada", PASSWORD)
        self.assertIsInstance(refusal, Refusal)
        for part in ("paused", "Next:"):
            self.assertIn(part, refusal.describe())

    def test_two_wrong_passwords_do_not_lock(self) -> None:
        fail(self.front, times=2)
        self.assertIsInstance(self.front.login("ada", PASSWORD), str)

    def test_the_right_password_works_again_when_the_lock_runs_out(self) -> None:
        fail(self.front)
        self.clock.now += 59
        self.assertIsInstance(self.front.login("ada", PASSWORD), Refusal)
        self.clock.now += 1
        self.assertIsInstance(self.front.login("ada", PASSWORD), str)

    def test_a_good_login_resets_the_count(self) -> None:
        fail(self.front, times=2)
        self.assertIsInstance(self.front.login("ada", PASSWORD), str)
        fail(self.front, times=2)
        self.assertIsInstance(self.front.login("ada", PASSWORD), str)

    def test_one_players_lock_does_not_affect_another(self) -> None:
        fail(self.front, "ada")
        self.assertIsInstance(self.front.login("bob", PASSWORD), str)

    def test_a_locked_known_name_and_a_locked_unknown_name_look_the_same(self) -> None:
        fail(self.front, "ada")
        fail(self.front, "nobody")
        self.assertEqual(
            self.front.login("ada", PASSWORD).describe(),
            self.front.login("nobody", PASSWORD).describe(),
        )

    def test_the_log_names_the_lock_but_never_a_password(self) -> None:
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            fail(self.front)
            self.front.login("ada", PASSWORD)
        text = "\n".join(logs.output)
        self.assertIn("ada", text)
        self.assertIn("locked", text)
        self.assertNotIn(PASSWORD, text)
        self.assertNotIn("wrong password", text)


class TestSessionExpiry(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self.front = a_front(self, self.clock)
        token = self.front.login("ada", PASSWORD)
        assert isinstance(token, str)
        self.token = token

    def test_a_token_works_while_it_is_fresh_and_used(self) -> None:
        self.clock.now += 40
        self.assertIn("carrying", self.front.submit(self.token, "inventory"))

    def test_a_token_stops_working_after_its_lifetime_even_if_it_is_used(self) -> None:
        self.clock.now += 40
        self.front.submit(self.token, "inventory")
        self.clock.now += 40
        self.front.submit(self.token, "inventory")
        self.clock.now += 21
        self.assertIn("not logged in", self.front.submit(self.token, "inventory"))

    def test_a_token_that_sits_unused_expires(self) -> None:
        self.clock.now += 50
        self.assertIn("not logged in", self.front.submit(self.token, "inventory"))

    def test_logging_in_again_gives_a_fresh_working_token(self) -> None:
        self.clock.now += 200
        token = self.front.login("ada", PASSWORD)
        self.assertIn("carrying", self.front.submit(token, "inventory"))


if __name__ == "__main__":
    unittest.main()