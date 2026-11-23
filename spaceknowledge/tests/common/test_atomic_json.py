"""Tests for write_json_atomically and write_text_atomically."""

import json
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spaceknowledge.common.atomic_json import write_json_atomically, write_text_atomically


class TestWriteJsonAtomically(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = self.directory / "state.json"

    def files(self) -> list[str]:
        return sorted(item.name for item in self.directory.iterdir())

    def read(self) -> object:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_the_document_is_written(self) -> None:
        write_json_atomically(self.path, {"a": 1})
        self.assertEqual({"a": 1}, self.read())

    def test_a_missing_folder_is_created(self) -> None:
        nested = self.directory / "data" / "state.json"
        write_json_atomically(nested, {"a": 1})
        self.assertTrue(nested.exists())

    def test_no_temporary_file_is_left(self) -> None:
        write_json_atomically(self.path, {"a": 1})
        self.assertEqual(["state.json"], self.files())

    def test_a_second_write_replaces_the_first(self) -> None:
        write_json_atomically(self.path, {"a": 1})
        write_json_atomically(self.path, {"a": 2})
        self.assertEqual({"a": 2}, self.read())

    def test_a_failed_replace_keeps_the_old_file_and_leaves_nothing(self) -> None:
        write_json_atomically(self.path, {"a": 1})
        with patch("spaceknowledge.common.atomic_json.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                write_json_atomically(self.path, {"a": 2})
        self.assertEqual({"a": 1}, self.read())
        self.assertEqual(["state.json"], self.files())

    def test_a_document_that_is_not_json_keeps_the_old_file_and_leaves_nothing(self) -> None:
        write_json_atomically(self.path, {"a": 1})
        with self.assertRaises(TypeError):
            write_json_atomically(self.path, {"a": object()})
        self.assertEqual({"a": 1}, self.read())
        self.assertEqual(["state.json"], self.files())

    def test_every_write_uses_its_own_temporary_file_in_the_same_folder(self) -> None:
        used: list[Path] = []
        real_replace = os.replace

        def spy(source: str, target: Path) -> None:
            used.append(Path(source))
            real_replace(source, target)

        with patch("spaceknowledge.common.atomic_json.os.replace", side_effect=spy):
            write_json_atomically(self.path, {"a": 1})
            write_json_atomically(self.path, {"a": 2})
        self.assertEqual(2, len(used))
        self.assertNotEqual(used[0], used[1])
        for temporary in used:
            self.assertEqual(self.directory, temporary.parent)

    def test_a_leftover_temporary_file_from_another_writer_is_not_touched(self) -> None:
        stale = self.directory / "state.json.tmp"
        stale.write_text("half written by someone else", encoding="utf-8")
        write_json_atomically(self.path, {"a": 1})
        self.assertEqual("half written by someone else", stale.read_text(encoding="utf-8"))
        self.assertEqual({"a": 1}, self.read())

class TestWriteTextAtomically(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = self.directory / "note.txt"

    def test_the_text_is_written_and_replaced(self) -> None:
        write_text_atomically(self.path, "one")
        write_text_atomically(self.path, "two")
        self.assertEqual("two", self.path.read_text(encoding="utf-8"))
        self.assertEqual(["note.txt"], sorted(p.name for p in self.directory.iterdir()))

    def test_a_failed_replace_keeps_the_old_text_and_leaves_nothing(self) -> None:
        write_text_atomically(self.path, "old")
        with patch("spaceknowledge.common.atomic_json.os.replace", side_effect=OSError("full")):
            with self.assertRaises(OSError):
                write_text_atomically(self.path, "new")
        self.assertEqual("old", self.path.read_text(encoding="utf-8"))
        self.assertEqual(["note.txt"], sorted(p.name for p in self.directory.iterdir()))

    @unittest.skipIf(os.name == "nt", "file modes are a POSIX feature")
    def test_the_file_is_readable_by_its_owner_only(self) -> None:
        write_text_atomically(self.path, "secret")
        self.assertEqual(0o600, stat.S_IMODE(self.path.stat().st_mode))


if __name__ == "__main__":
    unittest.main()