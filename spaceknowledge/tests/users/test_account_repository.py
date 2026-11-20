"""Tests for the account repositories: in memory and JSON on disk."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from spaceknowledge.users.account_repository import (
    AccountRepository,
    CorruptAccountsError,
    InMemoryAccountRepository,
    JsonAccountRepository,
)
from spaceknowledge.users.credentials import make_hash

ACCOUNTS = {"ada": make_hash("correct horse", 10), "bob": make_hash("battery staple", 10)}
GOOD = {"salt": "a" * 32, "iterations": 5, "hash": "b" * 64}


class TestInMemory(unittest.TestCase):
    def test_nothing_saved_loads_as_empty(self) -> None:
        self.assertEqual({}, InMemoryAccountRepository().load())

    def test_what_was_saved_is_loaded_as_a_copy(self) -> None:
        repository = InMemoryAccountRepository()
        repository.save(ACCOUNTS)
        repository.load().clear()
        self.assertEqual(ACCOUNTS, repository.load())

    def test_the_abstract_repository_cannot_be_built(self) -> None:
        with self.assertRaises(TypeError):
            AccountRepository()  # type: ignore[abstract]


class TestJson(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = self.directory / "accounts.json"
        self.repository = JsonAccountRepository(self.path)

    def test_a_missing_file_loads_as_empty(self) -> None:
        self.assertEqual({}, self.repository.load())

    def test_accounts_round_trip(self) -> None:
        self.repository.save(ACCOUNTS)
        self.assertEqual(ACCOUNTS, self.repository.load())

    def test_saving_leaves_no_temporary_file(self) -> None:
        self.repository.save(ACCOUNTS)
        self.assertEqual(["accounts.json"], sorted(p.name for p in self.directory.iterdir()))

    def test_the_file_holds_no_plain_password(self) -> None:
        self.repository.save(ACCOUNTS)
        text = self.path.read_text(encoding="utf-8")
        self.assertNotIn("correct horse", text)
        self.assertNotIn("battery staple", text)

    def test_a_file_that_cannot_be_trusted_is_refused(self) -> None:
        def doc(accounts: object, version: object = 1) -> str:
            return json.dumps({"version": version, "accounts": accounts})

        bad_files = [
            "{bad",
            "[]",
            doc({}, version=2),
            doc({}, version=True),
            doc([]),
            doc({"Ab": GOOD}),
            doc({"ada": "x"}),
            doc({"ada": {k: v for k, v in GOOD.items() if k != "salt"}}),
            doc({"ada": {**GOOD, "salt": "zz"}}),
            doc({"ada": {**GOOD, "iterations": 0}}),
            doc({"ada": {**GOOD, "iterations": True}}),
            doc({"ada": {**GOOD, "hash": "b" * 10}}),
        ]
        for text in bad_files:
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(CorruptAccountsError):
                    self.repository.load()

    def test_a_string_is_refused_where_a_path_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            JsonAccountRepository("accounts.json")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()