"""The customer console: register or log in, then play. It contains no admin
operation, not even a hidden one."""

from collections.abc import Callable

from observatory.app.front import Front
from observatory.common.refusal import Refusal

Read = Callable[[str], str]
Write = Callable[[str], None]


def _ask(read: Read, prompt: str) -> str | None:
    """One line, or None at the end of the input."""
    try:
        return read(prompt)
    except EOFError:
        return None


def _unavailable(what: str) -> str:
    return Refusal(what, "the game did not answer", "try again in a moment").describe()


def run_customer(front: Front, read: Read, read_secret: Read, write: Write) -> None:
    """The menu, then the game. `read_secret` asks for passwords without
    showing them. The program ends when the player quits."""
    if not isinstance(front, Front):
        raise TypeError(f"front must be a Front, not {type(front).__name__}")
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
            _register(front, read, read_secret, write)
        elif choice == "login":
            token = _login(front, read, read_secret, write)
            if token is not None:
                _play(front, token, read, write)
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


def _register(front: Front, read: Read, read_secret: Read, write: Write) -> None:
    given = _credentials(read, read_secret)
    if given is None:
        return
    try:
        refusal = front.register(*given)
    except OSError:
        write(Refusal("register", "the account could not be saved", "try again in a moment").describe())
        return
    write("Account created. Now type login." if refusal is None else refusal.describe())


def _login(front: Front, read: Read, read_secret: Read, write: Write) -> str | None:
    given = _credentials(read, read_secret)
    if given is None:
        return None
    try:
        result = front.login(*given)
    except (ConnectionError, TimeoutError):
        write(_unavailable("log in"))
        return None
    if isinstance(result, Refusal):
        write(result.describe())
        return None
    return result


def _play(front: Front, token: str, read: Read, write: Write) -> None:
    write("Welcome. Type help to see what you can do, or quit to leave.")
    try:
        while True:
            line = _ask(read, "> ")
            if line is None or line.strip().lower() in ("quit", "q"):
                return
            if not line.strip():
                continue
            try:
                write(front.submit(token, line))
            except (ConnectionError, TimeoutError):
                write(_unavailable(line.strip()))
    finally:
        front.logout(token)