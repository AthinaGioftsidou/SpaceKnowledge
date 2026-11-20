"""Tests for AccountRegistry."""

import shutil
import tempfile
import unittest
from pathlib import Path

from spaceknowledge.common.refusal import Refusal
from spaceknowledge.users.account_repository import (
    InMemoryAccountRepository,
    JsonAccountRepository,
)
from spaceknowledge.users.accounts import AccountRegistry

PASSWORD = "correct horse"


def a_registry(repository: InMemoryAccountRepository | None = None) -> AccountRegistry:
    # One hashing round, so the tests are fast. Real use keeps the default.
    return AccountRegistry(repository, iterations=1)


class FailingRepository(InMemoryAccountRepository):
    def save(self, accounts) -> None:  # type: ignore[no-untyped-def]
        raise OSError("disk full")


class TestRegistering(unittest.TestCase):
    def test_a_registered_player_can_log_in(self) -> None:
        registry = a_registry()
        self.assertIsNone(registry.register("ada", PASSWORD))
        self.assertTrue(registry.has_account("ada"))
        self.assertIsNone(registry.authenticate("ada", PASSWORD))

    def test_names_are_not_case_sensitive(self) -> None:
        registry = a_registry()
        registry.register("Ada", PASSWORD)
        self.assertIsNone(registry.authenticate("ADA", PASSWORD))

    def test_a_taken_name_is_refused(self) -> None:
        registry = a_registry()
        registry.register("ada", PASSWORD)
        refusal = registry.register("ada", "another password")
        self.assertIn("taken", refusal.describe())
        self.assertIsNone(registry.authenticate("ada", PASSWORD))

    def test_a_bad_name_or_password_is_refused_with_all_three_parts(self) -> None:
        registry = a_registry()
        for name, password in (("ab", PASSWORD), ("has space", PASSWORD), ("ada", "short")):
            with self.subTest(name=name, password=password):
                refusal = registry.register(name, password)
                self.assertIsInstance(refusal, Refusal)
                self.assertIn("Next:", refusal.describe())
                self.assertFalse(registry.has_account(name))

    def test_a_refusal_never_contains_the_password(self) -> None:
        refusal = a_registry().register("ab", "secret-password-123")
        self.assertNotIn("secret-password-123", refusal.describe())

    def test_a_failed_save_registers_nobody(self) -> None:
        registry = a_registry(FailingRepository())
        with self.assertRaises(OSError):
            registry.register("ada", PASSWORD)
        self.assertFalse(registry.has_account("ada"))


class TestLoggingIn(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = a_registry()
        self.registry.register("ada", PASSWORD)

    def test_a_wrong_password_is_refused(self) -> None:
        self.assertIsInstance(self.registry.authenticate("ada", "wrong password"), Refusal)

    def test_an_unknown_name_gets_the_same_answer_as_a_wrong_password(self) -> None:
        # So nobody can use the answer to find out which names exist.
        unknown = self.registry.authenticate("zed", PASSWORD)
        wrong = self.registry.authenticate("ada", "wrong password")
        self.assertEqual(wrong.describe(), unknown.describe())

    def test_an_enormous_password_is_refused_without_hashing_it(self) -> None:
        self.assertIsInstance(self.registry.authenticate("ada", "x" * 100000), Refusal)

    def test_the_refusal_says_what_why_and_next(self) -> None:
        text = self.registry.authenticate("ada", "wrong password").describe()
        for part in ("Refused", "Why:", "Next:"):
            self.assertIn(part, text)


class TestRestart(unittest.TestCase):
    def test_accounts_survive_a_restart_in_memory(self) -> None:
        repository = InMemoryAccountRepository()
        a_registry(repository).register("ada", PASSWORD)
        self.assertIsNone(a_registry(repository).authenticate("ada", PASSWORD))

    def test_accounts_survive_a_restart_through_a_real_file(self) -> None:
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory)
        path = directory / "accounts.json"
        a_registry(JsonAccountRepository(path)).register("ada", PASSWORD)
        again = a_registry(JsonAccountRepository(path))
        self.assertIsNone(again.authenticate("ada", PASSWORD))
        self.assertIsInstance(again.authenticate("ada", "wrong password"), Refusal)


class TestArguments(unittest.TestCase):
    def test_bad_arguments_are_refused(self) -> None:
        registry = a_registry()
        with self.assertRaisesRegex(TypeError, "must be"):
            AccountRegistry("accounts.json")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            AccountRegistry(iterations=0)
        with self.assertRaisesRegex(TypeError, "must be"):
            registry.register("ada", 12345678)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            registry.authenticate(5, PASSWORD)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()