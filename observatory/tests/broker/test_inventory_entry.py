"""Tests for InventoryEntry and the three states an item can be in."""

import unittest

from observatory.broker.inventory_entry import InventoryEntry
from observatory.common.refusal import Refusal


def a_torch() -> InventoryEntry:
    return InventoryEntry("torch", "torch")


class TestConstruction(unittest.TestCase):
    def test_a_new_entry_is_owned_and_usable(self) -> None:
        entry = a_torch()
        self.assertEqual("owned", entry.state_name())
        self.assertTrue(entry.is_usable())

    def test_an_empty_id_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            InventoryEntry("", "torch")

    def test_an_empty_name_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            InventoryEntry("torch", "")


class TestOwned(unittest.TestCase):
    def test_beginning_a_drop_makes_it_unusable(self) -> None:
        entry = a_torch()
        self.assertIsNone(entry.begin_drop())
        self.assertEqual("being_dropped", entry.state_name())
        self.assertFalse(entry.is_usable())

    def test_finishing_a_drop_that_never_began_is_refused(self) -> None:
        entry = a_torch()
        self.assertIsInstance(entry.finish_drop(), Refusal)
        self.assertEqual("owned", entry.state_name())

    def test_cancelling_a_drop_that_never_began_is_refused(self) -> None:
        entry = a_torch()
        self.assertIsInstance(entry.cancel_drop(), Refusal)
        self.assertEqual("owned", entry.state_name())


class TestBeingDropped(unittest.TestCase):
    def setUp(self) -> None:
        self.entry = a_torch()
        self.entry.begin_drop()

    def test_a_second_drop_is_refused_and_nothing_changes(self) -> None:
        refusal = self.entry.begin_drop()
        self.assertIsInstance(refusal, Refusal)
        self.assertEqual("being_dropped", self.entry.state_name())

    def test_the_universe_saying_ok_finishes_the_drop(self) -> None:
        self.assertIsNone(self.entry.finish_drop())
        self.assertEqual("dropped", self.entry.state_name())

    def test_the_universe_saying_no_gives_the_item_back(self) -> None:
        self.assertIsNone(self.entry.cancel_drop())
        self.assertEqual("owned", self.entry.state_name())
        self.assertTrue(self.entry.is_usable())


class TestDroppedIsFinal(unittest.TestCase):
    def setUp(self) -> None:
        self.entry = a_torch()
        self.entry.begin_drop()
        self.entry.finish_drop()

    def test_it_is_not_usable(self) -> None:
        self.assertFalse(self.entry.is_usable())

    def test_no_move_gets_it_back(self) -> None:
        for move in (self.entry.begin_drop, self.entry.finish_drop, self.entry.cancel_drop):
            with self.subTest(move=move.__name__):
                self.assertIsInstance(move(), Refusal)
                self.assertEqual("dropped", self.entry.state_name())


class TestTheRefusalExplainsItself(unittest.TestCase):
    def test_it_names_the_item_and_the_state(self) -> None:
        entry = a_torch()
        entry.begin_drop()
        text = entry.begin_drop().describe()
        self.assertIn("torch", text)
        self.assertIn("being_dropped", text)


if __name__ == "__main__":
    unittest.main()