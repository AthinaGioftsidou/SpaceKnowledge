"""Tests for ResourceBag, the quantities of resources one player holds."""

import unittest

from observatory.broker.resource_bag import ResourceBag


class TestResourceBag(unittest.TestCase):
    def test_a_new_bag_is_empty(self) -> None:
        bag = ResourceBag()
        self.assertTrue(bag.is_empty())
        self.assertEqual(0, bag.amount_of("iron"))

    def test_adding_accumulates(self) -> None:
        bag = ResourceBag()
        bag.add("iron", 3)
        bag.add("iron", 2)
        self.assertEqual(5, bag.amount_of("iron"))
        self.assertFalse(bag.is_empty())

    def test_the_snapshot_is_a_copy(self) -> None:
        bag = ResourceBag()
        bag.add("iron", 3)
        bag.snapshot()["iron"] = 999
        self.assertEqual(3, bag.amount_of("iron"))

    def test_an_amount_below_one_is_refused(self) -> None:
        for amount in (0, -1):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    ResourceBag().add("iron", amount)

    def test_an_empty_resource_name_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            ResourceBag().add("", 1)

    def test_an_amount_that_is_not_a_whole_number_is_refused(self) -> None:
        for amount in (2.5, "3", True):
            with self.subTest(amount=amount):
                with self.assertRaisesRegex(TypeError, "must be"):
                    ResourceBag().add("iron", amount)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()