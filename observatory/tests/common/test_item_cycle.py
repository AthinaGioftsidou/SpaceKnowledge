"""Tests for ItemCycle: four phases, three states, one loop."""

import unittest

from observatory.common.item_cycle import (
    BROKER,
    DONE,
    FLIGHT,
    OWNED,
    UNIVERSE,
    ItemCycle,
    OnGroundPhase,
    Phase,
)
from observatory.common.refusal import Refusal

MOVES = ("begin_drop", "finish_drop", "cancel_drop",
         "begin_pick", "finish_pick", "cancel_pick")

# How to reach each phase from the start, and which moves it allows.
PATHS = {
    "owned": [],
    "being_dropped": ["begin_drop"],
    "on_ground": ["begin_drop", "finish_drop"],
    "being_picked": ["begin_drop", "finish_drop", "begin_pick"],
}
ALLOWED = {
    "owned": {"begin_drop"},
    "being_dropped": {"finish_drop", "cancel_drop"},
    "on_ground": {"begin_pick"},
    "being_picked": {"finish_pick", "cancel_pick"},
}
OWNERS = {"owned": BROKER, "being_dropped": BROKER,
          "on_ground": UNIVERSE, "being_picked": UNIVERSE}
STATES = {"owned": OWNED, "being_dropped": FLIGHT,
          "on_ground": DONE, "being_picked": FLIGHT}


def at(phase_name: str) -> ItemCycle:
    cycle = ItemCycle("torch")
    for move in PATHS[phase_name]:
        assert getattr(cycle, move)() is None
    return cycle


class TestTheCycle(unittest.TestCase):
    def test_a_new_item_is_in_the_owned_phase_and_usable(self) -> None:
        cycle = ItemCycle("torch")
        self.assertEqual("owned", cycle.phase_name())
        self.assertEqual(OWNED, cycle.state())
        self.assertEqual(BROKER, cycle.owner())
        self.assertTrue(cycle.is_usable())

    def test_the_whole_loop_returns_to_owned_and_can_go_round_again(self) -> None:
        cycle = ItemCycle("torch")
        for _ in range(2):
            for move, expected in (("begin_drop", "being_dropped"),
                                   ("finish_drop", "on_ground"),
                                   ("begin_pick", "being_picked"),
                                   ("finish_pick", "owned")):
                self.assertIsNone(getattr(cycle, move)())
                self.assertEqual(expected, cycle.phase_name())

    def test_a_refused_drop_gives_the_item_back(self) -> None:
        cycle = at("being_dropped")
        self.assertIsNone(cycle.cancel_drop())
        self.assertEqual("owned", cycle.phase_name())

    def test_a_refused_pick_leaves_it_on_the_ground(self) -> None:
        cycle = at("being_picked")
        self.assertIsNone(cycle.cancel_pick())
        self.assertEqual("on_ground", cycle.phase_name())

    def test_each_phase_belongs_to_one_side(self) -> None:
        for name, owner in OWNERS.items():
            with self.subTest(phase=name):
                self.assertEqual(owner, at(name).owner())

    def test_each_phase_has_its_state(self) -> None:
        for name, state in STATES.items():
            with self.subTest(phase=name):
                self.assertEqual(state, at(name).state())

    def test_only_the_owned_state_is_usable(self) -> None:
        for name in PATHS:
            with self.subTest(phase=name):
                self.assertEqual(name == "owned", at(name).is_usable())


class TestEveryOtherMoveIsRefused(unittest.TestCase):
    def test_a_move_a_phase_does_not_allow_is_refused_and_changes_nothing(self) -> None:
        for name in PATHS:
            for move in MOVES:
                if move in ALLOWED[name]:
                    continue
                with self.subTest(phase=name, move=move):
                    cycle = at(name)
                    self.assertIsInstance(getattr(cycle, move)(), Refusal)
                    self.assertEqual(name, cycle.phase_name())

    def test_a_refusal_names_the_item_the_phase_and_what_to_do(self) -> None:
        text = at("being_dropped").begin_drop().describe()
        self.assertIn("torch", text)
        self.assertIn("being_dropped", text)
        self.assertIn("Next:", text)

    def test_the_advice_depends_on_the_phase(self) -> None:
        self.assertIn("wait", at("being_dropped").begin_drop().next_step)
        self.assertIn("ground", at("on_ground").begin_drop().next_step)


class TestArguments(unittest.TestCase):
    def test_an_item_may_start_on_the_ground(self) -> None:
        cycle = ItemCycle("rock", OnGroundPhase())
        self.assertEqual("on_ground", cycle.phase_name())
        self.assertIsNone(cycle.begin_pick())

    def test_bad_arguments_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            ItemCycle("")
        with self.assertRaisesRegex(TypeError, "must be"):
            ItemCycle("torch", "owned")  # type: ignore[arg-type]

    def test_the_abstract_phase_cannot_be_built(self) -> None:
        with self.assertRaises(TypeError):
            Phase()  # type: ignore[abstract]


if __name__ == "__main__":
    unittest.main()