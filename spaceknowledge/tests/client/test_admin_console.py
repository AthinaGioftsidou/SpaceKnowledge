"""Tests for the admin client console, with a fake client (no network)."""

import unittest
from typing import Any

from spaceknowledge.client.admin_client import AdminClient
from spaceknowledge.client.admin_console import format_stats, run_admin_client
from spaceknowledge.client.http_client import SessionEnded
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.tests.app.helpers import Script

CODE = "12345678"


class FakeAdminClient(AdminClient):
    def __init__(self) -> None:
        super().__init__("127.0.0.1", 9)
        self.calls: list[str] = []
        self.down = False
        self.expired = False

    def request_code(self, admin: str) -> Refusal | None:
        self.calls.append("request_code")
        if self.down:
            raise ConnectionError("down")
        return None

    def login(self, admin: str, code: str) -> str | Refusal:
        self.calls.append("login")
        if code != CODE:
            return Refusal("admin login", "the code is wrong, expired or already used",
                           "request a new code")
        return "admin-token"

    def players(self, token: str) -> list[str]:
        self.calls.append("players")
        if self.expired:
            raise SessionEnded(Refusal("list", "you are not logged in", "log in again"))
        return ["ada", "bob"]

    def stats(self, token: str) -> dict[str, Any]:
        self.calls.append("stats")
        return {"queue_depth": 0, "latency_ms": {"mean": 1.5, "max": 3.0}}

    def logout(self, token: str) -> bool:
        self.calls.append("logout")
        return True


def run(client: FakeAdminClient, lines: list[str], secrets: list[str]) -> list[str]:
    out: list[str] = []
    run_admin_client(client, Script(*lines), Script(*secrets), out.append)
    return out


class TestConsole(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeAdminClient()

    def test_a_whole_session(self) -> None:
        out = run(self.client, ["root", "help", "players", "stats", "quit"], [CODE])
        text = "\n".join(out)
        self.assertIn("Players: ada, bob", text)
        self.assertIn("queue depth: 0", text)
        self.assertIn("latency ms: max 3.0, mean 1.5", text)
        self.assertEqual("Goodbye.", out[-1])
        self.assertEqual(["request_code", "login", "players", "stats", "logout"], self.client.calls)

    def test_the_code_is_never_printed(self) -> None:
        self.assertNotIn(CODE, "\n".join(run(self.client, ["root", "quit"], [CODE])))

    def test_a_wrong_code_is_refused_and_nothing_else_runs(self) -> None:
        out = run(self.client, ["root", "players"], ["00000000"])
        self.assertTrue(any("Next:" in text for text in out))
        self.assertNotIn("players", self.client.calls)

    def test_an_unknown_command_is_refused_and_blank_lines_are_ignored(self) -> None:
        out = run(self.client, ["root", "", "delete", "quit"], [CODE])
        self.assertTrue(any("delete" in text and "Next:" in text for text in out))

    def test_a_game_that_cannot_be_reached_is_explained(self) -> None:
        self.client.down = True
        out = run(self.client, ["root"], [])
        self.assertTrue(any("did not answer" in text for text in out))

    def test_an_expired_session_is_explained_and_ends_the_console(self) -> None:
        self.client.expired = True
        out = run(self.client, ["root", "players", "stats"], [CODE])
        self.assertTrue(any("not logged in" in text for text in out))
        self.assertNotIn("stats", self.client.calls)

    def test_the_end_of_the_input_ends_quietly_and_logs_out(self) -> None:
        run(self.client, ["root"], [CODE])
        self.assertIn("logout", self.client.calls)
        self.assertEqual(1, len(run(FakeAdminClient(), [], [])))

    def test_stats_are_formatted_one_line_each(self) -> None:
        self.assertEqual("a b: 1\nc: x 2, y 3", format_stats({"c": {"x": 2, "y": 3}, "a_b": 1}))

    def test_a_string_is_refused_where_a_client_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            run_admin_client("client", Script(), Script(), print)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()