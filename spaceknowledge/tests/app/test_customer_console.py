"""Tests for the customer console."""

import shutil
import tempfile
import unittest
from pathlib import Path

from spaceknowledge.app.customer_console import run_customer
from spaceknowledge.app.game import Game, build_game
from spaceknowledge.tests.app.helpers import Script

SPACE_FILE = Path(__file__).resolve().parents[3] / "data" / "space.json"
PASSWORD = "correct horse"


class TestCustomerConsole(unittest.TestCase):
    def setUp(self) -> None:
        self.state = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state)
        self.game = build_game(SPACE_FILE, self.state, iterations=1)
        self.addCleanup(self.game.close)

    def play(self, lines: list[str], secrets: list[str], game: Game | None = None) -> list[str]:
        out: list[str] = []
        run_customer((game or self.game).front, Script(*lines), Script(*secrets), out.append)
        return out

    def test_a_whole_game_from_register_to_quit(self) -> None:
        out = self.play(
            ["register", "ada", "login", "ada", "mine iron 2", "inventory", "quit"],
            [PASSWORD, PASSWORD],
        )
        self.assertIn("You mine 2 iron.", out)
        self.assertIn("You are carrying: torch\nResources: iron 2", out)
        self.assertEqual("Goodbye.", out[-1])

    def test_a_password_is_never_printed(self) -> None:
        out = self.play(["register", "ada", "login", "ada", "quit"], [PASSWORD, PASSWORD])
        self.assertNotIn(PASSWORD, "\n".join(out))

    def test_a_wrong_password_is_refused_with_three_parts(self) -> None:
        out = self.play(["register", "ada", "login", "ada", "quit"], [PASSWORD, "wrong password"])
        text = "\n".join(out)
        for part in ("Refused", "Why:", "Next:"):
            self.assertIn(part, text)

    def test_a_taken_name_is_refused(self) -> None:
        out = self.play(["register", "ada", "register", "ada", "quit"], [PASSWORD, PASSWORD])
        self.assertTrue(any("taken" in text for text in out))

    def test_an_unknown_menu_word_gets_a_refusal_and_blank_lines_are_ignored(self) -> None:
        out = self.play(["", "juggle", "quit"], [])
        self.assertTrue(any("Next:" in text and "juggle" in text for text in out))

    def test_nonsense_in_the_game_gets_a_three_part_refusal(self) -> None:
        out = self.play(["register", "ada", "login", "ada", "juggle", "quit"], [PASSWORD, PASSWORD])
        self.assertTrue(any("Why:" in text and "juggle" in text for text in out))

    def test_the_end_of_the_input_ends_the_game_quietly(self) -> None:
        out = self.play([], [])
        self.assertEqual(1, len(out))

    def test_a_game_that_stopped_is_explained_and_not_a_crash(self) -> None:
        self.play(["register", "ada", "quit"], [PASSWORD])
        self.game.close()
        out = self.play(["login", "ada", "quit"], [PASSWORD])
        self.assertTrue(any("did not answer" in text for text in out))

    def test_a_string_is_refused_where_a_front_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            run_customer("front", Script(), Script(), print)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()