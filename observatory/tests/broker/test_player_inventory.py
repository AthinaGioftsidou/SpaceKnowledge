"""Tests for PlayerInventory, the Broker's list of what one player holds."""

import unittest

from observatory.broker.inventory_entry import InventoryEntry
from observatory.broker.player_inventory import PlayerInventory
from observatory.common.refusal import Refusal


def an_inventory_with_a_torch() -> PlayerInventory:
    inventory = PlayerInventory()
    inventory.add(InventoryEntry("torch", "torch"))
    return inventory


class TestHolding(unittest.TestCase):
    def test_a_new_inventory_is_empty(self) -> None:
        self.assertEqual(0, PlayerInventory().count())

    def test_an_added_entry_is_found(self) -> None:
        inventory = PlayerInventory()
        entry = InventoryEntry("torch", "torch")
        inventory.add(entry)
        self.assertIs(entry, inventory.find("torch"))

    def test_an_absent_entry_is_none(self) -> None:
        self.assertIsNone(PlayerInventory().find("torch"))

    def test_duplicate_ids_are_refused(self) -> None:
        inventory = an_inventory_with_a_torch()
        with self.assertRaises(ValueError):
            inventory.add(InventoryEntry("torch", "torch"))

    def test_a_string_is_refused_where_an_entry_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            PlayerInventory().add("torch")  # type: ignore[arg-type]

    def test_entries_is_a_copy(self) -> None:
        inventory = an_inventory_with_a_torch()
        inventory.entries().clear()
        self.assertEqual(1, inventory.count())


class TestUsing(unittest.TestCase):
    def test_an_owned_item_may_be_used(self) -> None:
        self.assertIsNone(an_inventory_with_a_torch().check_usable("torch"))

    def test_an_item_not_carried_is_refused(self) -> None:
        self.assertIsInstance(PlayerInventory().check_usable("torch"), Refusal)

    def test_an_item_being_dropped_is_refused_and_says_why(self) -> None:
        inventory = an_inventory_with_a_torch()
        inventory.begin_drop("torch")
        refusal = inventory.check_usable("torch")
        self.assertIsInstance(refusal, Refusal)
        self.assertIn("flight", refusal.describe())


class TestDropping(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = an_inventory_with_a_torch()

    def test_dropping_an_item_not_carried_is_refused(self) -> None:
        self.assertIsInstance(self.inventory.begin_drop("lantern"), Refusal)

    def test_beginning_a_drop_keeps_the_entry_but_locks_it(self) -> None:
        self.assertIsNone(self.inventory.begin_drop("torch"))
        self.assertEqual(1, self.inventory.count())
        self.assertFalse(self.inventory.find("torch").is_usable())

    def test_finishing_a_drop_removes_the_entry(self) -> None:
        self.inventory.begin_drop("torch")
        self.assertIsNone(self.inventory.finish_drop("torch"))
        self.assertEqual(0, self.inventory.count())

    def test_cancelling_a_drop_gives_the_item_back(self) -> None:
        self.inventory.begin_drop("torch")
        self.assertIsNone(self.inventory.cancel_drop("torch"))
        self.assertEqual(1, self.inventory.count())
        self.assertTrue(self.inventory.find("torch").is_usable())

    def test_finishing_a_drop_that_never_began_is_refused_and_keeps_the_item(self) -> None:
        self.assertIsInstance(self.inventory.finish_drop("torch"), Refusal)
        self.assertEqual(1, self.inventory.count())

    def test_finishing_or_cancelling_an_unknown_item_is_refused(self) -> None:
        for move in (self.inventory.finish_drop, self.inventory.cancel_drop):
            with self.subTest(move=move.__name__):
                self.assertIsInstance(move("lantern"), Refusal)


if __name__ == "__main__":
    unittest.main()