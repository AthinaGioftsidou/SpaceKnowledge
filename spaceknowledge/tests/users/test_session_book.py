"""Tests for SessionBook: tokens, the players they stand for, and expiry."""

import unittest

from spaceknowledge.users.session_book import SessionBook


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def a_book(clock: Clock) -> SessionBook:
    return SessionBook(clock, lifetime=100.0, idle_timeout=50.0)


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
        with self.assertRaises(ValueError):
            SessionBook(lifetime=0)
        with self.assertRaises(ValueError):
            SessionBook(idle_timeout=0)


class TestExpiry(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self.book = a_book(self.clock)
        self.token = self.book.open("ada")

    def test_a_token_works_until_its_lifetime_runs_out_even_when_it_is_used(self) -> None:
        for _ in range(3):
            self.clock.now += 30
            self.assertEqual("ada", self.book.player_for(self.token))
        self.clock.now += 10          # 100 seconds after login, last used 10 ago
        self.assertIsNone(self.book.player_for(self.token))

    def test_a_token_that_is_not_used_expires_after_the_idle_time(self) -> None:
        self.clock.now += 49
        self.assertEqual("ada", self.book.player_for(self.token))
        self.clock.now += 50
        self.assertIsNone(self.book.player_for(self.token))

    def test_using_a_token_restarts_the_idle_time(self) -> None:
        self.clock.now += 40
        self.book.player_for(self.token)
        self.clock.now += 40
        self.assertEqual("ada", self.book.player_for(self.token))

    def test_an_expired_token_is_removed_and_stays_dead(self) -> None:
        self.clock.now += 200
        self.assertIsNone(self.book.player_for(self.token))
        self.assertEqual(0, self.book.count())
        self.clock.now -= 190
        self.assertIsNone(self.book.player_for(self.token))

    def test_opening_a_session_clears_out_the_expired_ones(self) -> None:
        self.clock.now += 200
        self.book.open("bob")
        self.assertEqual(1, self.book.count())

    def test_closing_an_expired_session_says_there_was_none(self) -> None:
        self.clock.now += 200
        self.assertFalse(self.book.close(self.token))


if __name__ == "__main__":
    unittest.main()