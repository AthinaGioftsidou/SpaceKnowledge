"""Tests for Deposits, the resources lying in each destination."""

import json
import unittest
from pathlib import Path

from observatory.universe.deposits import Deposits

SPACE_FILE = Path(__file__).resolve().parents[3] / "data" / "space.json"


def some_deposits() -> Deposits:
    return Deposits({"earth": {"iron": 10, "water": 0}, "mars": {"nickel": 5}})


class TestReading(unittest.TestCase):
    def test_a_known_resource_reports_its_quantity(self) -> None:
        self.assertEqual(10, some_deposits().available("earth", "iron"))

    def test_an_unknown_destination_or_resource_has_none(self) -> None:
        deposits = some_deposits()
        self.assertEqual(0, deposits.available("venus", "iron"))
        self.assertEqual(0, deposits.available("earth", "nickel"))

    def test_the_input_is_copied(self) -> None:
        stock = {"earth": {"iron": 10}}
        deposits = Deposits(stock)
        stock["earth"]["iron"] = 999
        self.assertEqual(10, deposits.available("earth", "iron"))

    def test_the_snapshot_is_a_copy(self) -> None:
        deposits = some_deposits()
        deposits.snapshot()["earth"]["iron"] = 999
        self.assertEqual(10, deposits.available("earth", "iron"))


class TestRemoving(unittest.TestCase):
    def test_removing_reduces_the_stock(self) -> None:
        deposits = some_deposits()
        deposits.remove("earth", "iron", 4)
        self.assertEqual(6, deposits.available("earth", "iron"))

    def test_removing_more_than_there_is_refused_and_changes_nothing(self) -> None:
        deposits = some_deposits()
        with self.assertRaises(ValueError):
            deposits.remove("earth", "iron", 11)
        self.assertEqual(10, deposits.available("earth", "iron"))

    def test_removing_nothing_or_less_is_refused(self) -> None:
        for amount in (0, -1):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    some_deposits().remove("earth", "iron", amount)

    def test_removing_from_an_unknown_resource_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            some_deposits().remove("earth", "nickel", 1)


class TestBadData(unittest.TestCase):
    def test_a_quantity_that_is_not_a_whole_number_is_refused(self) -> None:
        for quantity in (-1, 2.5, "ten", True, None):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValueError):
                    Deposits({"earth": {"iron": quantity}})

    def test_empty_names_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            Deposits({"": {"iron": 1}})
        with self.assertRaises(ValueError):
            Deposits({"earth": {"": 1}})


class TestReadingFromRawData(unittest.TestCase):
    def test_rooms_with_resources_are_read_and_others_skipped(self) -> None:
        raw = {"rooms": [
            {"id": "earth", "resources": {"iron": 7}},
            {"id": "moon"},
        ]}
        deposits = Deposits.from_raw(raw)
        self.assertEqual(7, deposits.available("earth", "iron"))
        self.assertEqual(0, deposits.available("moon", "iron"))

    def test_resources_that_are_not_an_object_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            Deposits.from_raw({"rooms": [{"id": "earth", "resources": ["iron"]}]})

    def test_the_shipped_space_file_has_iron_on_earth_and_nickel_on_mars(self) -> None:
        raw = json.loads(SPACE_FILE.read_text(encoding="utf-8"))
        deposits = Deposits.from_raw(raw)
        self.assertEqual(500, deposits.available("earth", "iron"))
        self.assertEqual(200, deposits.available("mars", "nickel"))

class TestRestore(unittest.TestCase):
    def test_restore_replaces_everything(self) -> None:
        deposits = some_deposits()
        deposits.restore({"venus": {"gold": 2}})
        self.assertEqual(2, deposits.available("venus", "gold"))
        self.assertEqual(0, deposits.available("earth", "iron"))

    def test_a_bad_restore_changes_nothing(self) -> None:
        deposits = some_deposits()
        with self.assertRaises(ValueError):
            deposits.restore({"earth": {"iron": -1}})
        self.assertEqual(10, deposits.available("earth", "iron"))

    def test_the_restored_data_is_copied(self) -> None:
        stock = {"earth": {"iron": 5}}
        deposits = some_deposits()
        deposits.restore(stock)
        stock["earth"]["iron"] = 999
        self.assertEqual(5, deposits.available("earth", "iron"))

if __name__ == "__main__":
    unittest.main()