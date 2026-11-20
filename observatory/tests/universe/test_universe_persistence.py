"""Tests that the Universe survives a restart."""

import shutil
import tempfile
import unittest
from pathlib import Path

from observatory.common.messages import Request, Response
from observatory.common.refusal import Refusal
from observatory.universe.deposits import Deposits
from observatory.universe.universe import Universe
from observatory.universe.universe_repository import (
    CorruptStateError,
    InMemoryUniverseRepository,
    JsonUniverseRepository,
    UniverseRepository,
    UniverseState,
)
from observatory.world.item import PlainItem
from observatory.world.room import Room
from observatory.world.world import World


def mine(op_id: str = "op1", amount: int = 3) -> Request:
    return Request(op_id, "mine", "ada", "iron", amount)


def drop(op_id: str = "op2") -> Request:
    return Request(op_id, "add_item", "ada", "torch")


class TestRestart(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryUniverseRepository()
        self.universe, self.deposits, self.earth = self.start(self.repository)
        self.universe.place_player("ada", "earth")

    @staticmethod
    def start(repository: UniverseRepository) -> tuple[Universe, Deposits, Room]:
        """A fresh process: the world and deposits are rebuilt from their
        starting data, and only the repository remembers anything."""
        earth = Room("earth", "Earth", "Home.")
        deposits = Deposits({"earth": {"iron": 10}})
        universe = Universe(World({"earth": earth}, "earth"), deposits, repository)
        return universe, deposits, earth

    def test_a_player_location_survives(self) -> None:
        universe, deposits, _ = self.start(self.repository)
        self.assertTrue(universe.handle(mine()).ok)
        self.assertEqual(7, deposits.available("earth", "iron"))

    def test_mined_stock_survives(self) -> None:
        self.universe.handle(mine())
        _, deposits, _ = self.start(self.repository)
        self.assertEqual(7, deposits.available("earth", "iron"))

    def test_a_dropped_item_is_back_in_the_world(self) -> None:
        self.universe.handle(drop())
        _, _, earth = self.start(self.repository)
        self.assertIsNotNone(earth.find_item("torch"))

    def test_an_answered_op_id_is_still_answered_and_changes_nothing(self) -> None:
        self.universe.handle(mine("op1"))
        universe, deposits, _ = self.start(self.repository)
        self.assertTrue(universe.handle(mine("op1")).ok)
        self.assertEqual(7, deposits.available("earth", "iron"))

    def test_a_refusal_is_remembered_too(self) -> None:
        first = self.universe.handle(mine("op1", 11))
        universe, deposits, _ = self.start(self.repository)
        second = universe.handle(mine("op1", 11))
        self.assertFalse(second.ok)
        self.assertEqual(first.refusal.describe(), second.refusal.describe())
        self.assertEqual(10, deposits.available("earth", "iron"))

    def test_a_new_op_id_after_a_restart_is_decided_fresh(self) -> None:
        self.universe.handle(mine("op1"))
        universe, deposits, _ = self.start(self.repository)
        universe.handle(mine("op9"))
        self.assertEqual(4, deposits.available("earth", "iron"))

    def test_a_dropped_item_keeps_its_name_after_a_restart(self) -> None:
        self.universe.handle(Request("op5", "add_item", "ada", "torch-1", name="torch"))
        _, _, earth = self.start(self.repository)
        self.assertEqual("torch", earth.find_item("torch-1").name)


class TestSavedStateIsChecked(unittest.TestCase):
    def a_world(self) -> World:
        return World({"earth": Room("earth", "Earth", "Home.")}, "earth")

    def universe_with(self, state: UniverseState) -> Universe:
        repository = InMemoryUniverseRepository()
        repository.save(state)
        return Universe(self.a_world(), Deposits({}), repository)

    def test_a_location_in_an_unknown_destination_is_refused(self) -> None:
        with self.assertRaises(CorruptStateError):
            self.universe_with(UniverseState({"ada": "venus"}, {}, {}, {}))

    def test_stock_in_an_unknown_destination_is_refused(self) -> None:
        with self.assertRaises(CorruptStateError):
            self.universe_with(UniverseState({}, {"venus": {"iron": 1}}, {}, {}))

    def test_a_drop_in_an_unknown_destination_is_refused(self) -> None:
        with self.assertRaises(CorruptStateError):
            self.universe_with(UniverseState({}, {}, {"venus": ["torch"]}, {}))

    def test_a_drop_that_clashes_with_an_item_already_there_is_refused(self) -> None:
        world = self.a_world()
        world.room("earth").add_item(PlainItem("torch", "torch", "a torch"))
        repository = InMemoryUniverseRepository()
        repository.save(UniverseState({}, {}, {"earth": ["torch"]}, {}))
        with self.assertRaises(CorruptStateError):
            Universe(world, Deposits({}), repository)

    def test_a_refused_state_leaves_the_deposits_untouched(self) -> None:
        repository = InMemoryUniverseRepository()
        repository.save(UniverseState({}, {"earth": {"iron": 1}}, {"venus": ["x"]}, {}))
        deposits = Deposits({"earth": {"iron": 10}})
        with self.assertRaises(CorruptStateError):
            Universe(self.a_world(), deposits, repository)
        self.assertEqual(10, deposits.available("earth", "iron"))

    def test_a_string_is_refused_where_a_repository_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            Universe(self.a_world(), None, "universe.json")  # type: ignore[arg-type]


class TestThroughARealFile(unittest.TestCase):
    def test_a_second_universe_reads_what_the_first_wrote(self) -> None:
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory)
        path = directory / "universe.json"

        def run() -> tuple[Universe, Deposits, Room]:
            earth = Room("earth", "Earth", "Home.")
            deposits = Deposits({"earth": {"iron": 10}})
            universe = Universe(
                World({"earth": earth}, "earth"), deposits, JsonUniverseRepository(path)
            )
            return universe, deposits, earth

        first, _, _ = run()
        first.place_player("ada", "earth")
        first.handle(mine("op1"))
        first.handle(drop("op2"))

        second, deposits, earth = run()
        self.assertEqual(7, deposits.available("earth", "iron"))
        self.assertIsNotNone(earth.find_item("torch"))
        self.assertTrue(second.handle(mine("op1")).ok)
        self.assertEqual(7, deposits.available("earth", "iron"))


if __name__ == "__main__":
    unittest.main()