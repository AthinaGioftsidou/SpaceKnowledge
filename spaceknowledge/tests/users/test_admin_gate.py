"""Tests for AdminGate."""

import unittest

from spaceknowledge.common.refusal import Refusal
from spaceknowledge.users.admin_gate import AdminGate
from spaceknowledge.users.one_time import InMemoryMailbox, OneTimePasswords
from spaceknowledge.users.session_book import SessionBook

LOGGER = "spaceknowledge.users.admin_gate"


def a_gate() -> tuple[AdminGate, InMemoryMailbox]:
    mailbox = InMemoryMailbox()
    return AdminGate(OneTimePasswords(["root"], mailbox)), mailbox


def code_for(gate: AdminGate, mailbox: InMemoryMailbox) -> str:
    gate.request_code("root")
    return mailbox.messages[-1][1]


class TestAdminGate(unittest.TestCase):
    def test_the_emailed_code_gives_an_admin_token(self) -> None:
        gate, mailbox = a_gate()
        token = gate.login("root", code_for(gate, mailbox))
        self.assertIsInstance(token, str)
        self.assertEqual("root", gate.admin_for(token))

    def test_a_wrong_code_gives_a_refusal_and_no_token(self) -> None:
        gate, mailbox = a_gate()
        code_for(gate, mailbox)
        self.assertIsInstance(gate.login("root", "00000000x"), Refusal)

    def test_a_code_cannot_log_in_twice(self) -> None:
        gate, mailbox = a_gate()
        code = code_for(gate, mailbox)
        gate.login("root", code)
        self.assertIsInstance(gate.login("root", code), Refusal)

    def test_a_customer_token_is_not_an_admin_token(self) -> None:
        gate, _ = a_gate()
        customer_token = SessionBook().open("root")
        self.assertIsNone(gate.admin_for(customer_token))

    def test_logging_out_ends_the_session(self) -> None:
        gate, mailbox = a_gate()
        token = gate.login("root", code_for(gate, mailbox))
        self.assertTrue(gate.logout(token))
        self.assertIsNone(gate.admin_for(token))

    def test_the_log_names_a_failed_login_but_never_the_code(self) -> None:
        gate, mailbox = a_gate()
        code_for(gate, mailbox)
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            gate.login("root", "99999999")
        text = "\n".join(logs.output)
        self.assertIn("root", text)
        self.assertNotIn("99999999", text)

    def test_bad_arguments_are_refused(self) -> None:
        gate, _ = a_gate()
        with self.assertRaisesRegex(TypeError, "must be"):
            AdminGate("codes")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            AdminGate(OneTimePasswords(["root"], InMemoryMailbox()), "book")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            gate.admin_for(5)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()