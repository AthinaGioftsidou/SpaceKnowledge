"""Tests for read_existing_key: a Broker never creates the server key."""

import shutil
import tempfile
import unittest
from pathlib import Path

from spaceknowledge.app.keys import MissingKeyError, read_existing_key
from spaceknowledge.transport.server_auth import CorruptKeyError, load_or_create_key


class TestReadExistingKey(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = self.directory / "server.key"

    def test_a_missing_key_is_refused_and_not_created(self) -> None:
        with self.assertRaises(MissingKeyError):
            read_existing_key(self.path)
        self.assertFalse(self.path.exists())

    def test_an_existing_key_is_read(self) -> None:
        key = load_or_create_key(self.path)
        self.assertEqual(key, read_existing_key(self.path))

    def test_a_damaged_key_is_refused(self) -> None:
        self.path.write_text("abc", encoding="ascii")
        with self.assertRaises(CorruptKeyError):
            read_existing_key(self.path)

    def test_a_string_is_refused_where_a_path_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            read_existing_key("server.key")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()