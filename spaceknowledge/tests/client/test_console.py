"""Tests for the client console, with a fake client (no network)."""

import unittest

from spaceknowledge.client.console import run_client
from spaceknowledge.client.game_client import GameClient, SessionEnded
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.tests.app.helpers import Script

PASSWORD = "correct horse"


class FakeClient(GameClient):
    """Scripted behaviour, and a record of what the console asked for."""

    def __init__(self) -> None:
        super().__init__("127.0.0.1", 9)
        self.calls: list[tuple[str, str]] = []
        self.accounts: dict[str, str] = {}
        self.down = False
        self.failing_line: str | None = None
        self.expire_after: int | None = None
        self.commands = 0

    def register(self, username: str, password: str) -> Refusal | None:
        self.calls.append(("register", username))
        if self.down:
            raise ConnectionError("down")
        if username in self.accounts:
            return Refusal("register", "that name is already taken", "choose another name")
        self.accounts[username] = password
        return None

    def login(self, username: str, password: str) -> str | Refusal:
        self.calls.append(("login", username))
        if self.down:
            raise ConnectionError("down")
        if self.accounts.get(username) != password:
            return Refusal("log in", "the name or the password is wrong", "check both")
        return "token-" + username

    def command(self, token: str, line: str) -> str:
        self.calls.append(("command", line))
        if line == self.failing_line:
            raise ConnectionError("down")
        self.commands += 1
        if self.expire_after is not None and self.commands > self.expire_after:
            raise SessionEnded(Refusal("send a command", "you are not logged in", "log in first"))
        return "echo: " + line

    def logout(self, token: str) -> bool:
        self.calls.append(("logout", token))
        return True


def play(client: FakeClient, lines: list[str], secrets: list[str]) -> list[str]:
    out: list[str] = []
    run_client(client, Script(*lines), Script(*secrets), out.append)
    return out


class TestConsole(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeClient()

    def test_a_whole_game_from_register_to_quit(self) -> None:
        out = play(self.client, ["register", "ada", "login", "ada", "mine iron 2", "quit"],
                   [PASSWORD, PASSWORD])
        self.assertIn("echo: mine iron 2", out)
        self.assertEqual("Goodbye.", out[-1])
        self.assertIn(("logout", "token-ada"), self.client.calls)

    def test_a_password_is_never_printed(self) -> None:
        out = play(self.client, ["register", "ada", "login", "ada", "quit"], [PASSWORD, PASSWORD])
        self.assertNotIn(PASSWORD, "\n".join(out))

    def test_a_wrong_password_and_a_taken_name_are_refused_with_three_parts(self) -> None:
        out = play(self.client, ["register", "ada", "register", "ada", "login", "ada", "quit"],
                   [PASSWORD, PASSWORD, "wrong password"])
        text = "\n".join(out)
        for part in ("already taken", "Why:", "Next:"):
            self.assertIn(part, text)

    def test_an_unknown_menu_word_is_refused_and_blank_lines_are_ignored(self) -> None:
        out = play(self.client, ["", "juggle", "quit"], [])
        self.assertTrue(any("juggle" in text and "Next:" in text for text in out))

    def test_the_end_of_the_input_ends_quietly_and_logs_out(self) -> None:
        self.assertEqual(1, len(play(self.client, [], [])))
        play(self.client, ["register", "ada", "login", "ada"], [PASSWORD, PASSWORD])
        self.assertIn(("logout", "token-ada"), self.client.calls)

    def test_a_game_that_cannot_be_reached_is_explained_and_never_crashes(self) -> None:
        self.client.down = True
        out = play(self.client, ["register", "ada", "login", "ada", "quit"], [PASSWORD, PASSWORD])
        text = "\n".join(out)
        self.assertEqual(2, text.count("did not answer"))
        self.assertNotIn("universe", text.lower())

    def test_a_lost_connection_mid_game_is_explained_and_the_game_goes_on(self) -> None:
        self.client.failing_line = "fail"
        out = play(self.client,
                   ["register", "ada", "login", "ada", "fail", "ok", "quit"], [PASSWORD, PASSWORD])
        self.assertTrue(any("did not answer" in text for text in out))
        self.assertIn("echo: ok", out)

    def test_an_expired_session_returns_to_the_menu_where_the_player_can_log_in_again(self) -> None:
        self.client.expire_after = 1
        out = play(self.client,
                   ["register", "ada", "login", "ada", "a", "b", "quit"], [PASSWORD, PASSWORD])
        text = "\n".join(out)
        self.assertIn("not logged in", text)
        self.assertEqual("Goodbye.", out[-1])
        self.assertIn(("logout", "token-ada"), self.client.calls)

    def test_a_string_is_refused_where_a_client_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            run_client("client", Script(), Script(), print)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()