"""Tests for the admin office and the admin console."""

import shutil
import tempfile
import unittest
from pathlib import Path

from observatory.app.admin import AdminOffice, build_admin
from observatory.app.admin_console import run_admin
from observatory.app.paths import ACCOUNTS_FILE
from observatory.common.refusal import Refusal
from observatory.tests.app.helpers import Script
from observatory.users.account_repository import JsonAccountRepository
from observatory.users.accounts import AccountRegistry


class TestAdmin(unittest.TestCase):
    def setUp(self) -> None:
        self.state = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state)
        self.office = build_admin(self.state)

    def register(self, *names: str) -> None:
        accounts = AccountRegistry(JsonAccountRepository(self.state / ACCOUNTS_FILE), 1)
        for name in names:
            accounts.register(name, "correct horse")

    def code(self, prompt: str = "") -> str:
        return self.office.mailbox_path.read_text(encoding="utf-8").split("Code: ")[1][:8]

    def token(self) -> str:
        self.office.request_code("root")
        token = self.office.login("root", self.code())
        assert isinstance(token, str), token
        return token

    def test_the_code_in_the_mailbox_file_gives_an_admin_token_once(self) -> None:
        self.office.request_code("root")
        code = self.code()
        self.assertIsInstance(self.office.login("root", code), str)
        self.assertIsInstance(self.office.login("root", code), Refusal)

    def test_a_wrong_code_or_an_unknown_admin_is_refused(self) -> None:
        self.office.request_code("root")
        self.assertIsInstance(self.office.login("root", "00000000x"), Refusal)
        self.assertIsInstance(self.office.login("mallory", "12345678"), Refusal)

    def test_the_players_are_listed_fresh_from_the_saved_accounts(self) -> None:
        token = self.token()
        self.assertEqual([], self.office.players(token))
        self.register("bob", "ada")
        self.assertEqual(["ada", "bob"], self.office.players(token))

    def test_without_an_admin_token_nothing_is_listed(self) -> None:
        self.assertIsInstance(self.office.players("not-a-token"), Refusal)
        token = self.token()
        self.office.logout(token)
        self.assertIsInstance(self.office.players(token), Refusal)

    def test_the_console_logs_in_lists_players_and_quits(self) -> None:
        self.register("ada")
        out: list[str] = []
        run_admin(self.office, Script("root", "help", "players", "quit"), self.code, out.append)
        # the code is read only after the request has written it
        text = "\n".join(out)
        self.assertIn("Players: ada", text)
        self.assertIn("You can:", text)
        self.assertEqual("Goodbye.", out[-1])

    def test_the_console_refuses_a_wrong_code_and_stops(self) -> None:
        out: list[str] = []
        run_admin(self.office, Script("root", "players"), Script("99999999"), out.append)
        text = "\n".join(out)
        self.assertIn("Next:", text)
        self.assertNotIn("Players", text)

    def test_the_console_refuses_an_unknown_command(self) -> None:
        out: list[str] = []
        run_admin(self.office, Script("root", "delete", "quit"), self.code, out.append)
        self.assertTrue(any("delete" in text and "Next:" in text for text in out))

    def test_bad_arguments_are_refused(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            AdminOffice("gate", None, Path("x"))  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            run_admin("office", Script(), Script(), print)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()