"""Tests for Room."""

import unittest

from observatory.world.door import Door
from observatory.world.item import PlainItem
from observatory.world.room import Room


def a_key() -> PlainItem:
    return PlainItem("brass_key", "brass key", "a small brass key")


class TestRoomConstruction(unittest.TestCase):
    def test_empty_room_id_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            Room("", "Entrance Hall", "Cold and tiled.")

    def test_a_new_room_holds_nothing(self) -> None:
        room = Room("hall", "Entrance Hall", "Cold and tiled.")
        self.assertEqual(0, room.item_count())


class TestRoomItems(unittest.TestCase):
    def setUp(self) -> None:
        self.room = Room("hall", "Entrance Hall", "Cold and tiled.")

    def test_an_added_item_can_be_found(self) -> None:
        key = a_key()
        self.room.add_item(key)
        self.assertIs(key, self.room.find_item("brass_key"))

    def test_a_missing_item_is_none_not_an_error(self) -> None:
        # Absent is a legitimate answer to "is it here", so it returns None.
        # Compare remove_item below, where absent really is a caller mistake.
        self.assertIsNone(self.room.find_item("lantern"))

    def test_duplicate_ids_are_refused(self) -> None:
        self.room.add_item(a_key())
        with self.assertRaises(ValueError):
            self.room.add_item(a_key())

    def test_removing_an_item_returns_it_and_empties_the_room(self) -> None:
        self.room.add_item(a_key())
        taken = self.room.remove_item("brass_key")
        self.assertEqual("brass_key", taken.item_id)
        self.assertEqual(0, self.room.item_count())

    def test_removing_something_absent_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.room.remove_item("lantern")


class TestRoomExits(unittest.TestCase):
    def setUp(self) -> None:
        self.hall = Room("hall", "Entrance Hall", "Cold and tiled.")
        self.reception = Room("reception", "Reception", "A long desk.")

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
        self.hall.add_exit("east", Room("r2", "Library", "Shelves."))
        # --- INSTRUCTOR SWAP 01 : week 01 : defect in the TEST ---------------
        # The broken assertion contradicts this test's own name, which is the
        # intended tell. See dev_notes.txt Part 1, week 1.
        #
        #   self.assertIn("Exits: north, east", self.hall.describe())  # BROKEN
        #
        self.assertIn("Exits: east, north", self.hall.describe())  # CORRECT
        # --- END INSTRUCTOR SWAP 01 ------------------------------------------


class TestRoomDescription(unittest.TestCase):
    def test_description_lists_name_text_items_and_exits(self) -> None:
        room = Room("hall", "Entrance Hall", "Cold and tiled.")
        room.add_item(a_key())
        room.add_exit("north", Room("reception", "Reception", "A long desk."))
        text = room.describe()
        self.assertIn("Entrance Hall", text)
        self.assertIn("Cold and tiled.", text)
        self.assertIn("a small brass key", text)
        self.assertIn("Exits: north", text)


class TestDoors(unittest.TestCase):
    """Week 4. An exit and the door on it are two different questions."""

    def setUp(self) -> None:
        self.stairwell = Room("stairwell", "Stairwell", "Iron stairs.")
        self.dome = Room("dome", "Dome", "A telescope.")
        self.door = Door("hatch", "hatch", "brass_key")
        self.stairwell.add_exit("up", self.dome, self.door)

    def test_a_locked_exit_is_still_an_exit(self) -> None:
        # exit_to answers "is there a way", which stays true when it is shut.
        # Folding the two questions into one method is the design this rejects.
        self.assertIs(self.dome, self.stairwell.exit_to("up"))

    def test_the_door_is_reachable_from_the_room(self) -> None:
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
        room = Room("hall", "Entrance Hall", "Cold and tiled.")
        bad = "not an object"
        calls = [
            ("add_item item", lambda: room.add_item(bad)),
            ("add_exit destination", lambda: room.add_exit("north", bad)),
        ]
        calls.append(("add_exit door", lambda: room.add_exit("north", room, bad)))
        for label, call in calls:
            with self.subTest(label):
                with self.assertRaisesRegex(TypeError, "must be"):
                    call()


if __name__ == "__main__":
    unittest.main()
