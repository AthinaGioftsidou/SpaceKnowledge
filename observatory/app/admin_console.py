"""The admin console: a one-time code, then admin commands. It contains no
player operation."""

from collections.abc import Callable

from observatory.app.admin import AdminOffice
from observatory.common.refusal import Refusal

Read = Callable[[str], str]
Write = Callable[[str], None]

COMMANDS = ("help", "players", "quit")


def _ask(read: Read, prompt: str) -> str | None:
    try:
        return read(prompt)
    except EOFError:
        return None


def run_admin(office: AdminOffice, read: Read, read_secret: Read, write: Write) -> None:
    if not isinstance(office, AdminOffice):
        raise TypeError(f"office must be an AdminOffice, not {type(office).__name__}")
    write("Admin console.")
    name = _ask(read, "Admin name: ")
    if name is None:
        return
    office.request_code(name)
    write(f"If {name.strip()} is an administrator, a one-time code was written to "
          f"{office.mailbox_path}. It works once and expires soon.")
    code = _ask(read_secret, "Code: ")
    if code is None:
        return
    token = office.login(name, code.strip())
    if isinstance(token, Refusal):
        write(token.describe())
        return
    try:
        _commands(office, token, read, write)
    finally:
        office.logout(token)


def _commands(office: AdminOffice, token: str, read: Read, write: Write) -> None:
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
        if word == "help":
            write("You can: " + ", ".join(COMMANDS))
        elif word == "players":
            result = office.players(token)
            if isinstance(result, Refusal):
                write(result.describe())
            else:
                write("Players: " + (", ".join(result) if result else "none yet"))
        else:
            write(Refusal(word, "that is not an admin command",
                          "type help to see the commands").describe())