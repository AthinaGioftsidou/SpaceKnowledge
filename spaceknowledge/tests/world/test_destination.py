"""Tests for Destination."""

import unittest

from spaceknowledge.world.door import Door
from spaceknowledge.world.item import PlainItem
from spaceknowledge.world.destination import Destination


def a_key() -> PlainItem:
    return PlainItem("brass_key", "brass key", "a small brass key")


class TestDestinationConstruction(unittest.TestCase):
    def test_empty_destination_id_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            Destination("", "Entrance Hall", "Cold and tiled.")

    def test_a_new_destination_holds_nothing(self) -> None:
        destination = Destination("hall", "Entrance Hall", "Cold and tiled.")
        self.assertEqual(0, destination.item_count())

    def test_the_description_is_readable(self) -> None:
        self.assertEqual("Cold and tiled.", Destination("hall", "Hall", "Cold and tiled.").description)


class TestDestinationItems(unittest.TestCase):
    def setUp(self) -> None:
        self.destination = Destination("hall", "Entrance Hall", "Cold and tiled.")

    def test_an_added_item_can_be_found(self) -> None:
        key = a_key()
        self.destination.add_item(key)
        self.assertIs(key, self.destination.find_item("brass_key"))

    def test_a_missing_item_is_none_not_an_error(self) -> None:
        # Absent is a legitimate answer to "is it here", so it returns None.
        # Compare remove_item below, where absent really is a caller mistake.
        self.assertIsNone(self.destination.find_item("lantern"))

    def test_duplicate_ids_are_refused(self) -> None:
        self.destination.add_item(a_key())
        with self.assertRaises(ValueError):
            self.destination.add_item(a_key())

    def test_removing_an_item_returns_it_and_empties_the_destination(self) -> None:
        self.destination.add_item(a_key())
        taken = self.destination.remove_item("brass_key")
        self.assertEqual("brass_key", taken.item_id)
        self.assertEqual(0, self.destination.item_count())

    def test_removing_something_absent_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.destination.remove_item("lantern")


class TestDestinationExits(unittest.TestCase):
    def setUp(self) -> None:
        self.hall = Destination("hall", "Entrance Hall", "Cold and tiled.")
        self.reception = Destination("reception", "Reception", "A long desk.")

    def test_an_exit_leads_to_the_destination(self) -> None:
        self.hall.add_exit("north", self.reception)
        self.assertIs(self.reception, self.hall.exit_to("north"))

    def test_exits_are_one_way_unless_stated_twice(self) -> None:
        # Deliberate: a one-way passage must be expressible, so add_exit does
        # not silently create the reverse.
        self.hall.add_exit("north", self.reception)
        self.assertIsNone(self.reception.exit_to("south"))

    def test_an_absent_exit_is_none(self) -> None:
        self.assertIsNone(self.hall.exit_to("up"))

    def test_exits_are_listed_alphabetically(self) -> None:
        self.hall.add_exit("north", self.reception)
        self.hall.add_exit("east", Destination("r2", "Library", "Shelves."))
        self.assertIn("Exits: east, north", self.hall.describe())


class TestDestinationDescription(unittest.TestCase):
    def test_description_lists_name_text_items_and_exits(self) -> None:
        destination = Destination("hall", "Entrance Hall", "Cold and tiled.")
        destination.add_item(a_key())
        destination.add_exit("north", Destination("reception", "Reception", "A long desk."))
        text = destination.describe()
        self.assertIn("Entrance Hall", text)
        self.assertIn("Cold and tiled.", text)
        self.assertIn("a small brass key", text)
        self.assertIn("Exits: north", text)


class TestDoors(unittest.TestCase):
    """Week 4. An exit and the door on it are two different questions."""

    def setUp(self) -> None:
        self.stairwell = Destination("stairwell", "Stairwell", "Iron stairs.")
        self.dome = Destination("dome", "Dome", "A telescope.")
        self.door = Door("hatch", "hatch", "brass_key")
        self.stairwell.add_exit("up", self.dome, self.door)

    def test_a_locked_exit_is_still_an_exit(self) -> None:
        # exit_to answers "is there a way", which stays true when it is shut.
        # Folding the two questions into one method is the design this rejects.
        self.assertIs(self.dome, self.stairwell.exit_to("up"))

    def test_the_door_is_reachable_from_the_destination(self) -> None:
        self.assertIs(self.door, self.stairwell.door_to("up"))

    def test_an_exit_with_no_door_has_none(self) -> None:
        self.stairwell.add_exit("south", self.dome)
        self.assertIsNone(self.stairwell.door_to("south"))

    def test_a_shut_door_is_described(self) -> None:
        self.assertIn("The hatch up is locked.", self.stairwell.describe())

    def test_an_open_door_is_not_described(self) -> None:
        # Silence is the right report for a door you can walk through. Telling
        # a player about every unlocked door buries the one that matters.
        self.door.unlock("brass_key")
        self.assertNotIn("hatch", self.stairwell.describe())


class TestArgumentTypes(unittest.TestCase):
    def test_a_string_is_refused_where_a_class_is_expected(self) -> None:
        # Python does not enforce an annotation, so the method checks it.
        destination = Destination("hall", "Entrance Hall", "Cold and tiled.")
        bad = "not an object"
        calls = [
            ("add_item item", lambda: destination.add_item(bad)),
            ("add_exit destination", lambda: destination.add_exit("north", bad)),
        ]
        calls.append(("add_exit door", lambda: destination.add_exit("north", destination, bad)))
        for label, call in calls:
            with self.subTest(label):
                with self.assertRaisesRegex(TypeError, "must be"):
                    call()


if __name__ == "__main__":
    unittest.main()
