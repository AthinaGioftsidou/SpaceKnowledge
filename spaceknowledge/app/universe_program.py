"""The Universe as its own program. Start it from the project folder:

    python -m spaceknowledge.app.universe_program

It listens on the host and port in settings.json (default 127.0.0.1:7400) and
only the Brokers named there can connect. Stop it with Ctrl+C.
"""

import json
import time
from datetime import date
from pathlib import Path

from spaceknowledge.app.layout import SETTINGS_FILE, UNIVERSE_STATE_DIR, WORLD_FILE
from spaceknowledge.app.paths import SERVER_KEY_FILE, UNIVERSE_FILE
from spaceknowledge.app.settings import SettingsError, load_settings
from spaceknowledge.common.logfile import LOG_DIR, close_log, open_log
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.transport.server_auth import (
    CorruptKeyError,
    ServerIdentity,
    load_or_create_key,
)
from spaceknowledge.transport.universe_listener import UniverseListener
from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.universe import Universe
from spaceknowledge.universe.universe_repository import CorruptStateError, JsonUniverseRepository
from spaceknowledge.world.loader import StandardWorldLoader
from spaceknowledge.universe.missions import MissionBook


class UniverseProcess:
    """A running Universe: the world, and the listener that serves it."""

    def __init__(self, universe: Universe, listener: UniverseListener) -> None:
        if not isinstance(universe, Universe):
            raise TypeError(f"universe must be a Universe, not {type(universe).__name__}")
        if not isinstance(listener, UniverseListener):
            raise TypeError(f"listener must be a UniverseListener, not {type(listener).__name__}")
        self._universe = universe
        self._listener = listener

    @property
    def address(self) -> tuple[str, int]:
        return self._listener.address

    @property
    def universe(self) -> Universe:
        return self._universe

    def close(self) -> None:
        """Stop listening and end every connection. Harmless to call twice."""
        self._listener.stop()


def start_universe(
    world_file: Path,
    state_dir: Path,
    host: str = "127.0.0.1",
    port: int = 0,
    peers: tuple[str, ...] = ("broker-1",),
) -> UniverseProcess:
    """Load the world and its saved state, create the server key if there is
    none, and start listening. Port 0 lets the system pick a free port."""
    if not isinstance(world_file, Path):
        raise TypeError(f"world_file must be a Path, not {type(world_file).__name__}")
    if not isinstance(state_dir, Path):
        raise TypeError(f"state_dir must be a Path, not {type(state_dir).__name__}")
    raw = json.loads(world_file.read_text(encoding="utf-8"))
    world = StandardWorldLoader().build(raw)
    universe = Universe(
        world, Deposits.from_raw(raw), JsonUniverseRepository(state_dir / UNIVERSE_FILE),
        missions=MissionBook.from_raw(raw),
    )
    key = load_or_create_key(state_dir / SERVER_KEY_FILE)
    listener = UniverseListener(universe, ServerIdentity("universe", key), host, port, peers)
    try:
        listener.start()
    except BaseException:
        listener.stop()  # release the port if starting failed
        raise
    return UniverseProcess(universe, listener)


def main() -> int:
    handler = open_log(LOG_DIR, date.today())
    try:
        try:
            settings = load_settings(SETTINGS_FILE)
            process = start_universe(
                WORLD_FILE, UNIVERSE_STATE_DIR,
                settings.universe_host, settings.universe_port, settings.brokers,
            )
        except (SettingsError, CorruptStateError, CorruptKeyError, OSError) as problem:
            print(Refusal(
                "start the Universe", str(problem),
                "fix or delete the file named above, or change the port in settings.json",
            ).describe())
            return 1
        host, port = process.address
        print(f"The Universe is listening on {host}:{port} for: {', '.join(settings.brokers)}.")
        print("Press Ctrl+C to stop it.")
        try:
            while True:
                time.sleep(1)  # a loop, because one long wait is not interruptible on Windows
        except KeyboardInterrupt:
            print("\nStopping.")
        finally:
            process.close()
        return 0
    finally:
        close_log(handler)


if __name__ == "__main__":
    raise SystemExit(main())