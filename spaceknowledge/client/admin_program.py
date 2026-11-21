"""The administrator client. Start a Broker first, then, from the project folder:

    python -m spaceknowledge.client.admin_program --port 8400

The one-time code is written to the Broker's mailbox file, which stands in for
an email: state/broker-1/mailbox/admin_mailbox.txt for broker-1. Open it, copy
the 8 digits, and paste them at the hidden Code prompt.
"""

import argparse
from getpass import getpass

from spaceknowledge.client.admin_client import AdminClient
from spaceknowledge.client.admin_console import run_admin_client
from spaceknowledge.common.refusal import Refusal

DEFAULT_PORT = 8400


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Administer a Space Knowledge Broker.")
    parser.add_argument("--host", default="127.0.0.1", help="the game's address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="the game's port")
    args = parser.parse_args(argv)
    try:
        client = AdminClient(args.host, args.port)
    except ValueError as problem:
        print(Refusal("start the client", str(problem),
                      "give a host name and a port from 1 to 65535").describe())
        return 1
    try:
        run_admin_client(client, input, getpass, print)
    except KeyboardInterrupt:
        print("\nGoodbye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())