"""Tests for the folder layout."""

import unittest

from spaceknowledge.app.layout import STATE_ROOT, UNIVERSE_STATE_DIR, broker_state_dir


class TestLayout(unittest.TestCase):
    def test_each_broker_has_its_own_folder_beside_the_universes(self) -> None:
        self.assertEqual(STATE_ROOT / "broker-1", broker_state_dir("broker-1"))
        self.assertNotEqual(broker_state_dir("broker-1"), broker_state_dir("broker-2"))
        self.assertEqual(STATE_ROOT, UNIVERSE_STATE_DIR.parent)

    def test_a_name_that_could_leave_the_state_folder_is_refused(self) -> None:
        for name in ("", "../x", "a/b", "Broker", "universe"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    broker_state_dir(name)


if __name__ == "__main__":
    unittest.main()