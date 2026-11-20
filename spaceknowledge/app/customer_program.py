"""Start the customer game from the project folder:

    python -m spaceknowledge.app.customer_program

Saved games live in `state/`. Delete that folder to start from the beginning.
"""

from datetime import date
from getpass import getpass
from pathlib import Path

from spaceknowledge.app.customer_console import run_customer
from spaceknowledge.app.game import build_game
from spaceknowledge.broker.inventory_repository import CorruptStoreError
from spaceknowledge.common.logfile import LOG_DIR, close_log, open_log
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.transport.server_auth import CorruptKeyError
from spaceknowledge.universe.universe_repository import CorruptStateError
from spaceknowledge.users.account_repository import CorruptAccountsError

PROJECT = Path(__file__).resolve().parents[2]
WORLD_FILE = PROJECT / "data" / "space.json"
STATE_DIR = PROJECT / "state"


def main() -> int:
    handler = open_log(LOG_DIR, date.today())
    try:
        try:
            game = build_game(WORLD_FILE, STATE_DIR)
        except (CorruptStoreError, CorruptStateError, CorruptAccountsError, CorruptKeyError) as problem:
            print(Refusal(
                "start the game", str(problem),
                f"restore the files in the {STATE_DIR.name} folder from a backup, "
                "or delete that folder to begin a new game",
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