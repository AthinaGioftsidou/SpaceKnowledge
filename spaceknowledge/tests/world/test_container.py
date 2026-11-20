"""Tests for Container, the Composite node."""

import unittest

from spaceknowledge.world.container import Container
from spaceknowledge.world.item import PlainItem
from spaceknowledge.world.destination import Destination


def a_key() -> PlainItem:
    return PlainItem("brass_key", "brass key", "a small brass key")


def a_chest() -> Container:
    return Container("chest", "chest", "a dented tin chest")


class TestContainerIsAnItem(unittest.TestCase):
    def test_a_container_can_go_in_a_destination(self) -> None:
        # The whole point of Composite: Destination takes Item, and Container IS-A Item,
        # so Destination needed no change at all to hold one.
        destination = Destination("hall", "Entrance Hall", "Cold and tiled.")
        destination.add_item(a_chest())
        self.assertEqual(1, destination.item_count())

    def test_a_container_can_go_in_a_container(self) -> None:
        outer = a_chest()
        outer.add(Container("box", "box", "a cardboard box"))
        self.assertEqual(1, outer.count())


class TestContainerContents(unittest.TestCase):
    def setUp(self) -> None:
        self.chest = a_chest()

    def test_an_added_item_is_found(self) -> None:
        key = a_key()
        self.chest.add(key)
        self.assertIs(key, self.chest.find("brass_key"))

    def test_an_absent_item_is_none(self) -> None:
        self.assertIsNone(self.chest.find("lantern"))

    def test_duplicate_ids_are_refused(self) -> None:
        self.chest.add(a_key())
        with self.assertRaises(ValueError):
            self.chest.add(a_key())

    def test_direct_self_containment_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.chest.add(self.chest)

    def test_removing_an_item_returns_it_and_empties(self) -> None:
        key = a_key()
        self.chest.add(key)
        self.assertIs(key, self.chest.remove("brass_key"))
        self.assertEqual(0, self.chest.count())

    def test_removing_something_absent_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.chest.remove("lantern")

    def test_count_is_direct_contents_only(self) -> None:
        # A chest holding a box holding a key counts one, not two. count() is
        # not a size of the tree, and the name says so.
        box = Container("box", "box", "a cardboard box")
        box.add(a_key())
        self.chest.add(box)
        self.assertEqual(1, self.chest.count())


class TestDeepSearch(unittest.TestCase):
    def setUp(self) -> None:
        self.chest = a_chest()
        self.box = Container("box", "box", "a cardboard box")
        self.box.add(a_key())
        self.chest.add(self.box)

    def test_shallow_find_does_not_see_through_a_container(self) -> None:
        self.assertIsNone(self.chest.find("brass_key"))

    def test_deep_find_sees_two_levels(self) -> None:
        found = self.chest.find_deep("brass_key")
        self.assertIsNotNone(found)

    def test_deep_find_sees_three_levels(self) -> None:
        # The level that catches a recursion which runs but discards its result.
        crate = Container("crate", "crate", "a wooden crate")
        crate.add(self.chest)
        self.assertIsNotNone(crate.find_deep("brass_key"))

    def test_deep_find_returns_none_when_truly_absent(self) -> None:
        self.assertIsNone(self.chest.find_deep("lantern"))


class TestContainerDescription(unittest.TestCase):
    def test_an_empty_container_says_so(self) -> None:
        self.assertIn("empty", a_chest().describe())

    def test_description_nests(self) -> None:
        chest = a_chest()
        box = Container("box", "box", "a cardboard box")
        box.add(a_key())
        chest.add(box)
        text = chest.describe()
        self.assertIn("a dented tin chest", text)
        self.assertIn("a cardboard box", text)
        self.assertIn("a small brass key", text)


class TestArgumentTypes(unittest.TestCase):
    def test_a_string_is_refused_where_a_class_is_expected(self) -> None:
        # Python does not enforce an annotation, so the method checks it.
        bad = "not an object"
        calls = [
            ("add item", lambda: a_chest().add(bad)),
        ]
        for label, call in calls:
            with self.subTest(label):
                with self.assertRaisesRegex(TypeError, "must be"):
                    call()


if __name__ == "__main__":
    unittest.main()
