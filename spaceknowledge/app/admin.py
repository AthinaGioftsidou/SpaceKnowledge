"""The admin's side: a one-time-code login and read-only queries."""

from pathlib import Path

from spaceknowledge.app.paths import ACCOUNTS_FILE, MAILBOX_FILE
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.users.account_repository import AccountRepository, JsonAccountRepository
from spaceknowledge.users.admin_gate import AdminGate
from spaceknowledge.users.one_time import FileMailbox, OneTimePasswords


class AdminOffice:
    """What an administrator may do. Nothing here plays the game.

    Until the servers talk over sockets, this reads the saved account file
    fresh on every query instead of asking the running game.
    """

    def __init__(self, gate: AdminGate, accounts: AccountRepository, mailbox_path: Path) -> None:
        if not isinstance(gate, AdminGate):
            raise TypeError(f"gate must be an AdminGate, not {type(gate).__name__}")
        if not isinstance(accounts, AccountRepository):
            raise TypeError(f"accounts must be an AccountRepository, not {type(accounts).__name__}")
        if not isinstance(mailbox_path, Path):
            raise TypeError(f"mailbox_path must be a Path, not {type(mailbox_path).__name__}")
        self._gate = gate
        self._accounts = accounts
        self._mailbox_path = mailbox_path

    @property
    def mailbox_path(self) -> Path:
        return self._mailbox_path

    def request_code(self, admin: str) -> None:
        self._gate.request_code(admin)

    def login(self, admin: str, code: str) -> str | Refusal:
        return self._gate.login(admin, code)

    def logout(self, token: str) -> bool:
        return self._gate.logout(token)

    def players(self, token: str) -> list[str] | Refusal:
        """The registered player names, sorted, for a valid admin token."""
        if self._gate.admin_for(token) is None:
            return Refusal(
                "list the players",
                "you are not logged in as an administrator",
                "log in with a one-time code first",
            )
        return sorted(self._accounts.load())


def build_admin(state_dir: Path, admins: tuple[str, ...] = ("root",)) -> AdminOffice:
    """An office whose codes are written to a file in the state folder."""
    if not isinstance(state_dir, Path):
        raise TypeError(f"state_dir must be a Path, not {type(state_dir).__name__}")
    mailbox_path = state_dir / MAILBOX_FILE
    codes = OneTimePasswords(admins, FileMailbox(mailbox_path))
    return AdminOffice(
        AdminGate(codes), JsonAccountRepository(state_dir / ACCOUNTS_FILE), mailbox_path
    )