"""Tests for Mission and MissionBook."""

import unittest
from typing import Any

from spaceknowledge.universe.missions import (
    COLLECTING,
    COMPLETE,
    QUESTION,
    Mission,
    MissionBook,
    MissionError,
)

RAW: dict[str, Any] = {
    "id": "ship", "title": "Upgrade the ship",
    "goal": {"resource": "iron", "amount": 5, "destination": "earth"},
    "briefing": "Mine iron.", "question": "Which metal?",
    "answers": ["iron", "rust"], "hint": "think", "success": "Well done.",
    "opens": {"destination": "earth", "direction": "mars"},
}


def a_mission(**changes: Any) -> Mission:
    fields: dict[str, Any] = dict(
        mission_id="ship", title="Upgrade the ship", resource="iron", amount=5, where="earth",
        briefing="Mine iron.", question="Which metal?", answers=("iron", "rust"),
        hint="think", success="Well done.", opens_from="earth", opens_direction="mars",
    )
    fields.update(changes)
    return Mission(**fields)


def a_book(amount: int = 5) -> MissionBook:
    return MissionBook([a_mission(amount=amount)])


class TestMission(unittest.TestCase):
    def test_the_key_is_named_after_the_mission(self) -> None:
        self.assertEqual("mission:ship", a_mission().key())

    def test_answers_are_matched_by_whole_words_ignoring_case_and_punctuation(self) -> None:
        for answer in ("iron", "Iron!", "it is rust", "the iron oxide", "  RUST  "):
            with self.subTest(answer=answer):
                self.assertTrue(a_mission().accepts(answer))

    def test_wrong_empty_partial_or_rambling_answers_are_refused(self) -> None:
        for answer in ("", "   ", "copper", "ironic", "x x x x x x x x x iron"):
            with self.subTest(answer=answer):
                self.assertFalse(a_mission().accepts(answer))

    def test_a_phrase_with_several_words_must_appear_in_order(self) -> None:
        mission = a_mission(answers=("iron oxide",))
        self.assertTrue(mission.accepts("it is iron oxide"))
        self.assertFalse(mission.accepts("oxide iron"))

    def test_bad_values_are_refused(self) -> None:
        for changes in ({"mission_id": ""}, {"title": " "}, {"where": ""}, {"hint": ""},
                        {"amount": 0}, {"amount": True}, {"amount": 1.5},
                        {"answers": ()}, {"answers": ("",)}, {"answers": ["iron"]},
                        {"opens_direction": ""}):
            with self.subTest(changes=changes):
                with self.assertRaises(MissionError):
                    a_mission(**changes)


class TestProgress(unittest.TestCase):
    def test_a_new_mission_is_collecting(self) -> None:
        book = a_book()
        self.assertEqual((COLLECTING, 0), (book.status("ship"), book.collected("ship")))

    def test_only_the_right_resource_in_the_right_place_counts(self) -> None:
        book = a_book()
        book.record_mining("mars", "iron", 3)
        book.record_mining("earth", "wood", 3)
        self.assertEqual(0, book.collected("ship"))
        book.record_mining("earth", "iron", 3)
        self.assertEqual(3, book.collected("ship"))

    def test_amounts_add_up_and_stop_at_the_goal(self) -> None:
        book = a_book()
        book.record_mining("earth", "iron", 3)
        book.record_mining("earth", "iron", 9)
        self.assertEqual((5, QUESTION), (book.collected("ship"), book.status("ship")))

    def test_there_is_nothing_to_answer_until_the_goal_is_reached(self) -> None:
        self.assertIsNone(a_book().answer("iron"))

    def test_a_wrong_answer_changes_nothing_and_the_right_one_completes(self) -> None:
        book = a_book()
        book.record_mining("earth", "iron", 5)
        mission, correct = book.answer("copper")
        self.assertFalse(correct)
        self.assertEqual(QUESTION, book.status("ship"))
        mission, correct = book.answer("iron")
        self.assertTrue(correct)
        self.assertEqual(("ship", COMPLETE), (mission.mission_id, book.status("ship")))

    def test_the_text_follows_the_status(self) -> None:
        book = a_book()
        mission = book.current()
        self.assertIn("Collected 0 of 5 iron.", book.text(mission))
        self.assertIn("Mine iron.", book.text(mission))
        book.record_mining("earth", "iron", 5)
        self.assertIn("Which metal?", book.text(mission))
        book.answer("iron")
        self.assertEqual("Well done.", book.text(mission))

    def test_the_current_mission_is_the_first_unfinished_one_then_the_last(self) -> None:
        book = MissionBook([a_mission(amount=2), a_mission(mission_id="second", amount=2)])
        self.assertEqual("ship", book.current().mission_id)
        book.record_mining("earth", "iron", 2)
        book.answer("iron")
        self.assertEqual("second", book.current().mission_id)
        book.record_mining("earth", "iron", 2)
        book.answer("rust")
        self.assertEqual("second", book.current().mission_id)
        self.assertEqual(COMPLETE, book.status("second"))

    def test_an_empty_book_has_no_current_mission(self) -> None:
        self.assertIsNone(MissionBook().current())
        self.assertIsNone(MissionBook().answer("iron"))

    def test_duplicate_ids_are_refused(self) -> None:
        with self.assertRaises(MissionError):
            MissionBook([a_mission(), a_mission()])


class TestSaving(unittest.TestCase):
    def test_progress_round_trips(self) -> None:
        book = a_book()
        book.record_mining("earth", "iron", 3)
        saved = book.snapshot()
        self.assertEqual({"ship": {"collected": 3, "complete": False}}, saved)
        again = a_book()
        again.restore(saved)
        self.assertEqual(3, again.collected("ship"))

    def test_the_snapshot_is_a_copy(self) -> None:
        book = a_book()
        book.snapshot()["ship"]["collected"] = 99
        self.assertEqual(0, book.collected("ship"))

    def test_progress_that_cannot_be_trusted_is_refused_and_changes_nothing(self) -> None:
        book = a_book()
        for saved in ({"nope": {"collected": 0, "complete": False}},
                      {"ship": {"collected": -1, "complete": False}},
                      {"ship": {"collected": 6, "complete": False}},
                      {"ship": {"collected": True, "complete": False}},
                      {"ship": {"collected": 1, "complete": "no"}},
                      {"ship": {"collected": 1}}):
            with self.subTest(saved=saved):
                with self.assertRaises(MissionError):
                    book.restore(saved)
                self.assertEqual(0, book.collected("ship"))


class TestFromData(unittest.TestCase):
    def test_a_good_spec_is_read(self) -> None:
        mission = MissionBook.from_raw({"missions": [RAW]}).current()
        self.assertEqual(("ship", "iron", 5, "earth", ("iron", "rust"), "earth", "mars"),
                         (mission.mission_id, mission.resource, mission.amount, mission.where,
                          mission.answers, mission.opens_from, mission.opens_direction))

    def test_no_missions_section_gives_an_empty_book(self) -> None:
        self.assertIsNone(MissionBook.from_raw({}).current())

    def test_bad_data_is_refused(self) -> None:
        bad: list[Any] = [
            {"missions": "ship"}, {"missions": ["ship"]},
            {"missions": [{**RAW, "extra": 1}]},
            {"missions": [{**RAW, "goal": "iron"}]},
            {"missions": [{**RAW, "goal": {**RAW["goal"], "amount": "5"}}]},
            {"missions": [{**RAW, "answers": "iron"}]},
            {"missions": [{**RAW, "opens": {"destination": "earth"}}]},
        ]
        bad += [{"missions": [{k: v for k, v in RAW.items() if k != key}]} for key in RAW]
        for raw in bad:
            with self.subTest(raw=str(raw)[:60]):
                with self.assertRaises(MissionError):
                    MissionBook.from_raw(raw)


if __name__ == "__main__":
    unittest.main()