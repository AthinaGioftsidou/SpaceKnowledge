"""Start the admin console from the project folder:

    python -m observatory.app.admin_program

The one-time code is written to `state/mailbox/admin_mailbox.txt`.
"""

from datetime import date
from getpass import getpass
from pathlib import Path

from observatory.app.admin import build_admin
from observatory.app.admin_console import run_admin
from observatory.common.logfile import LOG_DIR, close_log, open_log

PROJECT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT / "state"
ADMINS = ("root",)


def main() -> int:
    handler = open_log(LOG_DIR, date.today())
    try:
        try:
            run_admin(build_admin(STATE_DIR, ADMINS), input, getpass, print)
        except KeyboardInterrupt:
            print("\nGoodbye.")
        return 0
    finally:
        close_log(handler)


if __name__ == "__main__":
    raise SystemExit(main())