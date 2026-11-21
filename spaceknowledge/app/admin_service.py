"""AdminService: everything an administrator may do, decided by the server."""

import logging
from typing import Any

from spaceknowledge.broker.broker_server import BrokerServer
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.users.accounts import AccountRegistry
from spaceknowledge.users.admin_gate import AdminGate

# Where these lines go is decided once, by the program that opens the log.
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class AdminService:
    """Admin identity is kept apart from the customer's: admin tokens come from
    the gate's own session book, and only a one-time code from the mailbox
    creates one. Every read is checked here and written to the log with the
    admin's name. An admin can read, and cannot play or change anything."""

    def __init__(
        self, gate: AdminGate, accounts: AccountRegistry, server: BrokerServer, broker_name: str
    ) -> None:
        if not isinstance(gate, AdminGate):
            raise TypeError(f"gate must be an AdminGate, not {type(gate).__name__}")
        if not isinstance(accounts, AccountRegistry):
            raise TypeError(f"accounts must be an AccountRegistry, not {type(accounts).__name__}")
        if not isinstance(server, BrokerServer):
            raise TypeError(f"server must be a BrokerServer, not {type(server).__name__}")
        if not broker_name:
            raise ValueError("broker_name must not be empty")
        self._gate = gate
        self._accounts = accounts
        self._server = server
        self._broker_name = broker_name

    def request_code(self, admin: str) -> None:
        """Write a one-time code to the mailbox. Says nothing either way."""
        self._gate.request_code(admin)

    def login(self, admin: str, code: str) -> str | Refusal:
        """An admin token, or the reason the login was refused."""
        return self._gate.login(admin, code)

    def logout(self, token: str) -> bool:
        return self._gate.logout(token)

    def players(self, token: str) -> list[str] | Refusal:
        """The registered players of this Broker."""
        admin = self._admin(token, "list the players")
        if isinstance(admin, Refusal):
            return admin
        log.info("%s listed the players", admin)
        return self._accounts.names()

    def stats(self, token: str) -> dict[str, Any] | Refusal:
        """How this Broker is doing: queue depth, pending operations, recovery
        and latency."""
        admin = self._admin(token, "read the statistics")
        if isinstance(admin, Refusal):
            return admin
        log.info("%s read the broker statistics", admin)
        snapshot = self._server.stats()
        snapshot["broker"] = self._broker_name
        snapshot["registered_players"] = len(self._accounts.names())
        return snapshot

    def _admin(self, token: str, what: str) -> str | Refusal:
        admin = self._gate.admin_for(token)
        if admin is None:
            return Refusal(
                what,
                "you are not logged in as an administrator",
                "log in with a one-time code first",
            )
        return admin