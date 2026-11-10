"""Tests for resources in the inventory repositories, and for version 2 files."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from observatory.broker.inventory_repository import (
    CorruptStoreError,
    InMemoryInventoryRepository,
    JsonInventoryRepository,
)

ITEMS = {"ada": [("torch", "torch")], "bob": []}
RESOURCES = {"ada": {"iron": 3, "water": 2}, "bob": {}}


class TestInMemoryResources(unittest.TestCase):
    def test_nothing_saved_means_no_resources(self) -> None:
        self.assertEqual({}, InMemoryInventoryRepository().load_resources())

    def test_saved_resources_are_loaded(self) -> None:
        repository = InMemoryInventoryRepository()
        repository.save(ITEMS, RESOURCES)
        self.assertEqual(RESOURCES, repository.load_resources())

    def test_saving_without_resources_gives_every_player_an_empty_bag(self) -> None:
        repository = InMemoryInventoryRepository()
        repository.save(ITEMS)
        self.assertEqual({"ada": {}, "bob": {}}, repository.load_resources())

    def test_the_loaded_resources_are_a_copy(self) -> None:
        repository = InMemoryInventoryRepository()
        repository.save(ITEMS, RESOURCES)
        repository.load_resources()["ada"]["iron"] = 999
        self.assertEqual(3, repository.load_resources()["ada"]["iron"])

    def test_resources_for_a_player_with_no_record_are_refused(self) -> None:
        repository = InMemoryInventoryRepository()
        repository.save(ITEMS, RESOURCES)
        with self.assertRaises(ValueError):
            repository.save(ITEMS, {"eve": {"iron": 1}})
        self.assertEqual(RESOURCES, repository.load_resources())


class TestJsonResources(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = self.directory / "players.json"
        self.repository = JsonInventoryRepository(self.path)

    def test_a_missing_file_has_no_resources(self) -> None:
        self.assertEqual({}, self.repository.load_resources())

    def test_items_and_resources_round_trip_together(self) -> None:
        self.repository.save(ITEMS, RESOURCES)
        self.assertEqual(ITEMS, self.repository.load())
        self.assertEqual(RESOURCES, self.repository.load_resources())

    def test_saving_writes_a_version_2_file(self) -> None:
        self.repository.save(ITEMS, RESOURCES)
        document = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(2, document["version"])

    def test_a_version_1_file_is_still_read_with_empty_bags(self) -> None:
        self.path.write_text(
            '{"version": 1, "players": {"ada": [{"id": "torch", "name": "torch"}]}}',
            encoding="utf-8",
        )
        self.assertEqual({"ada": [("torch", "torch")]}, self.repository.load())
        self.assertEqual({"ada": {}}, self.repository.load_resources())

    def test_resources_for_a_player_with_no_record_are_refused_and_the_file_is_kept(self) -> None:
        self.repository.save(ITEMS, RESOURCES)
        with self.assertRaises(ValueError):
            self.repository.save(ITEMS, {"eve": {"iron": 1}})
        self.assertEqual(RESOURCES, self.repository.load_resources())
        self.assertEqual(["players.json"], sorted(item.name for item in self.directory.iterdir()))

    def test_a_version_2_file_that_cannot_be_trusted_is_refused(self) -> None:
        bad_files = [
            '{"version": true, "players": {}}',
            '{"version": 2, "players": {"ada": []}}',
            '{"version": 2, "players": {"ada": {"items": []}}}',
            '{"version": 2, "players": {"ada": {"resources": {}}}}',
            '{"version": 2, "players": {"ada": {"items": [], "resources": []}}}',
            '{"version": 2, "players": {"ada": {"items": [], "resources": {"iron": 0}}}}',
            '{"version": 2, "players": {"ada": {"items": [], "resources": {"iron": 1.5}}}}',
            '{"version": 2, "players": {"ada": {"items": [], "resources": {"iron": true}}}}',
            '{"version": 2, "players": {"ada": {"items": [], "resources": {"": 3}}}}',
        ]
        for text in bad_files:
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(CorruptStoreError):
                    self.repository.load_resources()


if __name__ == "__main__":
    unittest.main()