"""Tests for Front: login, then lines that carry a token and nothing else."""

import unittest

from spaceknowledge.app.front import Front
from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.broker_server import BrokerServer
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.transport.channel import InMemoryChannel
from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.universe import Universe
from spaceknowledge.users.accounts import AccountRegistry
from spaceknowledge.users.session_book import SessionBook
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World

PASSWORD = "correct horse"
LOGGER = "spaceknowledge.app.front"


def a_front(test: unittest.TestCase) -> tuple[Front, Universe]:
    earth = Destination("earth", "Earth", "Home.")
    universe = Universe(World({"earth": earth}, "earth"), Deposits({"earth": {"iron": 10}}))
    universe.place_player("ada", "earth")
    broker = Broker(InMemoryChannel(universe))
    broker.add_player("ada")
    server = BrokerServer(broker)
    server.start()
    test.addCleanup(server.stop)
    accounts = AccountRegistry(iterations=1)
    accounts.register("ada", PASSWORD)
    accounts.register("bob", PASSWORD)  # has an account, but no Broker player
    return Front(accounts, SessionBook(), server), universe


def token_of(result: object) -> str:
    assert isinstance(result, str), result
    return result


class TestLogin(unittest.TestCase):
    def test_a_good_login_gives_a_token_that_plays(self) -> None:
        front, _ = a_front(self)
        token = token_of(front.login("ada", PASSWORD))
        self.assertEqual("You mine 3 iron.", front.submit(token, "mine iron 3"))

    def test_a_wrong_password_gives_a_refusal_and_no_token(self) -> None:
        front, _ = a_front(self)
        self.assertIsInstance(front.login("ada", "wrong password"), Refusal)

    def test_the_log_names_a_failed_login_but_never_its_password(self) -> None:
        front, _ = a_front(self)
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            front.login("ada", "wrong password")
        text = "\n".join(logs.output)
        self.assertIn("ada", text)
        self.assertNotIn("wrong password", text)


class TestTheTokenIsTheIdentity(unittest.TestCase):
    def test_a_line_with_no_valid_token_is_refused_and_changes_nothing(self) -> None:
        front, universe = a_front(self)
        text = front.submit("not-a-token", "mine iron 3")
        for part in ("not logged in", "Next:"):
            self.assertIn(part, text)
        self.assertEqual(10, universe._deposits.available("earth", "iron"))

    def test_a_player_can_only_act_as_themselves(self) -> None:
        front, _ = a_front(self)
        bob = token_of(front.login("bob", PASSWORD))
        # bob has no Broker player, and nothing he types can make him ada.
        self.assertIn("bob", front.submit(bob, "inventory"))

    def test_logging_out_ends_the_session(self) -> None:
        front, _ = a_front(self)
        token = token_of(front.login("ada", PASSWORD))
        self.assertTrue(front.logout(token))
        self.assertIn("not logged in", front.submit(token, "inventory"))
        self.assertFalse(front.logout(token))

    def test_two_sessions_of_one_player_both_work(self) -> None:
        front, _ = a_front(self)
        first = token_of(front.login("ada", PASSWORD))
        second = token_of(front.login("ada", PASSWORD))
        front.submit(first, "mine iron 1")
        self.assertIn("iron 1", front.submit(second, "inventory"))

    def test_command_gives_a_refusal_object_for_a_bad_token_and_text_for_a_good_one(self) -> None:
        front, _ = a_front(self)
        self.assertIsInstance(front.command("nope", "look"), Refusal)
        token = token_of(front.login("ada", PASSWORD))
        self.assertIsInstance(front.command(token, "inventory"), str)


class TestArguments(unittest.TestCase):
    def test_bad_arguments_are_refused(self) -> None:
        front, _ = a_front(self)
        with self.assertRaisesRegex(TypeError, "must be"):
            Front("accounts", SessionBook(), BrokerServer.__new__(BrokerServer))  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            front.submit(5, "look")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            front.login("ada", 5)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()