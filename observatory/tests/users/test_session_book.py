"""Tests for SessionBook."""

import unittest

from observatory.users.session_book import SessionBook


class TestSessionBook(unittest.TestCase):
    def test_a_token_gives_back_its_player(self) -> None:
        book = SessionBook()
        token = book.open("ada")
        self.assertEqual("ada", book.player_for(token))

    def test_every_login_gets_a_different_long_token(self) -> None:
        book = SessionBook()
        first, second = book.open("ada"), book.open("ada")
        self.assertNotEqual(first, second)
        self.assertGreaterEqual(len(first), 32)

    def test_an_unknown_token_gives_nobody(self) -> None:
        self.assertIsNone(SessionBook().player_for("not-a-token"))

    def test_closing_ends_only_that_session(self) -> None:
        book = SessionBook()
        first, second = book.open("ada"), book.open("ada")
        self.assertTrue(book.close(first))
        self.assertIsNone(book.player_for(first))
        self.assertEqual("ada", book.player_for(second))

    def test_closing_twice_says_so(self) -> None:
        book = SessionBook()
        token = book.open("ada")
        book.close(token)
        self.assertFalse(book.close(token))

    def test_bad_arguments_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            SessionBook().open("")
        with self.assertRaisesRegex(TypeError, "must be"):
            SessionBook().player_for(5)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()