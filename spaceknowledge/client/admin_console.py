"""The administrator's console: a one-time code, then read-only commands. It
talks to an AdminClient and to nothing else."""

from collections.abc import Callable
from typing import Any

from spaceknowledge.client.admin_client import AdminClient, SessionEnded
from spaceknowledge.common.refusal import Refusal

Read = Callable[[str], str]
Write = Callable[[str], None]

COMMANDS = ("help", "players", "stats", "quit")


def _ask(read: Read, prompt: str) -> str | None:
    try:
        return read(prompt)
    except EOFError:
        return None


def _lost(what: str) -> str:
    return Refusal(what, "the game did not answer",
                   "check that the game is running, then try again").describe()


def format_stats(stats: dict[str, Any]) -> str:
    """One line per number, objects flattened onto their line."""
    lines = []
    for key in sorted(stats):
        value = stats[key]
        if isinstance(value, dict):
            value = ", ".join(f"{name} {item}" for name, item in sorted(value.items()))
        lines.append(f"{key.replace('_', ' ')}: {value}")
    return "\n".join(lines)


def run_admin_client(client: AdminClient, read: Read, read_secret: Read, write: Write) -> None:
    if not isinstance(client, AdminClient):
        raise TypeError(f"client must be an AdminClient, not {type(client).__name__}")
    write("Space Knowledge administration.")
    name = _ask(read, "Admin name: ")
    if name is None:
        return
    try:
        refusal = client.request_code(name)
    except ConnectionError:
        write(_lost("ask for a code"))
        return
    if refusal is not None:
        write(refusal.describe())
        return
    write("If that name is an administrator, a one-time code was sent to its mailbox. "
          "It works once and expires soon.")
    code = _ask(read_secret, "Code: ")
    if code is None:
        return
    try:
        token = client.login(name, code.strip())
    except ConnectionError:
        write(_lost("log in"))
        return
    if isinstance(token, Refusal):
        write(token.describe())
        return
    try:
        _commands(client, token, read, write)
    finally:
        try:
            client.logout(token)
        except ConnectionError:
            pass  # the session ends on its own when the game is unreachable


def _commands(client: AdminClient, token: str, read: Read, write: Write) -> None:
    write("Logged in. Type help to see what you can do.")
    while True:
        line = _ask(read, "admin> ")
        if line is None:
            return
        word = line.strip().lower()
        if word in ("quit", "q"):
            write("Goodbye.")
            return
        if not word:
            continue
        try:
            if word == "help":
                write("You can: " + ", ".join(COMMANDS))
            elif word == "players":
                names = client.players(token)
                write("Players: " + (", ".join(names) if names else "none yet"))
            elif word == "stats":
                write(format_stats(client.stats(token)))
            else:
                write(Refusal(word, "that is not an admin command",
                              "type help to see the commands").describe())
        except SessionEnded as ended:
            write(ended.refusal.describe())
            return
        except ConnectionError:
            write(_lost(word))