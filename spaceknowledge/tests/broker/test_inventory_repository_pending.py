"""Tests for pending operations in the inventory repositories."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from spaceknowledge.broker.inventory_repository import (
    CorruptStoreError,
    InMemoryInventoryRepository,
    JsonInventoryRepository,
)
from spaceknowledge.common.messages import Request

RECORDS = {"ada": [("torch", "torch")], "bob": []}
MINE = Request("op1", "mine", "ada", "iron", 3)
DROP = Request("op2", "add_item", "ada", "torch")


def describe(requests: list[Request]) -> list[tuple]:
    """Requests have no equality of their own, so compare what they say."""
    return [(r.op_id, r.action, r.player_id, r.item_id, r.amount) for r in requests]


class TestInMemoryPending(unittest.TestCase):
    def test_nothing_saved_means_nothing_pending(self) -> None:
        self.assertEqual([], InMemoryInventoryRepository().load_pending())

    def test_saved_pending_operations_are_loaded_in_order(self) -> None:
        repository = InMemoryInventoryRepository()
        repository.save(RECORDS, None, [MINE, DROP])
        self.assertEqual(describe([MINE, DROP]), describe(repository.load_pending()))

    def test_saving_without_pending_clears_it(self) -> None:
        repository = InMemoryInventoryRepository()
        repository.save(RECORDS, None, [MINE])
        repository.save(RECORDS)
        self.assertEqual([], repository.load_pending())

    def test_an_operation_for_an_unknown_player_is_refused_and_old_data_kept(self) -> None:
        repository = InMemoryInventoryRepository()
        repository.save(RECORDS, None, [MINE])
        stranger = Request("op3", "mine", "eve", "iron", 1)
        with self.assertRaises(ValueError):
            repository.save(RECORDS, None, [stranger])
        self.assertEqual(describe([MINE]), describe(repository.load_pending()))

    def test_the_same_op_id_twice_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            InMemoryInventoryRepository().save(RECORDS, None, [MINE, MINE])


class TestJsonPending(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = self.directory / "players.json"
        self.repository = JsonInventoryRepository(self.path)

    def test_a_missing_file_has_nothing_pending(self) -> None:
        self.assertEqual([], self.repository.load_pending())

    def test_everything_round_trips_together(self) -> None:
        self.repository.save(RECORDS, None, [MINE, DROP])
        self.assertEqual(RECORDS, self.repository.load())
        self.assertEqual(describe([MINE, DROP]), describe(self.repository.load_pending()))

    def test_saving_writes_a_version_3_file(self) -> None:
        self.repository.save(RECORDS, None, [MINE])
        self.assertEqual(3, json.loads(self.path.read_text(encoding="utf-8"))["version"])

    def test_a_version_2_file_is_still_read_with_nothing_pending(self) -> None:
        self.path.write_text(
            '{"version": 2, "players": {"ada": {"items": [], "resources": {}}}}',
            encoding="utf-8",
        )
        self.assertEqual({"ada": []}, self.repository.load())
        self.assertEqual([], self.repository.load_pending())

    def test_an_operation_for_an_unknown_player_is_refused_and_the_file_kept(self) -> None:
        self.repository.save(RECORDS, None, [MINE])
        stranger = Request("op3", "mine", "eve", "iron", 1)
        with self.assertRaises(ValueError):
            self.repository.save(RECORDS, None, [stranger])
        self.assertEqual(describe([MINE]), describe(self.repository.load_pending()))
        self.assertEqual(["players.json"], sorted(item.name for item in self.directory.iterdir()))

    def test_a_version_3_file_that_cannot_be_trusted_is_refused(self) -> None:
        good = {"op_id": "op1", "action": "mine", "player_id": "ada", "item_id": "iron", "amount": 3}

        def document(pending: object) -> str:
            return json.dumps({
                "version": 3,
                "players": {"ada": {"items": [], "resources": {}}},
                "pending": pending,
            })

        without_amount = {key: value for key, value in good.items() if key != "amount"}
        bad_files = [
            '{"version": 3, "players": {}}',
            document("op1"),
            document(["op1"]),
            document([{**good, "op_id": ""}]),
            document([{**good, "action": 5}]),
            document([{**good, "player_id": "eve"}]),
            document([{**good, "item_id": ""}]),
            document([{**good, "amount": 0}]),
            document([{**good, "amount": 1.5}]),
            document([{**good, "amount": True}]),
            document([without_amount]),
            document([good, good]),
        ]
        for text in bad_files:
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(CorruptStoreError):
                    self.repository.load_pending()

class TestNameInPending(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = self.directory / "players.json"

    def test_a_name_round_trips_in_both_repositories(self) -> None:
        named = Request("op3", "add_item", "ada", "torch-1", name="torch")
        for repository in (InMemoryInventoryRepository(), JsonInventoryRepository(self.path)):
            with self.subTest(repository=type(repository).__name__):
                repository.save({"ada": [("torch-1", "torch")]}, None, [named])
                self.assertEqual("torch", repository.load_pending()[0].name)

    def write(self, **changes: object) -> JsonInventoryRepository:
        body = {"op_id": "op1", "action": "add_item", "player_id": "ada",
                "item_id": "torch-1", "amount": 1, **changes}
        body = {key: value for key, value in body.items() if value is not ...}
        self.path.write_text(json.dumps({
            "version": 3,
            "players": {"ada": {"items": [{"id": "torch-1", "name": "torch"}], "resources": {}}},
            "pending": [body],
        }), encoding="utf-8")
        return JsonInventoryRepository(self.path)

    def test_an_operation_saved_without_a_name_still_loads(self) -> None:
        self.assertIsNone(self.write().load_pending()[0].name)

    def test_a_bad_name_is_refused(self) -> None:
        for name in ("", 5):
            with self.subTest(name=name):
                with self.assertRaises(CorruptStoreError):
                    self.write(name=name).load_pending()


if __name__ == "__main__":
    unittest.main()