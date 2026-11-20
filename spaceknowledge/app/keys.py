"""Reading the server key without ever creating it."""

from pathlib import Path

from spaceknowledge.transport.server_auth import load_or_create_key


class MissingKeyError(ValueError):
    """The server key file does not exist."""


def read_existing_key(path: Path) -> bytes:
    """The key in `path`. A Broker must never create the key: only the Universe
    does, and a Broker that made its own would simply be refused later, with a
    confusing message."""
    if not isinstance(path, Path):
        raise TypeError(f"path must be a Path, not {type(path).__name__}")
    if not path.exists():
        raise MissingKeyError(f"{path.name} does not exist: start the Universe first, it creates the key")
    return load_or_create_key(path)  # the file exists, so this only reads and checks it