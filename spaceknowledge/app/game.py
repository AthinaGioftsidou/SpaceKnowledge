"""Assembly: builds a whole game in one process and owns its threads."""

import json
from contextlib import ExitStack
from pathlib import Path

from spaceknowledge.app.admin_service import AdminService
from spaceknowledge.app.front import Front
from spaceknowledge.app.paths import ACCOUNTS_FILE, PLAYERS_FILE, SERVER_KEY_FILE, UNIVERSE_FILE
from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.broker_server import BrokerServer
from spaceknowledge.broker.inventory_repository import JsonInventoryRepository
from spaceknowledge.transport.server_auth import (
    AuthenticatedChannel,
    ServerIdentity,
    load_or_create_key,
)
from spaceknowledge.transport.threaded_channel import ThreadedChannel
from spaceknowledge.transport.universe_server import UniverseServer
from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.missions import MissionBook
from spaceknowledge.universe.universe import Universe
from spaceknowledge.universe.universe_repository import JsonUniverseRepository
from spaceknowledge.users.account_repository import JsonAccountRepository
from spaceknowledge.users.accounts import AccountRegistry
from spaceknowledge.users.credentials import DEFAULT_ITERATIONS
from spaceknowledge.users.session_book import SessionBook
from spaceknowledge.world.loader import StandardWorldLoader


class Game:
    """A running game: the Front that clients use, the threads behind it and,
    when the game was built with one, the AdminService.

    Always call `close`. It stops the Broker thread first and the world behind
    it second, because the Broker may still be waiting on it.
    """

    def __init__(self, front: Front, threads: ExitStack, admin: AdminService | None = None) -> None:
        if not isinstance(front, Front):
            raise TypeError(f"front must be a Front, not {type(front).__name__}")
        if not isinstance(threads, ExitStack):
            raise TypeError(f"threads must be an ExitStack, not {type(threads).__name__}")
        if admin is not None and not isinstance(admin, AdminService):
            raise TypeError(f"admin must be an AdminService, not {type(admin).__name__}")
        self._front = front
        self._threads = threads
        self._admin = admin

    @property
    def front(self) -> Front:
        return self._front

    @property
    def admin(self) -> AdminService | None:
        return self._admin

    def close(self) -> None:
        """Stop both threads. Harmless to call twice."""
        self._threads.close()


def build_game(
    world_file: Path, state_dir: Path, iterations: int = DEFAULT_ITERATIONS
) -> Game:
    """Start (or restart) the whole game in one process and return it.

    Order matters. The Universe loads its saved state, then its thread starts,
    then the Broker loads its own and finishes unfinished operations, then the
    Broker thread starts. If anything fails on the way, the threads already
    started are stopped again. (The two-program version is `build_broker`.)
    """
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
    accounts = AccountRegistry(JsonAccountRepository(state_dir / ACCOUNTS_FILE), iterations)

    with ExitStack() as stack:
        universe_server = UniverseServer(universe)
        universe_server.start()
        stack.callback(universe_server.stop)

        channel = AuthenticatedChannel(
            ThreadedChannel(universe_server),
            ServerIdentity("broker", key),
            ServerIdentity("universe", key),
        )
        broker = Broker(channel, JsonInventoryRepository(state_dir / PLAYERS_FILE))
        broker.recover()

        broker_server = BrokerServer(broker)
        broker_server.start()
        stack.callback(broker_server.stop)

        front = Front(accounts, SessionBook(), broker_server, world.start_destination.destination_id)
        # Hand the stack to the Game, so leaving this block does not stop anything.
        return Game(front, stack.pop_all())