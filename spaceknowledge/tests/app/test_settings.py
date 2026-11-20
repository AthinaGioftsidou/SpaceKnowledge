"""Tests for Settings and load_settings."""

import shutil
import tempfile
import unittest
from pathlib import Path

from spaceknowledge.app.settings import (
    DEFAULT_PORT,
    Settings,
    SettingsError,
    is_valid_name,
    load_settings,
)


class TestNames(unittest.TestCase):
    def test_good_names(self) -> None:
        for name in ("broker-1", "b", "broker_2", "a" * 30):
            with self.subTest(name=name):
                self.assertTrue(is_valid_name(name))

    def test_bad_names(self) -> None:
        for name in ("", "Broker", "-x", "has space", "../x", "a" * 31, "universe", 5):
            with self.subTest(name=name):
                self.assertFalse(is_valid_name(name))  # type: ignore[arg-type]


class TestSettings(unittest.TestCase):
    def test_the_defaults(self) -> None:
        settings = Settings()
        self.assertEqual(
            ("127.0.0.1", DEFAULT_PORT, ("broker-1", "broker-2"), "earth"),
            (settings.universe_host, settings.universe_port, settings.brokers, settings.start),
        )

    def test_bad_values_are_refused(self) -> None:
        bad = [
            {"universe_host": ""}, {"universe_host": 5},
            {"universe_port": 0}, {"universe_port": 70000},
            {"universe_port": True}, {"universe_port": "7400"},
            {"brokers": ()}, {"brokers": ["broker-1"]}, {"brokers": ("Bad",)},
            {"brokers": ("a", "a")}, {"brokers": ("universe",)}, {"brokers": (5,)},
            {"start": ""}, {"start": 5},
        ]
        for kwargs in bad:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(SettingsError):
                    Settings(**kwargs)  # type: ignore[arg-type]


class TestLoading(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = self.directory / "settings.json"

    def test_a_missing_file_gives_the_defaults(self) -> None:
        self.assertEqual(Settings(), load_settings(self.path))

    def test_a_full_file_is_read(self) -> None:
        self.path.write_text(
            '{"universe_host": "127.0.0.1", "universe_port": 7500, '
            '"brokers": ["b1", "b2", "b3"], "start": "mars"}', encoding="utf-8")
        self.assertEqual(Settings("127.0.0.1", 7500, ("b1", "b2", "b3"), "mars"),
                         load_settings(self.path))

    def test_a_partial_file_keeps_the_other_defaults(self) -> None:
        self.path.write_text('{"universe_port": 7500}', encoding="utf-8")
        self.assertEqual(Settings(universe_port=7500), load_settings(self.path))

    def test_a_file_that_cannot_be_trusted_is_refused(self) -> None:
        for text in ("{bad", "[]", '{"nope": 1}', '{"brokers": "broker-1"}',
                     '{"universe_port": 0}', '{"brokers": ["Bad Name"]}'):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(SettingsError):
                    load_settings(self.path)

    def test_a_string_is_refused_where_a_path_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            load_settings("settings.json")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()