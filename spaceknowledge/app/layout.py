"""Where each program keeps its files."""

from pathlib import Path

from spaceknowledge.app.settings import is_valid_name

PROJECT = Path(__file__).resolve().parents[2]
WORLD_FILE = PROJECT / "data" / "space.json"
SETTINGS_FILE = PROJECT / "settings.json"
STATE_ROOT = PROJECT / "state"
UNIVERSE_STATE_DIR = STATE_ROOT / "universe"


def broker_state_dir(name: str) -> Path:
    """The folder one Broker owns. The name is checked first, because it
    becomes part of a path."""
    if not is_valid_name(name):
        raise ValueError(f"{name!r} is not a valid Broker name")
    return STATE_ROOT / name