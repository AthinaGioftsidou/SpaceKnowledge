"""Tests for Item and PlainItem."""

import unittest

from observatory.world.item import Item, PlainItem


class TestItemConstruction(unittest.TestCase):
    def test_plain_item_reports_its_description(self) -> None:
        key = PlainItem("brass_key", "brass key", "a small brass key")
        self.assertEqual("a small brass key", key.describe())

    def test_identity_is_exposed(self) -> None:
        key = PlainItem("brass_key", "brass key", "a small brass key")
        self.assertEqual("brass_key", key.item_id)
        self.assertEqual("brass key", key.name)

    def test_empty_item_id_is_refused(self) -> None:
        # An item with no id could never be referred to by any verb, so it is
        # refused at construction rather than allowed to exist and fail later.
        with self.assertRaises(ValueError):
            PlainItem("", "brass key", "a small brass key")

    def test_empty_name_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            PlainItem("brass_key", "", "a small brass key")

    def test_empty_description_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            PlainItem("brass_key", "brass key", "")


class TestItemIsAbstract(unittest.TestCase):
    def test_item_cannot_be_instantiated(self) -> None:
        # Item declares describe() and supplies no body, so Python refuses to
        # build one. This is what @abstractmethod buys over a docstring saying so.
        with self.assertRaises(TypeError):
            Item("x", "x")  # type: ignore[abstract]


if __name__ == "__main__":
    unittest.main()
