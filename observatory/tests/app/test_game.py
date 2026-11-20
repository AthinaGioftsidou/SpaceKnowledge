"""Tests for build_game: the whole game, with both threads."""

import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from observatory.app.game import Game, build_game
from observatory.app.paths import ACCOUNTS_FILE, PLAYERS_FILE, SERVER_KEY_FILE, UNIVERSE_FILE
from observatory.broker.inventory_repository import CorruptStoreError, JsonInventoryRepository
from observatory.common.messages import Request
from observatory.tests.transport.helpers import WAIT
from observatory.transport.server_auth import CorruptKeyError
from observatory.universe.universe_repository import JsonUniverseRepository, UniverseState
from observatory.users.account_repository import JsonAccountRepository
from observatory.users.accounts import AccountRegistry

SPACE_FILE = Path(__file__).resolve().parents[3] / "data" / "space.json"
PASSWORD = "correct horse"
THREADS = {"broker", "universe"}


def thread_names() -> set[str]:
    return {thread.name for thread in threading.enumerate()}


class TestGame(unittest.TestCase):
    def setUp(self) -> None:
        self.state = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state)

    def start(self) -> Game:
        game = build_game(SPACE_FILE, self.state, iterations=1)
        self.addCleanup(game.close)
        return game

    def signed_in(self, game: Game, name: str) -> str:
        self.assertIsNone(game.front.register(name, PASSWORD))
        token = game.front.login(name, PASSWORD)
        assert isinstance(token, str), token
        return token

    def test_a_player_can_register_log_in_mine_and_look_at_the_inventory(self) -> None:
        game = self.start()
        token = self.signed_in(game, "ada")
        self.assertEqual("You mine 3 iron.", game.front.submit(token, "mine iron 3"))
        self.assertEqual("You are carrying: torch\nResources: iron 3",
                         game.front.submit(token, "inventory"))

    def test_both_threads_run_and_close_stops_them(self) -> None:
        game = self.start()
        self.assertLessEqual(THREADS, thread_names())
        game.close()
        self.assertFalse(THREADS & thread_names())
        game.close()  # twice is harmless

    def test_everything_survives_a_restart(self) -> None:
        game = self.start()
        token = self.signed_in(game, "ada")
        game.front.submit(token, "mine iron 3")
        game.close()
        again = self.start()
        token = again.front.login("ada", PASSWORD)
        self.assertEqual("You are carrying: torch\nResources: iron 3",
                         again.front.submit(token, "inventory"))
        self.assertEqual("You mine 497 iron.", again.front.submit(token, "mine iron 497"))

    def test_a_dropped_torch_stays_dropped_and_is_not_given_back(self) -> None:
        game = self.start()
        token = self.signed_in(game, "ada")
        self.assertEqual("You drop the torch.", game.front.submit(token, "drop torch"))
        game.close()
        again = self.start()
        token = again.front.login("ada", PASSWORD)
        self.assertEqual("You are carrying nothing.", again.front.submit(token, "inventory"))

    def test_players_have_separate_bags_and_each_their_own_torch(self) -> None:
        game = self.start()
        ada, bob = self.signed_in(game, "ada"), self.signed_in(game, "bob")
        game.front.submit(ada, "mine iron 2")
        self.assertEqual("You are carrying: torch", game.front.submit(bob, "inventory"))
        self.assertEqual("You drop the torch.", game.front.submit(ada, "drop torch"))
        # The bug your professor hit: before, this second drop was refused.
        self.assertEqual("You drop the torch.", game.front.submit(bob, "drop torch"))
        self.assertEqual("On the ground here: torch, torch", game.front.submit(bob, "look"))

    def test_two_players_mining_at_once_lose_nothing(self) -> None:
        game = self.start()
        tokens = [self.signed_in(game, "ada"), self.signed_in(game, "bob")]

        def work(token: str) -> None:
            for _ in range(5):
                game.front.submit(token, "mine iron 1")

        workers = [threading.Thread(target=work, args=(t,), daemon=True) for t in tokens]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(WAIT)
        self.assertEqual("You mine 490 iron.", game.front.submit(tokens[0], "mine iron 490"))

    def test_an_operation_left_unfinished_is_recovered_at_startup(self) -> None:
        AccountRegistry(JsonAccountRepository(self.state / ACCOUNTS_FILE), 1).register(
            "ada", PASSWORD)
        JsonUniverseRepository(self.state / UNIVERSE_FILE).save(
            UniverseState({"ada": "earth"}, {"earth": {"iron": 500}}, {}, {}))
        JsonInventoryRepository(self.state / PLAYERS_FILE).save(
            {"ada": [("torch", "torch")]}, None,
            [Request("old-op1", "mine", "ada", "iron", 3)])
        game = self.start()
        token = game.front.login("ada", PASSWORD)
        self.assertEqual("You are carrying: torch\nResources: iron 3",
                         game.front.submit(token, "inventory"))


class TestStartupFailures(unittest.TestCase):
    def setUp(self) -> None:
        self.state = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state)

    def test_a_damaged_key_file_is_refused_before_any_thread_starts(self) -> None:
        (self.state / SERVER_KEY_FILE).write_text("abc", encoding="ascii")
        with self.assertRaises(CorruptKeyError):
            build_game(SPACE_FILE, self.state, iterations=1)
        self.assertFalse(THREADS & thread_names())

    def test_a_failure_after_the_universe_thread_started_stops_it_again(self) -> None:
        (self.state / PLAYERS_FILE).write_text("{bad", encoding="utf-8")
        with self.assertRaises(CorruptStoreError):
            build_game(SPACE_FILE, self.state, iterations=1)
        self.assertFalse(THREADS & thread_names())

    def test_bad_arguments_are_refused(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            build_game("space.json", self.state)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            build_game(SPACE_FILE, "state")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()