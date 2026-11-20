"""The log file: one file per day, always appended.

Modules ask for a logger with `logging.getLogger(__name__)`. Deciding where the
lines go is the program's job, so each program calls `open_log` once.

The day is a parameter, not read from the clock here, so a test can pass a
fixed date and always get the same file name.
"""

import logging
from datetime import date
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"

# Date and time, level, thread name (broker, universe, MainThread) and logger.
FORMAT = "%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s"


def log_path(directory: Path, day: date) -> Path:
    """The file for one day. It starts with the date, so files sort by day."""
    return directory / f"{day.isoformat()}_spaceknowledge.log"


def open_log(directory: Path, day: date) -> logging.FileHandler:
    """Send every `spaceknowledge` logger to the day's file, appending.
    Returns the handler so the caller can close it with `close_log`."""
    directory.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path(directory, day), mode="a", encoding="utf-8")
    handler.setFormatter(logging.Formatter(FORMAT))
    logger = logging.getLogger("spaceknowledge")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return handler


def close_log(handler: logging.FileHandler) -> None:
    logging.getLogger("spaceknowledge").removeHandler(handler)
    handler.close()