"""Tests for the name and password rules and the hashing."""

import unittest
from dataclasses import FrozenInstanceError

from observatory.users.credentials import (
    PasswordHash,
    check_password,
    check_username,
    make_hash,
    normalise_username,
    verify_password,
)


class TestUsernames(unittest.TestCase):
    def test_good_names_are_accepted(self) -> None:
        for name in ("ada", "a_b", "player_42", "x" * 20):
            with self.subTest(name=name):
                self.assertIsNone(check_username(name))

    def test_bad_names_are_refused_with_a_reason(self) -> None:
        for name in ("", "ab", "x" * 21, "Ada", "has space", "dot.dot", "ünï"):
            with self.subTest(name=name):
                self.assertIsInstance(check_username(name), str)

    def test_normalising_trims_and_lowercases(self) -> None:
        self.assertEqual("ada", normalise_username("  Ada "))
        self.assertIsNone(check_username(normalise_username("  Ada ")))


class TestPasswords(unittest.TestCase):
    def test_a_good_password_is_accepted(self) -> None:
        self.assertIsNone(check_password("correct horse"))

    def test_too_short_or_too_long_is_refused(self) -> None:
        for password in ("", "short", "x" * 129):
            with self.subTest(length=len(password)):
                self.assertIsInstance(check_password(password), str)

    def test_a_password_is_not_trimmed(self) -> None:
        self.assertIsNone(check_password("   spaces   "))


class TestHashing(unittest.TestCase):
    def test_the_right_password_verifies_and_a_wrong_one_does_not(self) -> None:
        stored = make_hash("correct horse", 10)
        self.assertTrue(verify_password("correct horse", stored))
        self.assertFalse(verify_password("correct horsf", stored))

    def test_the_same_password_hashes_differently_each_time(self) -> None:
        self.assertNotEqual(make_hash("correct horse", 10), make_hash("correct horse", 10))

    def test_the_hash_does_not_contain_the_password(self) -> None:
        stored = make_hash("correct horse", 10)
        self.assertNotIn("correct", f"{stored.salt}{stored.digest}")
        self.assertEqual(10, stored.iterations)

    def test_a_hash_cannot_be_changed(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            make_hash("correct horse", 10).iterations = 1  # type: ignore[misc]

    def test_a_badly_formed_hash_is_refused(self) -> None:
        good = {"salt": "a" * 32, "iterations": 5, "digest": "b" * 64}
        for change in ({"salt": "zz"}, {"salt": "a" * 31}, {"iterations": 0},
                       {"iterations": True}, {"iterations": 1.5},
                       {"digest": "b" * 63}, {"digest": "B" * 64}):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    PasswordHash(**{**good, **change})

    def test_bad_arguments_are_refused(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            check_username(5)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            check_password(5)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            normalise_username(5)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            make_hash(5, 10)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            verify_password("x", "hash")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            make_hash("correct horse", 0)


if __name__ == "__main__":
    unittest.main()