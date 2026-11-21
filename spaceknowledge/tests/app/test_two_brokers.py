"""Scenario tests: two Broker programs, one Universe, real sockets."""

import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from spaceknowledge.app.broker_program import build_broker
from spaceknowledge.app.game import Game
from spaceknowledge.app.keys import read_existing_key
from spaceknowledge.app.paths import ACCOUNTS_FILE, PLAYERS_FILE, SERVER_KEY_FILE, MAILBOX_FILE
from spaceknowledge.app.universe_program import start_universe
from spaceknowledge.broker.inventory_repository import JsonInventoryRepository
from spaceknowledge.common.messages import Request
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.tests.transport.helpers import WAIT, in_thread
from spaceknowledge.transport.server_auth import ServerIdentity, load_or_create_key
from spaceknowledge.transport.socket_channel import SocketChannel
from spaceknowledge.users.account_repository import JsonAccountRepository
from spaceknowledge.users.accounts import AccountRegistry

SPACE_FILE = Path(__file__).resolve().parents[3] / "data" / "space.json"
PASSWORD = "correct horse"
THREADS = {"broker", "universe-listener"}


def thread_names() -> set[str]:
    return {thread.name for thread in threading.enumerate()}


class TestTwoBrokers(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.universe_dir = self.root / "universe"
        self.process = start_universe(
            SPACE_FILE, self.universe_dir, peers=("broker-1", "broker-2"))
        self.addCleanup(lambda: self.process.close())  # the current one, even after a restart

    def broker(self, name: str, key_file: Path | None = None, timeout: float = 5.0) -> Game:
        host, port = self.process.address
        game = build_broker(
            self.root / name, key_file or self.universe_dir / SERVER_KEY_FILE,
            host, port, "earth", name, iterations=1, timeout=timeout)
        self.addCleanup(game.close)
        return game

    def signed_in(self, game: Game, name: str) -> str:
        self.assertIsNone(game.front.register(name, PASSWORD))
        token = game.front.login(name, PASSWORD)
        assert isinstance(token, str), token
        return token

    def test_a_broker_reports_how_many_operations_it_finished_at_start(self) -> None:
        host, port = self.process.address
        key = read_existing_key(self.universe_dir / SERVER_KEY_FILE)
        channel = SocketChannel(host, port, ServerIdentity("broker-1", key), 5.0)
        self.addCleanup(channel.close)
        channel.send(Request("j1", "join", "ada", "earth"))
        JsonInventoryRepository(self.root / "broker-1" / PLAYERS_FILE).save(
            {"ada": [("torch-1", "torch")]}, None,
            [Request("old-op1", "mine", "ada", "iron", 3)])
        one = self.broker("broker-1")
        one.admin.request_code("root")
        mailbox = (self.root / "broker-1" / MAILBOX_FILE).read_text(encoding="utf-8")
        token = one.admin.login("root", mailbox.split("Code: ")[1][:8])
        self.assertEqual(1, one.admin.stats(token)["recovered_at_start"])

    def test_players_on_different_brokers_share_one_stock(self) -> None:
        one, two = self.broker("broker-1"), self.broker("broker-2")
        ada, bob = self.signed_in(one, "ada"), self.signed_in(two, "bob")
        self.assertEqual("You mine 5 iron.", one.front.submit(ada, "mine iron 5"))
        self.assertEqual("You mine 5 iron.", two.front.submit(bob, "mine iron 5"))
        self.assertEqual("You mine 490 iron.", one.front.submit(ada, "mine iron 490"))
        self.assertIn("no iron to mine", two.front.submit(bob, "mine iron 1"))

    def test_an_item_dropped_through_one_broker_is_picked_up_through_the_other(self) -> None:
        one, two = self.broker("broker-1"), self.broker("broker-2")
        ada, bob = self.signed_in(one, "ada"), self.signed_in(two, "bob")
        self.assertEqual("You drop the torch.", one.front.submit(ada, "drop torch"))
        self.assertEqual("On the ground here: torch", two.front.submit(bob, "look"))
        self.assertEqual("You pick up the torch.", two.front.submit(bob, "pick torch"))
        self.assertEqual("You are carrying: torch, torch", two.front.submit(bob, "inventory"))
        self.assertEqual("Nothing lies on the ground here.", one.front.submit(ada, "look"))

    def test_two_players_picking_at_once_on_different_brokers_only_one_gets_it(self) -> None:
        one, two = self.broker("broker-1"), self.broker("broker-2")
        ada = self.signed_in(one, "ada")
        bob, cat = self.signed_in(two, "bob"), self.signed_in(one, "cat")
        one.front.submit(ada, "drop torch")
        replies: list[str] = []

        def grab(game: Game, token: str) -> None:
            replies.append(game.front.submit(token, "pick torch"))

        workers = [in_thread(lambda: grab(two, bob)), in_thread(lambda: grab(one, cat))]
        for worker in workers:
            worker.join(WAIT)
        self.assertEqual(2, len(replies))
        self.assertEqual(1, replies.count("You pick up the torch."))

    def test_everything_survives_restarting_the_universe_and_both_brokers(self) -> None:
        one, two = self.broker("broker-1"), self.broker("broker-2")
        ada = self.signed_in(one, "ada")
        one.front.submit(ada, "mine iron 3")
        self.signed_in(two, "bob")
        one.close()
        two.close()
        self.process.close()

        self.process = start_universe(
            SPACE_FILE, self.universe_dir, peers=("broker-1", "broker-2"))
        one, two = self.broker("broker-1"), self.broker("broker-2")
        ada = one.front.login("ada", PASSWORD)
        bob = two.front.login("bob", PASSWORD)
        self.assertEqual("You are carrying: torch\nResources: iron 3",
                         one.front.submit(ada, "inventory"))
        self.assertEqual("You mine 497 iron.", two.front.submit(bob, "mine iron 497"))
        self.assertIn("no iron to mine", two.front.submit(bob, "mine iron 1"))

    def test_an_operation_left_unfinished_by_a_broker_is_finished_across_the_socket(self) -> None:
        host, port = self.process.address
        key = read_existing_key(self.universe_dir / SERVER_KEY_FILE)
        channel = SocketChannel(host, port, ServerIdentity("broker-1", key), 5.0)
        self.addCleanup(channel.close)
        channel.send(Request("j1", "join", "ada", "earth"))
        AccountRegistry(JsonAccountRepository(self.root / "broker-1" / ACCOUNTS_FILE), 1
                        ).register("ada", PASSWORD)
        JsonInventoryRepository(self.root / "broker-1" / PLAYERS_FILE).save(
            {"ada": [("torch-1", "torch")]}, None,
            [Request("old-op1", "mine", "ada", "iron", 3)])

        one, two = self.broker("broker-1"), self.broker("broker-2")
        ada = one.front.login("ada", PASSWORD)
        self.assertEqual("You are carrying: torch\nResources: iron 3",
                         one.front.submit(ada, "inventory"))
        bob = self.signed_in(two, "bob")
        self.assertEqual("You mine 497 iron.", two.front.submit(bob, "mine iron 497"))

    def test_a_broker_with_the_wrong_key_cannot_place_players(self) -> None:
        other = self.root / "other.key"
        load_or_create_key(other)
        game = self.broker("broker-1", key_file=other)
        self.assertIsNone(game.front.register("ada", PASSWORD))
        self.assertIsInstance(game.front.login("ada", PASSWORD), Refusal)
        self.assertIsNone(self.process.universe.location_of("ada"))
        self.assertEqual(0, self.process.universe.answer_count())

    def test_a_broker_that_is_not_on_the_allowed_list_cannot_place_players(self) -> None:
        game = self.broker("broker-3")
        self.assertIsNone(game.front.register("ada", PASSWORD))
        self.assertIsInstance(game.front.login("ada", PASSWORD), Refusal)
        self.assertIsNone(self.process.universe.location_of("ada"))

    def test_when_the_universe_is_down_a_login_is_refused_not_a_crash(self) -> None:
        game = self.broker("broker-1", timeout=1.0)
        self.assertIsNone(game.front.register("ada", PASSWORD))
        self.process.close()
        refusal = game.front.login("ada", PASSWORD)
        self.assertIsInstance(refusal, Refusal)
        self.assertIn("Next:", refusal.describe())

    def test_closing_everything_leaves_no_thread_behind(self) -> None:
        one, two = self.broker("broker-1"), self.broker("broker-2")
        self.signed_in(one, "ada")
        self.signed_in(two, "bob")
        one.close()
        two.close()
        self.process.close()
        self.assertFalse(THREADS & thread_names())

    def test_a_missing_key_file_is_refused_before_anything_starts(self) -> None:
        with self.assertRaises(ValueError):
            self.broker("broker-1", key_file=self.root / "nowhere.key")
        self.assertNotIn("broker", thread_names())

    def test_bad_arguments_are_refused(self) -> None:
        host, port = self.process.address
        key_file = self.universe_dir / SERVER_KEY_FILE
        with self.assertRaisesRegex(TypeError, "must be"):
            build_broker("state", key_file, host, port, "earth", "broker-1")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            build_broker(self.root, "key", host, port, "earth", "broker-1")  # type: ignore[arg-type]
        for name in ("Bad Name", "../x", "universe", ""):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    build_broker(self.root / "x", key_file, host, port, "earth", name)


if __name__ == "__main__":
    unittest.main()