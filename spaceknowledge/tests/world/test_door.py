"""Tests for Door and its three states.

Read as a transition table. Every cell is either a legal move with a named
result, or a refusal, and there is a test for both kinds.
"""

import unittest

from spaceknowledge.world.door import (
    BrokenState,
    Door,
    DoorState,
    LockedState,
    UnlockedState,
)


def a_door(state: DoorState | None = None) -> Door:
    return Door("hatch", "hatch", "brass_key", state)


# ##01
class TestConstruction(unittest.TestCase):
    def test_a_door_starts_locked(self) -> None:
        self.assertEqual("locked", a_door().state_name())

    def test_a_door_may_start_unlocked(self) -> None:
        self.assertEqual("unlocked", a_door(UnlockedState()).state_name())

    def test_a_door_with_no_key_is_refused(self) -> None:
        # A door nothing can ever open is not a puzzle, it is a wall, and if
        # you wanted a wall you would not have written an exit.
        with self.assertRaises(ValueError):
            Door("hatch", "hatch", "")

    def test_a_door_with_no_name_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            Door("hatch", "", "brass_key")


# ##02
class TestLocked(unittest.TestCase):
    def setUp(self) -> None:
        self.door = a_door()

    def test_locked_is_not_passable(self) -> None:
        self.assertFalse(self.door.is_passable())

    def test_the_right_key_unlocks_it(self) -> None:
        self.assertIn("unlocks", self.door.unlock("brass_key"))
        self.assertEqual("unlocked", self.door.state_name())

    def test_the_wrong_key_does_not(self) -> None:
        # Both halves. A refusal that still changes the state is the defect
        # this week's exercise plants.
        self.assertIn("does not fit", self.door.unlock("crowbar"))
        self.assertEqual("locked", self.door.state_name())

    def test_no_key_at_all_does_not(self) -> None:
        self.assertIn("does not fit", self.door.unlock(""))
        self.assertEqual("locked", self.door.state_name())

    def test_locking_a_locked_door_is_refused(self) -> None:
        self.assertIn("is locked", self.door.lock("brass_key"))
        self.assertEqual("locked", self.door.state_name())

    def test_forcing_it_breaks_it(self) -> None:
        self.assertIn("ruined", self.door.force())
        self.assertEqual("broken", self.door.state_name())


class TestUnlocked(unittest.TestCase):
    def setUp(self) -> None:
        self.door = a_door(UnlockedState())

    def test_unlocked_is_passable(self) -> None:
        self.assertTrue(self.door.is_passable())

    def test_the_right_key_locks_it_again(self) -> None:
        self.assertIn("locks", self.door.lock("brass_key"))
        self.assertEqual("locked", self.door.state_name())

    def test_the_wrong_key_does_not(self) -> None:
        self.assertIn("does not fit", self.door.lock("crowbar"))
        self.assertEqual("unlocked", self.door.state_name())

    def test_unlocking_an_unlocked_door_is_refused(self) -> None:
        self.assertIn("is unlocked", self.door.unlock("brass_key"))
        self.assertEqual("unlocked", self.door.state_name())

    def test_forcing_an_unlocked_door_does_nothing(self) -> None:
        # Force is only defined on Locked. Everywhere else it inherits the
        # refusing default, which is why UnlockedState says nothing about it.
        self.door.force()
        self.assertEqual("unlocked", self.door.state_name())


# ##02
class TestBrokenIsTerminal(unittest.TestCase):
    """The reason three states beat two booleans.

    Broken is not a flag that happens to be set. It is a place with no way out,
    and these four tests are the whole of that guarantee.
    """

    def setUp(self) -> None:
        self.door = a_door(BrokenState())

    def test_broken_is_not_passable(self) -> None:
        self.assertFalse(self.door.is_passable())

    def test_the_key_no_longer_helps(self) -> None:
        self.door.unlock("brass_key")
        self.assertEqual("broken", self.door.state_name())

    def test_it_cannot_be_locked(self) -> None:
        self.door.lock("brass_key")
        self.assertEqual("broken", self.door.state_name())

    def test_forcing_it_again_changes_nothing(self) -> None:
        self.door.force()
        self.assertEqual("broken", self.door.state_name())

    def test_the_refusal_says_why(self) -> None:
        # Diagnostics are part of the contract. "The hatch is broken" would be
        # true and useless; a player needs to know to stop trying.
        self.assertIn("Nothing will move it now", self.door.refusal())


class TestTheTransitionsAreReachable(unittest.TestCase):
    """End to end through the state graph, using no constructor shortcuts."""

    def test_locked_to_unlocked_to_locked(self) -> None:
        door = a_door()
        door.unlock("brass_key")
        door.lock("brass_key")
        self.assertEqual("locked", door.state_name())

    def test_locked_to_broken_is_one_way(self) -> None:
        door = a_door()
        door.force()
        door.unlock("brass_key")
        door.force()
        door.lock("brass_key")
        self.assertEqual("broken", door.state_name())

    def test_you_cannot_reach_broken_from_unlocked(self) -> None:
        door = a_door()
        door.unlock("brass_key")
        door.force()
        self.assertEqual("unlocked", door.state_name())


class TestStatesHoldNoDoorData(unittest.TestCase):
    def test_one_state_object_serves_two_doors(self) -> None:
        """States are behaviour, not data, so they are interchangeable.

        This is why `Door` may hand `self` to the state and why swapping in a
        fresh `LockedState()` is not a bug. It is also the fact week 7 leans
        on when it argues about sharing single instances.
        """
        shared = LockedState()
        front, back = a_door(shared), Door("side", "side door", "iron_key", shared)
        self.assertIn("unlocks", front.unlock("brass_key"))
        self.assertIn("unlocks", back.unlock("iron_key"))
        # Each door moved on independently. The shared object was never mutated.
        self.assertEqual("unlocked", front.state_name())
        self.assertEqual("unlocked", back.state_name())


class TestArgumentTypes(unittest.TestCase):
    def test_a_string_is_refused_where_a_class_is_expected(self) -> None:
        # Python does not enforce an annotation, so the method checks it.
        bad = "not an object"
        calls = [
            ("Door state", lambda: Door("hatch", "hatch", "brass_key", bad)),
            ("DoorState.refusal door", lambda: LockedState().refusal(bad)),
            ("DoorState.unlock door", lambda: UnlockedState().unlock(bad, "brass_key")),
            ("DoorState.lock door", lambda: LockedState().lock(bad, "brass_key")),
            ("DoorState.force door", lambda: UnlockedState().force(bad)),
            ("LockedState.unlock door", lambda: LockedState().unlock(bad, "brass_key")),
            ("LockedState.force door", lambda: LockedState().force(bad)),
            ("UnlockedState.lock door", lambda: UnlockedState().lock(bad, "brass_key")),
            ("BrokenState.refusal door", lambda: BrokenState().refusal(bad)),
        ]
        for label, call in calls:
            with self.subTest(label):
                with self.assertRaisesRegex(TypeError, "must be"):
                    call()


if __name__ == "__main__":
    unittest.main()
