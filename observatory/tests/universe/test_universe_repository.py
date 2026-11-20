"""Tests for the Universe's repositories: in memory and JSON on disk."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from observatory.common.messages import ItemInfo, Response
from observatory.common.refusal import Refusal
from observatory.universe.universe_repository import (
    CorruptStateError,
    InMemoryUniverseRepository,
    JsonUniverseRepository,
    UniverseRepository,
    UniverseState,
)


def a_state() -> UniverseState:
    refusal = Refusal("mine iron", "only 1 left", "ask for 1")
    return UniverseState(
        {"ada": "earth"},
        {"earth": {"iron": 7, "water": 0}},
        {"earth": ["torch"]},
        {"op1": Response("op1"), "op2": Response("op2", refusal)},
    )


def summary(state: UniverseState) -> tuple:
    """Responses have no equality of their own, so compare what they say."""
    answers = {}
    for op_id, response in state.answers.items():
        answers[op_id] = response.refusal.describe() if response.refusal else "ok"
    return state.locations, state.stock, state.dropped, answers


class TestInMemory(unittest.TestCase):
    def test_nothing_saved_loads_as_none(self) -> None:
        self.assertIsNone(InMemoryUniverseRepository().load())

    def test_what_was_saved_is_loaded(self) -> None:
        repository = InMemoryUniverseRepository()
        repository.save(a_state())
        self.assertEqual(summary(a_state()), summary(repository.load()))

    def test_changing_the_loaded_copy_does_not_change_the_store(self) -> None:
        repository = InMemoryUniverseRepository()
        repository.save(a_state())
        loaded = repository.load()
        loaded.locations["ada"] = "mars"
        loaded.stock["earth"]["iron"] = 999
        loaded.dropped["earth"].clear()
        self.assertEqual(summary(a_state()), summary(repository.load()))

    def test_the_abstract_repository_cannot_be_built(self) -> None:
        with self.assertRaises(TypeError):
            UniverseRepository()  # type: ignore[abstract]

    def test_a_string_is_refused_where_a_state_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            InMemoryUniverseRepository().save("state")  # type: ignore[arg-type]


def document(**changes: object) -> str:
    base: dict[str, object] = {
        "version": 1, "locations": {}, "stock": {}, "dropped": {}, "answers": {},
    }
    base.update(changes)
    return json.dumps(base)


class TestJson(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = self.directory / "universe.json"
        self.repository = JsonUniverseRepository(self.path)

    def test_a_missing_file_loads_as_none(self) -> None:
        self.assertIsNone(self.repository.load())

    def test_what_was_saved_is_loaded(self) -> None:
        self.repository.save(a_state())
        self.assertEqual(summary(a_state()), summary(self.repository.load()))

    def test_a_refusal_keeps_all_three_parts(self) -> None:
        self.repository.save(a_state())
        refusal = self.repository.load().answers["op2"].refusal
        self.assertEqual(("mine iron", "only 1 left", "ask for 1"),
                         (refusal.what, refusal.why, refusal.next_step))

    def test_saving_writes_a_version_1_file_and_no_temporary_file(self) -> None:
        self.repository.save(a_state())
        self.assertEqual(1, json.loads(self.path.read_text(encoding="utf-8"))["version"])
        self.assertEqual(["universe.json"], sorted(item.name for item in self.directory.iterdir()))

    def test_a_minimal_valid_document_loads(self) -> None:
        self.path.write_text(document(), encoding="utf-8")
        self.assertEqual(({}, {}, {}, {}), summary(self.repository.load()))

    def test_a_file_that_cannot_be_trusted_is_refused(self) -> None:
        refusal = {"what": "a", "why": "b", "next_step": "c"}
        bad_files = [
            "{not json",
            "[]",
            '{"version": 1}',
            document(version=2),
            document(version=True),
            document(locations=[]),
            document(locations={"": "earth"}),
            document(locations={"ada": ""}),
            document(locations={"ada": 5}),
            document(stock={"earth": []}),
            document(stock={"earth": {"iron": -1}}),
            document(stock={"earth": {"iron": 1.5}}),
            document(stock={"earth": {"iron": True}}),
            document(stock={"earth": {"": 1}}),
            document(dropped={"earth": "torch"}),
            document(dropped={"earth": ["torch", "torch"]}),
            document(dropped={"earth": [""]}),
            document(answers={"": {"ok": True}}),
            document(answers={"op1": {"ok": "yes"}}),
            document(answers={"op1": {"ok": False}}),
            document(answers={"op1": {"ok": False, "refusal": {**refusal, "why": ""}}}),
        ]
        for text in bad_files:
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(CorruptStateError):
                    self.repository.load()

    def test_a_string_is_refused_where_a_path_or_state_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            JsonUniverseRepository("universe.json")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            self.repository.save("state")  # type: ignore[arg-type]

class TestItemsInAnswers(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = self.directory / "universe.json"
        self.repository = JsonUniverseRepository(self.path)

    def test_an_answer_with_items_round_trips_in_both_repositories(self) -> None:
        info = ItemInfo("torch", "torch", "a rubber torch")
        state = UniverseState({}, {}, {}, {"op1": Response("op1", items=(info,))})
        for repository in (self.repository, InMemoryUniverseRepository()):
            with self.subTest(repository=type(repository).__name__):
                repository.save(state)
                self.assertEqual((info,), repository.load().answers["op1"].items)

    def test_bad_items_in_an_answer_are_refused(self) -> None:
        good = {"id": "i", "name": "n", "description": "d"}
        for items in ("torch", ["torch"], [{"id": "", "name": "n", "description": "d"}],
                      [{"id": "i", "name": "n"}], [{**good, "name": 5}]):
            with self.subTest(items=items):
                self.path.write_text(
                    document(answers={"op1": {"ok": True, "items": items}}), encoding="utf-8")
                with self.assertRaises(CorruptStateError):
                    self.repository.load()

class TestNames(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = self.directory / "universe.json"
        self.repository = JsonUniverseRepository(self.path)

    def test_names_round_trip_in_both_repositories(self) -> None:
        state = UniverseState({}, {}, {"earth": ["torch-1"]}, {}, {"torch-1": "torch"})
        for repository in (self.repository, InMemoryUniverseRepository()):
            with self.subTest(repository=type(repository).__name__):
                repository.save(state)
                self.assertEqual({"torch-1": "torch"}, repository.load().names)

    def test_a_file_written_before_names_existed_still_loads(self) -> None:
        self.path.write_text(document(), encoding="utf-8")
        self.assertEqual({}, self.repository.load().names)

    def test_bad_names_are_refused(self) -> None:
        for names in ([], {"": "torch"}, {"t": ""}, {"t": 5}):
            with self.subTest(names=names):
                self.path.write_text(document(names=names), encoding="utf-8")
                with self.assertRaises(CorruptStateError):
                    self.repository.load()


if __name__ == "__main__":
    unittest.main()