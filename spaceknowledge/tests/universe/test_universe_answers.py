"""Tests for the bounded cache of answered operations."""

import unittest

from spaceknowledge.common.messages import Request, Response
from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.universe import DEFAULT_MAX_ANSWERS, Universe
from spaceknowledge.universe.universe_repository import (
    InMemoryUniverseRepository,
    UniverseState,
)
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World


def mine(op_id: str) -> Request:
    return Request(op_id, "mine", "ada", "iron", 1)


def an_earth(max_answers: int = 3, repository: InMemoryUniverseRepository | None = None):
    earth = Destination("earth", "Earth", "Home.")
    deposits = Deposits({"earth": {"iron": 100}})
    universe = Universe(World({"earth": earth}, "earth"), deposits, repository, max_answers)
    universe.place_player("ada", "earth")
    return universe, deposits


class TestTheCacheIsBounded(unittest.TestCase):
    def test_it_never_holds_more_than_the_limit(self) -> None:
        universe, deposits = an_earth()
        for number in range(1, 7):
            universe.handle(mine(f"op{number}"))
        self.assertEqual(3, universe.answer_count())
        self.assertEqual(94, deposits.available("earth", "iron"))

    def test_a_recent_answer_is_still_replayed_without_acting(self) -> None:
        universe, deposits = an_earth()
        for number in range(1, 5):
            universe.handle(mine(f"op{number}"))
        first = universe.handle(mine("op5"))
        self.assertIs(first, universe.handle(mine("op5")))
        self.assertEqual(95, deposits.available("earth", "iron"))

    def test_an_answer_older_than_the_limit_is_decided_again(self) -> None:
        # The documented limit: the cache must be larger than the number of
        # operations that can be unfinished at once.
        universe, deposits = an_earth()
        for number in range(1, 6):
            universe.handle(mine(f"op{number}"))
        universe.handle(mine("op1"))
        self.assertEqual(94, deposits.available("earth", "iron"))

    def test_the_saved_state_holds_only_the_kept_answers_newest_last(self) -> None:
        repository = InMemoryUniverseRepository()
        universe, _ = an_earth(3, repository)
        for number in range(1, 6):
            universe.handle(mine(f"op{number}"))
        self.assertEqual(["op3", "op4", "op5"], list(repository.load().answers))

    def test_a_look_is_never_counted(self) -> None:
        universe, _ = an_earth()
        for number in range(5):
            universe.handle(Request(f"l{number}", "look", "ada", "here"))
        self.assertEqual(0, universe.answer_count())

    def test_loading_more_than_the_limit_keeps_the_newest(self) -> None:
        repository = InMemoryUniverseRepository()
        repository.save(UniverseState(
            {"ada": "earth"}, {"earth": {"iron": 100}}, {},
            {f"op{n}": Response(f"op{n}") for n in range(1, 6)},
        ))
        universe, deposits = an_earth(2, repository)
        self.assertEqual(2, universe.answer_count())
        universe.handle(mine("op5"))            # kept: replayed, nothing mined
        self.assertEqual(100, deposits.available("earth", "iron"))
        universe.handle(mine("op1"))            # forgotten: decided again
        self.assertEqual(99, deposits.available("earth", "iron"))


class TestTheLimit(unittest.TestCase):
    def test_bad_limits_are_refused(self) -> None:
        world = World({"earth": Destination("earth", "Earth", "Home.")}, "earth")
        with self.assertRaises(ValueError):
            Universe(world, None, None, 0)
        for bad in ("3", True, 2.5):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(TypeError, "must be"):
                    Universe(world, None, None, bad)  # type: ignore[arg-type]

    def test_the_default_is_generous(self) -> None:
        self.assertGreaterEqual(DEFAULT_MAX_ANSWERS, 1000)


if __name__ == "__main__":
    unittest.main()