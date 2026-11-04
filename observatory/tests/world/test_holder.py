"""Tests for ItemHolder, the collection Room and Container now share."""

import unittest

from observatory.world.holder import AmbiguousName
from observatory.world.holder import ItemHolder
from observatory.world.item import PlainItem


def a_key() -> PlainItem:
    return PlainItem("brass_key", "brass key", "a small brass key")


class TestItemHolder(unittest.TestCase):
    def setUp(self) -> None:
        self.holder = ItemHolder()

    def test_a_new_holder_is_empty(self) -> None:
        self.assertEqual(0, self.holder.count())

    def test_an_added_item_is_found(self) -> None:
        key = a_key()
        self.holder.add(key)
        self.assertIs(key, self.holder.find("brass_key"))

    def test_an_absent_item_is_none(self) -> None:
        self.assertIsNone(self.holder.find("lantern"))

    def test_duplicate_ids_are_refused(self) -> None:
        self.holder.add(a_key())
        with self.assertRaises(ValueError):
            self.holder.add(a_key())

    def test_removing_returns_the_item_and_empties(self) -> None:
        self.holder.add(a_key())
        self.assertEqual("brass_key", self.holder.remove("brass_key").item_id)
        self.assertEqual(0, self.holder.count())

    def test_removing_something_absent_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.holder.remove("lantern")

    def test_contents_is_a_copy(self) -> None:
        # Hand out the real list and a caller appends past the duplicate-id
        # rule. An invariant is worthless if the caller keeps a handle.
        self.holder.add(a_key())
        self.holder.contents().clear()
        self.assertEqual(1, self.holder.count())


class TestRoomAndContainerAgreeByConstruction(unittest.TestCase):
    """The reason the extraction was worth doing.

    Before week 2 these two behaved identically by coincidence. Now they behave
    identically because there is one implementation. These tests would still
    pass with two copies; what changed is that they cannot now drift apart.
    """

    def test_both_refuse_duplicate_ids(self) -> None:
        from observatory.world.container import Container
        from observatory.world.room import Room

        room = Room("hall", "Hall", "Tiled.")
        chest = Container("chest", "chest", "a chest")
        room.add_item(a_key())
        chest.add(a_key())
        with self.assertRaises(ValueError):
            room.add_item(a_key())
        with self.assertRaises(ValueError):
            chest.add(a_key())


class TestTwoItemsOneName(unittest.TestCase):
    """Ids are unique, names are not. A name two items share must not pick one."""

    def setUp(self) -> None:
        self.holder = ItemHolder()
        self.holder.add(a_key())
        self.holder.add(PlainItem("spare_key", "brass key", "a dull brass key"))

    def test_the_shared_name_is_refused_and_both_ids_are_offered(self) -> None:
        with self.assertRaisesRegex(AmbiguousName, r"^Which brass key\? brass_key, spare_key$"):
            self.holder.match("Brass Key")

    def test_an_id_still_picks_exactly_one(self) -> None:
        self.assertEqual("spare_key", self.holder.match("spare_key").item_id)

    def test_a_name_only_one_item_has_still_matches(self) -> None:
        self.holder.add(PlainItem("torch", "torch", "a rubber torch"))
        self.assertEqual("torch", self.holder.match("torch").item_id)


class TestArgumentTypes(unittest.TestCase):
    def test_a_string_is_refused_where_a_class_is_expected(self) -> None:
        # Python does not enforce an annotation, so the method checks it.
        bad = "not an object"
        calls = [
            ("add item", lambda: ItemHolder().add(bad)),
        ]
        for label, call in calls:
            with self.subTest(label):
                with self.assertRaisesRegex(TypeError, "must be"):
                    call()


if __name__ == "__main__":
    unittest.main()
