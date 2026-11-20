"""##02 Tests for the day's log file.

Every test passes the same fixed date, so the file name is always the same:
`2026-10-08_spaceknowledge.log`. Nothing here reads the clock.
"""

import logging
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from spaceknowledge.common.logfile import LOG_DIR, close_log, log_path, open_log

DAY = date(2026, 10, 8)


def write(directory: Path, day: date, message: str) -> None:
    """One run of the program: open the log, write one line, close it."""
    handler = open_log(directory, day)
    try:
        logging.getLogger("spaceknowledge.test").info(message)
    finally:
        close_log(handler)


class TestLogFile(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)

    def lines(self) -> list[str]:
        return log_path(self.directory, DAY).read_text(encoding="utf-8").splitlines()

    def test_the_file_name_starts_with_the_date(self) -> None:
        self.assertEqual("2026-10-08_spaceknowledge.log", log_path(self.directory, DAY).name)

    def test_a_record_reaches_the_file(self) -> None:
        write(self.directory, DAY, "hello")
        self.assertEqual(1, len(self.lines()))
        self.assertIn("INFO", self.lines()[0])
        self.assertIn("hello", self.lines()[0])

    def test_a_second_run_appends(self) -> None:
        write(self.directory, DAY, "first run")
        write(self.directory, DAY, "second run")
        self.assertEqual(2, len(self.lines()))
        self.assertIn("first run", self.lines()[0])
        self.assertIn("second run", self.lines()[1])

    def test_another_day_gets_another_file(self) -> None:
        write(self.directory, DAY, "today")
        write(self.directory, date(2026, 10, 9), "tomorrow")
        self.assertEqual(1, len(self.lines()))

    def test_a_missing_directory_is_created(self) -> None:
        write(self.directory / "logs", DAY, "hello")
        self.assertTrue(log_path(self.directory / "logs", DAY).exists())

    def test_each_line_starts_with_the_date_and_time(self) -> None:
        write(self.directory, DAY, "hello")
        self.assertRegex(self.lines()[0], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


class TestTheRealLogDirectory(unittest.TestCase):
    """The game writes to `logs/` in the project. If this machine cannot write
    there (permissions, a read-only share, a synced folder that locks files),
    this is the test that says so, before a game is played."""

    def test_the_project_log_directory_is_writable(self) -> None:
        day = date(2000, 1, 1)
        path = log_path(LOG_DIR, day)
        try:
            write(LOG_DIR, day, "log directory check")
            self.assertIn("log directory check", path.read_text(encoding="utf-8"))
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
