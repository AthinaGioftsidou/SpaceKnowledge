"""The customer client. Start a Broker first, then, from the project folder:

    python -m spaceknowledge.client.program --port 8400

The port is the DMZ port of the Broker you want to play through (8400 for
broker-1, 8401 for broker-2 with the default settings). Nothing else about the
game is known to this program.
"""

import argparse
from getpass import getpass

from spaceknowledge.client.console import run_client
from spaceknowledge.client.game_client import GameClient
from spaceknowledge.common.refusal import Refusal

DEFAULT_PORT = 8400


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play Space Knowledge.")
    parser.add_argument("--host", default="127.0.0.1", help="the game's address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="the game's port")
    args = parser.parse_args(argv)
    try:
        client = GameClient(args.host, args.port)
    except ValueError as problem:
        print(Refusal("start the client", str(problem),
                      "give a host name and a port from 1 to 65535").describe())
        return 1
    try:
        run_client(client, input, getpass, print)
    except KeyboardInterrupt:
        print("\nGoodbye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())