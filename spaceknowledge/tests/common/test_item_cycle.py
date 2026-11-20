"""Tests for ItemCycle: three states, two processes, one loop."""

import unittest
from dataclasses import FrozenInstanceError

from spaceknowledge.common.item_cycle import (
    BROKER,
    DONE,
    DROP,
    FLIGHT,
    OWNED,
    PICK,
    UNIVERSE,
    ItemCycle,
    Process,
    State,
)
from spaceknowledge.common.refusal import Refusal

MOVES = ("begin", "finish", "cancel")
POSITIONS = [(p, s) for p in (DROP, PICK) for s in (OWNED, FLIGHT, DONE)]

HOLDERS = {
    ("drop", OWNED): BROKER, ("drop", FLIGHT): BROKER, ("drop", DONE): UNIVERSE,
    ("pick", OWNED): UNIVERSE, ("pick", FLIGHT): UNIVERSE, ("pick", DONE): BROKER,
}
USABLE = {("drop", OWNED), ("pick", DONE)}


def other(process: Process) -> Process:
    return PICK if process == DROP else DROP


def at(process: Process, state: str) -> ItemCycle:
    """An item standing at `state` of `process`."""
    cycle = ItemCycle("torch", process)
    if state in (FLIGHT, DONE):
        assert cycle.begin(process) is None
    if state == DONE:
        assert cycle.finish(process) is None
    return cycle


def allowed(process: Process, state: str) -> list[tuple[str, Process]]:
    """The only moves that work at each position."""
    if state == OWNED:
        return [("begin", process)]
    if state == FLIGHT:
        return [("finish", process), ("cancel", process)]
    return [("begin", other(process))]


class TestProcesses(unittest.TestCase):
    def test_who_holds_the_item_in_each_state(self) -> None:
        for process, state in POSITIONS:
            with self.subTest(process=process.name, state=state):
                self.assertEqual(HOLDERS[(process.name, state)], process.holder(state))

    def test_an_empty_word_or_an_unknown_holder_is_refused(self) -> None:
        bad = [
            ("", "drop", BROKER, BROKER, UNIVERSE, "a", "b"),
            ("drop", "", BROKER, BROKER, UNIVERSE, "a", "b"),
            ("drop", "drop", BROKER, BROKER, UNIVERSE, "", "b"),
            ("drop", "drop", BROKER, BROKER, UNIVERSE, "a", ""),
            ("drop", "drop", "nobody", BROKER, UNIVERSE, "a", "b"),
        ]
        for fields in bad:
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    Process(*fields)

    def test_a_process_cannot_be_changed(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            DROP.name = "throw"  # type: ignore[misc]


class TestTheCycle(unittest.TestCase):
    def test_a_new_item_is_owned_by_the_broker_and_usable(self) -> None:
        cycle = ItemCycle("torch")
        self.assertEqual(("drop", OWNED, BROKER),
                         (cycle.process_name(), cycle.state(), cycle.holder()))
        self.assertTrue(cycle.is_usable())

    def test_the_whole_loop_returns_to_the_broker_and_can_go_round_again(self) -> None:
        steps = [
            ("begin", DROP, "drop", FLIGHT, BROKER),
            ("finish", DROP, "drop", DONE, UNIVERSE),
            ("begin", PICK, "pick", FLIGHT, UNIVERSE),
            ("finish", PICK, "pick", DONE, BROKER),
        ]
        cycle = ItemCycle("torch")
        for _ in range(2):
            for move, process, name, state, holder in steps:
                self.assertIsNone(getattr(cycle, move)(process))
                self.assertEqual((name, state, holder),
                                 (cycle.process_name(), cycle.state(), cycle.holder()))

    def test_a_refused_drop_gives_the_item_back(self) -> None:
        cycle = at(DROP, FLIGHT)
        self.assertIsNone(cycle.cancel(DROP))
        self.assertEqual(("drop", OWNED, BROKER),
                         (cycle.process_name(), cycle.state(), cycle.holder()))

    def test_a_refused_pick_leaves_it_on_the_ground(self) -> None:
        cycle = at(PICK, FLIGHT)
        self.assertIsNone(cycle.cancel(PICK))
        self.assertEqual(("pick", OWNED, UNIVERSE),
                         (cycle.process_name(), cycle.state(), cycle.holder()))

    def test_on_the_ground_is_the_end_of_the_drop_and_the_start_of_the_pick(self) -> None:
        dropped = at(DROP, DONE)
        waiting = ItemCycle("torch", PICK)
        self.assertEqual(dropped.holder(), waiting.holder())
        self.assertEqual(UNIVERSE, waiting.holder())

    def test_an_item_may_start_on_the_ground(self) -> None:
        cycle = ItemCycle("rock", PICK)
        self.assertFalse(cycle.is_usable())
        self.assertIsNone(cycle.begin(PICK))

    def test_only_an_item_the_broker_holds_at_rest_is_usable(self) -> None:
        for process, state in POSITIONS:
            with self.subTest(process=process.name, state=state):
                self.assertEqual((process.name, state) in USABLE, at(process, state).is_usable())


class TestEveryOtherMoveIsRefused(unittest.TestCase):
    def test_a_move_a_position_does_not_allow_is_refused_and_changes_nothing(self) -> None:
        for process, state in POSITIONS:
            for move in MOVES:
                for wanted in (DROP, PICK):
                    if (move, wanted) in allowed(process, state):
                        continue
                    with self.subTest(process=process.name, state=state,
                                      move=move, wanted=wanted.name):
                        cycle = at(process, state)
                        self.assertIsInstance(getattr(cycle, move)(wanted), Refusal)
                        self.assertEqual((process.name, state),
                                         (cycle.process_name(), cycle.state()))

    def test_a_refusal_names_the_item_the_state_the_holder_and_what_to_do(self) -> None:
        text = at(DROP, FLIGHT).begin(DROP).describe()
        for part in ("torch", "flight", "broker", "Next:"):
            self.assertIn(part, text)

    def test_the_advice_depends_on_the_state_and_the_process(self) -> None:
        self.assertIn("wait", at(DROP, FLIGHT).begin(DROP).next_step)
        self.assertIn("ground", at(DROP, DONE).begin(DROP).next_step)
        self.assertIn("drop", at(PICK, DONE).begin(PICK).next_step)


class TestArguments(unittest.TestCase):
    def test_bad_arguments_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            ItemCycle("")
        with self.assertRaisesRegex(TypeError, "must be"):
            ItemCycle("torch", "drop")  # type: ignore[arg-type]
        cycle = ItemCycle("torch")
        for move in MOVES:
            with self.subTest(move=move):
                with self.assertRaisesRegex(TypeError, "must be"):
                    getattr(cycle, move)("drop")

    def test_the_abstract_state_cannot_be_built(self) -> None:
        with self.assertRaises(TypeError):
            State()  # type: ignore[abstract]


if __name__ == "__main__":
    unittest.main()