"""The client console: a menu, then the game. It talks to a GameClient and to
nothing else, so it holds no game rule and no server operation."""

from collections.abc import Callable

from spaceknowledge.client.game_client import GameClient, SessionEnded
from spaceknowledge.common.refusal import Refusal

Read = Callable[[str], str]
Write = Callable[[str], None]


def _ask(read: Read, prompt: str) -> str | None:
    """One line, or None at the end of the input."""
    try:
        return read(prompt)
    except EOFError:
        return None


def _lost(what: str) -> str:
    return Refusal(what, "the game did not answer",
                   "check that the game is running, then try again").describe()


def run_client(client: GameClient, read: Read, read_secret: Read, write: Write) -> None:
    """The menu and the game. `read_secret` asks for passwords without showing
    them. Returns when the player quits or the input ends."""
    if not isinstance(client, GameClient):
        raise TypeError(f"client must be a GameClient, not {type(client).__name__}")
    write("Space Knowledge. Type register, login or quit.")
    while True:
        answer = _ask(read, "> ")
        if answer is None:
            return
        choice = answer.strip().lower()
        if choice in ("quit", "q"):
            write("Goodbye.")
            return
        if not choice:
            continue
        if choice == "register":
            _register(client, read, read_secret, write)
        elif choice == "login":
            token = _login(client, read, read_secret, write)
            if token is not None and _play(client, token, read, write):
                write("Goodbye.")
                return
        else:
            write(Refusal(answer.strip(), "that is not a menu choice",
                          "type register, login or quit").describe())


def _credentials(read: Read, read_secret: Read) -> tuple[str, str] | None:
    name = _ask(read, "Name: ")
    if name is None:
        return None
    password = _ask(read_secret, "Password: ")
    if password is None:
        return None
    return name, password


def _register(client: GameClient, read: Read, read_secret: Read, write: Write) -> None:
    given = _credentials(read, read_secret)
    if given is None:
        return
    try:
        refusal = client.register(*given)
    except ConnectionError:
        write(_lost("register"))
        return
    write("Account created. Now type login." if refusal is None else refusal.describe())


def _login(client: GameClient, read: Read, read_secret: Read, write: Write) -> str | None:
    given = _credentials(read, read_secret)
    if given is None:
        return None
    try:
        result = client.login(*given)
    except ConnectionError:
        write(_lost("log in"))
        return None
    if isinstance(result, Refusal):
        write(result.describe())
        return None
    return result


def _play(client: GameClient, token: str, read: Read, write: Write) -> bool:
    """True if the player quit (or the input ended), False if the session ended
    and the player should be taken back to the menu."""
    write("Welcome. Type help to see what you can do, or quit to leave.")
    try:
        while True:
            line = _ask(read, "> ")
            if line is None or line.strip().lower() in ("quit", "q"):
                return True
            if not line.strip():
                continue
            try:
                write(client.command(token, line))
            except SessionEnded as ended:
                write(ended.refusal.describe())
                return False
            except ConnectionError:
                write(_lost(line.strip()))
    finally:
        try:
            client.logout(token)
        except ConnectionError:
            pass  # the session ends on its own when the game is unreachable