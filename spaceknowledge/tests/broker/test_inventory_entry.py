"""Tests for InventoryEntry, the Broker's record of one item."""

import unittest

from spaceknowledge.broker.inventory_entry import InventoryEntry
from spaceknowledge.common.refusal import Refusal


def a_torch() -> InventoryEntry:
    return InventoryEntry("torch", "torch")


class TestConstruction(unittest.TestCase):
    def test_a_new_entry_is_owned_by_the_broker_and_usable(self) -> None:
        entry = a_torch()
        self.assertEqual(("drop", "owned", "broker"),
                         (entry.process_name(), entry.state(), entry.holder()))
        self.assertTrue(entry.is_usable())

    def test_an_empty_id_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            InventoryEntry("", "torch")

    def test_an_empty_name_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            InventoryEntry("torch", "")


class TestOwned(unittest.TestCase):
    def test_beginning_a_drop_puts_it_in_flight_and_unusable(self) -> None:
        entry = a_torch()
        self.assertIsNone(entry.begin_drop())
        self.assertEqual("flight", entry.state())
        self.assertEqual("broker", entry.holder())
        self.assertFalse(entry.is_usable())

    def test_finishing_or_cancelling_a_drop_that_never_began_is_refused(self) -> None:
        for move in ("finish_drop", "cancel_drop"):
            with self.subTest(move=move):
                entry = a_torch()
                self.assertIsInstance(getattr(entry, move)(), Refusal)
                self.assertEqual("owned", entry.state())


class TestInFlight(unittest.TestCase):
    def setUp(self) -> None:
        self.entry = a_torch()
        self.entry.begin_drop()

    def test_a_second_drop_is_refused_and_nothing_changes(self) -> None:
        self.assertIsInstance(self.entry.begin_drop(), Refusal)
        self.assertEqual("flight", self.entry.state())

    def test_the_universe_saying_ok_finishes_the_drop(self) -> None:
        self.assertIsNone(self.entry.finish_drop())
        self.assertEqual("done", self.entry.state())
        self.assertEqual("universe", self.entry.holder())

    def test_the_universe_saying_no_gives_the_item_back(self) -> None:
        self.assertIsNone(self.entry.cancel_drop())
        self.assertEqual("owned", self.entry.state())
        self.assertTrue(self.entry.is_usable())


class TestDone(unittest.TestCase):
    def setUp(self) -> None:
        self.entry = a_torch()
        self.entry.begin_drop()
        self.entry.finish_drop()

    def test_it_is_not_usable(self) -> None:
        self.assertFalse(self.entry.is_usable())

    def test_the_drop_moves_are_refused(self) -> None:
        for move in (self.entry.begin_drop, self.entry.finish_drop, self.entry.cancel_drop):
            with self.subTest(move=move.__name__):
                self.assertIsInstance(move(), Refusal)
                self.assertEqual("done", self.entry.state())


class TestTheRefusalExplainsItself(unittest.TestCase):
    def test_it_names_the_item_and_the_state(self) -> None:
        entry = a_torch()
        entry.begin_drop()
        text = entry.begin_drop().describe()
        self.assertIn("torch", text)
        self.assertIn("flight", text)


if __name__ == "__main__":
    unittest.main()