"""A Broker program: the customer console, with a Broker that talks to a
separate Universe over a socket. Start the Universe first, then:

    python -m spaceknowledge.app.broker_program broker-1

The name must be one of the brokers in settings.json. Each Broker has its own
accounts and inventories in state/<name>/, and reads the shared server key
from state/universe/. (In the next block the Broker becomes a server of its
own and the console becomes a separate client.)
"""

import argparse
from contextlib import ExitStack
from datetime import date
from getpass import getpass
from pathlib import Path

from spaceknowledge.app.customer_console import run_customer
from spaceknowledge.app.front import Front
from spaceknowledge.app.game import Game
from spaceknowledge.app.keys import MissingKeyError, read_existing_key
from spaceknowledge.app.layout import (
    SETTINGS_FILE,
    UNIVERSE_STATE_DIR,
    broker_state_dir,
)
from spaceknowledge.app.paths import ACCOUNTS_FILE, PLAYERS_FILE, SERVER_KEY_FILE
from spaceknowledge.app.settings import SettingsError, is_valid_name, load_settings
from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.broker_server import BrokerServer
from spaceknowledge.broker.inventory_repository import CorruptStoreError, JsonInventoryRepository
from spaceknowledge.common.logfile import LOG_DIR, close_log, open_log
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.transport.server_auth import CorruptKeyError, ServerIdentity
from spaceknowledge.transport.socket_channel import SocketChannel
from spaceknowledge.users.account_repository import CorruptAccountsError, JsonAccountRepository
from spaceknowledge.users.accounts import AccountRegistry
from spaceknowledge.users.credentials import DEFAULT_ITERATIONS
from spaceknowledge.users.session_book import SessionBook


def build_broker(
    state_dir: Path,
    key_file: Path,
    host: str,
    port: int,
    start: str,
    name: str,
    iterations: int = DEFAULT_ITERATIONS,
    timeout: float = 3.0,
) -> Game:
    """Start (or restart) one Broker whose Universe is at host:port.

    The key must already exist. Unfinished operations from an earlier run are
    sent again BEFORE the Broker thread starts, so this raises ConnectionError
    if the Universe cannot be reached while something is still pending.
    """
    if not isinstance(state_dir, Path):
        raise TypeError(f"state_dir must be a Path, not {type(state_dir).__name__}")
    if not isinstance(key_file, Path):
        raise TypeError(f"key_file must be a Path, not {type(key_file).__name__}")
    if not is_valid_name(name):
        raise ValueError(f"{name!r} is not a valid Broker name")
    key = read_existing_key(key_file)
    accounts = AccountRegistry(JsonAccountRepository(state_dir / ACCOUNTS_FILE), iterations)

    with ExitStack() as stack:
        channel = SocketChannel(host, port, ServerIdentity(name, key), timeout)
        stack.callback(channel.close)
        broker = Broker(channel, JsonInventoryRepository(state_dir / PLAYERS_FILE))
        broker.recover()

        broker_server = BrokerServer(broker)
        broker_server.start()
        stack.callback(broker_server.stop)  # runs first, then the channel closes

        front = Front(accounts, SessionBook(), broker_server, start)
        return Game(front, stack.pop_all())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start a Broker with a customer console.")
    parser.add_argument("name", help="this Broker's name, one of the brokers in settings.json")
    args = parser.parse_args(argv)
    handler = open_log(LOG_DIR, date.today())
    try:
        try:
            settings = load_settings(SETTINGS_FILE)
            if args.name not in settings.brokers:
                raise SettingsError(f"{args.name} is not one of the brokers in settings.json")
            game = build_broker(
                broker_state_dir(args.name), UNIVERSE_STATE_DIR / SERVER_KEY_FILE,
                settings.universe_host, settings.universe_port, settings.start, args.name,
            )
        except (SettingsError, MissingKeyError, CorruptKeyError, CorruptStoreError,
                CorruptAccountsError, ConnectionError, TimeoutError) as problem:
            print(Refusal(
                "start the Broker", str(problem),
                "check that the Universe is running, that the name is in settings.json, "
                "and that the files named above are intact",
            ).describe())
            return 1
        try:
            run_customer(game.front, input, getpass, print)
        except KeyboardInterrupt:
            print("\nGoodbye.")
        finally:
            game.close()
        return 0
    finally:
        close_log(handler)


if __name__ == "__main__":
    raise SystemExit(main())