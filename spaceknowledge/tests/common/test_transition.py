"""Tests for Transition: the three phases every action goes through."""

import unittest
from dataclasses import FrozenInstanceError

from spaceknowledge.common.refusal import Refusal
from spaceknowledge.common.transition import ADD, DROP, MINE, Transition, TransitionKind

KINDS = (DROP, MINE, ADD)


class TestKinds(unittest.TestCase):
    def test_each_kind_has_its_own_words(self) -> None:
        self.assertEqual(("drop", "owned", "being_dropped", "dropped"),
                         (DROP.verb, DROP.start, DROP.in_flight, DROP.done))
        self.assertEqual(("mine", "available", "being_mined", "in_bag"),
                         (MINE.verb, MINE.start, MINE.in_flight, MINE.done))
        self.assertEqual(("add", "wanted", "being_added", "added"),
                         (ADD.verb, ADD.start, ADD.in_flight, ADD.done))

    def test_an_empty_word_is_refused(self) -> None:
        for words in (("", "a", "b", "c"), ("v", "", "b", "c"),
                      ("v", "a", "", "c"), ("v", "a", "b", "")):
            with self.subTest(words=words):
                with self.assertRaises(ValueError):
                    TransitionKind(*words)

    def test_two_phases_with_the_same_name_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            TransitionKind("drop", "owned", "owned", "dropped")

    def test_a_kind_cannot_be_changed(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            DROP.verb = "throw"  # type: ignore[misc]


class TestTheNormalFlow(unittest.TestCase):
    def test_every_kind_starts_at_its_start_word(self) -> None:
        for kind in KINDS:
            with self.subTest(kind=kind.verb):
                transition = Transition(kind, "thing")
                self.assertEqual(kind.start, transition.phase_name())
                self.assertTrue(transition.is_at_start())

    def test_begin_then_confirm_reaches_done(self) -> None:
        for kind in KINDS:
            with self.subTest(kind=kind.verb):
                transition = Transition(kind, "thing")
                self.assertIsNone(transition.begin())
                self.assertEqual(kind.in_flight, transition.phase_name())
                self.assertTrue(transition.is_in_flight())
                self.assertIsNone(transition.confirm())
                self.assertEqual(kind.done, transition.phase_name())
                self.assertTrue(transition.is_done())

    def test_cancel_goes_back_to_the_start_and_may_begin_again(self) -> None:
        for kind in KINDS:
            with self.subTest(kind=kind.verb):
                transition = Transition(kind, "thing")
                transition.begin()
                self.assertIsNone(transition.cancel())
                self.assertTrue(transition.is_at_start())
                self.assertIsNone(transition.begin())
                self.assertTrue(transition.is_in_flight())


class TestEverythingElseIsRefused(unittest.TestCase):
    def test_at_the_start_only_begin_is_allowed(self) -> None:
        for kind in KINDS:
            with self.subTest(kind=kind.verb):
                transition = Transition(kind, "thing")
                self.assertIsInstance(transition.confirm(), Refusal)
                self.assertIsInstance(transition.cancel(), Refusal)
                self.assertEqual(kind.start, transition.phase_name())

    def test_in_flight_a_second_begin_is_refused_and_nothing_changes(self) -> None:
        for kind in KINDS:
            with self.subTest(kind=kind.verb):
                transition = Transition(kind, "thing")
                transition.begin()
                self.assertIsInstance(transition.begin(), Refusal)
                self.assertEqual(kind.in_flight, transition.phase_name())

    def test_done_is_final(self) -> None:
        for kind in KINDS:
            with self.subTest(kind=kind.verb):
                transition = Transition(kind, "thing")
                transition.begin()
                transition.confirm()
                for move in (transition.begin, transition.confirm, transition.cancel):
                    self.assertIsInstance(move(), Refusal)
                    self.assertEqual(kind.done, transition.phase_name())

    def test_a_refusal_names_the_subject_the_phase_and_what_to_do(self) -> None:
        transition = Transition(MINE, "iron")
        transition.begin()
        text = transition.begin().describe()
        self.assertIn("iron", text)
        self.assertIn("being_mined", text)
        self.assertIn("Next:", text)

    def test_the_advice_depends_on_the_phase(self) -> None:
        transition = Transition(DROP, "torch")
        self.assertIn("begin", transition.confirm().next_step)
        transition.begin()
        self.assertIn("wait", transition.begin().next_step)
        transition.confirm()
        self.assertIn("finished", transition.begin().next_step)


class TestArguments(unittest.TestCase):
    def test_bad_arguments_are_refused(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            Transition("drop", "torch")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            Transition(DROP, "")


if __name__ == "__main__":
    unittest.main()