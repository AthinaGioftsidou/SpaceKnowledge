"""File names inside the state folder, in one place."""

from pathlib import Path

ACCOUNTS_FILE = "accounts.json"
PLAYERS_FILE = "players.json"
UNIVERSE_FILE = "universe.json"
SERVER_KEY_FILE = "server.key"
MAILBOX_FILE = Path("mailbox") / "admin_mailbox.txt"