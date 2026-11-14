"""##02 The log file: one file per day, named for the day, always appended.

Modules only ask for a logger with `logging.getLogger(__name__)` (##01).
Deciding where the lines go is the program's job, so the driver calls
`open_log` once.

The day is a parameter, not read from the clock in here, so a test can pass a
fixed date and always get the same file name.
"""

import logging
from datetime import date
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"

# Every line starts with the date and time, then the level, the thread
# (MainThread is the producer, consume is the consumer) and the logger.
FORMAT = "%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s"


def log_path(directory: Path, day: date) -> Path:
    """The file for one day. Starts with the date, so the files sort by day."""
    return directory / f"{day.isoformat()}_observatory.log"


def open_log(directory: Path, day: date) -> logging.FileHandler:
    """Send every `observatory` logger to the day's file, appending.

    Returns the handler, so the caller can close it with `close_log`.
    """
    directory.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path(directory, day), mode="a", encoding="utf-8")
    handler.setFormatter(logging.Formatter(FORMAT))
    logger = logging.getLogger("observatory")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return handler


def close_log(handler: logging.FileHandler) -> None:
    logging.getLogger("observatory").removeHandler(handler)
    handler.close()
