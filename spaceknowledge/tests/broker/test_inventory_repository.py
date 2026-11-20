"""Tests for the inventory repositories: in memory and JSON on disk."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spaceknowledge.broker.inventory_repository import (
    CorruptStoreError,
    InMemoryInventoryRepository,
    InventoryRepository,
    JsonInventoryRepository,
)

RECORDS = {"ada": [("torch", "torch"), ("brass_key", "brass key")], "bob": []}


class TestInMemory(unittest.TestCase):
    def test_a_new_repository_is_empty(self) -> None:
        self.assertEqual({}, InMemoryInventoryRepository().load())

    def test_what_was_saved_is_loaded(self) -> None:
        repository = InMemoryInventoryRepository()
        repository.save(RECORDS)
        self.assertEqual(RECORDS, repository.load())

    def test_changing_the_loaded_copy_does_not_change_the_store(self) -> None:
        repository = InMemoryInventoryRepository()
        repository.save(RECORDS)
        repository.load()["ada"].clear()
        self.assertEqual(2, len(repository.load()["ada"]))

    def test_the_abstract_repository_cannot_be_built(self) -> None:
        with self.assertRaises(TypeError):
            InventoryRepository()  # type: ignore[abstract]


class TestJson(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = self.directory / "players.json"
        self.repository = JsonInventoryRepository(self.path)

    def files(self) -> list[str]:
        return sorted(item.name for item in self.directory.iterdir())

    def test_a_missing_file_loads_as_empty(self) -> None:
        self.assertEqual({}, self.repository.load())

    def test_what_was_saved_is_loaded(self) -> None:
        self.repository.save(RECORDS)
        self.assertEqual(RECORDS, self.repository.load())

    def test_a_missing_folder_is_created(self) -> None:
        nested = JsonInventoryRepository(self.directory / "data" / "players.json")
        nested.save(RECORDS)
        self.assertEqual(RECORDS, nested.load())

    def test_saving_leaves_no_temporary_file(self) -> None:
        self.repository.save(RECORDS)
        self.assertEqual(["players.json"], self.files())

    def test_a_second_save_replaces_the_first(self) -> None:
        self.repository.save(RECORDS)
        self.repository.save({"ada": []})
        self.assertEqual({"ada": []}, self.repository.load())

    def test_a_failed_save_keeps_the_old_file_and_leaves_nothing_behind(self) -> None:
        self.repository.save(RECORDS)
        target = "spaceknowledge.broker.inventory_repository.os.replace"
        with patch(target, side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.repository.save({"ada": []})
        self.assertEqual(RECORDS, self.repository.load())
        self.assertEqual(["players.json"], self.files())

    def test_a_file_that_cannot_be_trusted_is_refused(self) -> None:
        bad_files = [
            "{not json",
            "[]",
            '{"version": 4, "players": {}}',
            '{"version": 1, "players": []}',
            '{"version": 1, "players": {"ada": "torch"}}',
            '{"version": 1, "players": {"ada": [{"id": "torch"}]}}',
            '{"version": 1, "players": {"ada": [{"id": "", "name": "torch"}]}}',
            '{"version": 1, "players": {"ada": [{"id": "t", "name": "t"}, {"id": "t", "name": "t"}]}}',
            '{"version": 1, "players": {"": []}}',
        ]
        for text in bad_files:
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(CorruptStoreError):
                    self.repository.load()

    def test_a_string_is_refused_where_a_path_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            JsonInventoryRepository("players.json")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()