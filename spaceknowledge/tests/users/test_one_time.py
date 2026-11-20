"""Tests for OneTimePasswords and the mailboxes."""

import shutil
import tempfile
import unittest
from pathlib import Path

from spaceknowledge.common.refusal import Refusal
from spaceknowledge.users.one_time import (
    FileMailbox,
    InMemoryMailbox,
    Mailbox,
    OneTimePasswords,
)


class Clock:
    """A clock the test moves by hand, so nothing ever sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FailingMailbox(Mailbox):
    def deliver(self, recipient: str, code: str, lifetime: float) -> None:
        raise OSError("mailbox full")


def an_office(lifetime: float = 300.0, attempts: int = 3):
    clock, mailbox = Clock(), InMemoryMailbox()
    codes = OneTimePasswords(
        ["root"], mailbox, clock=clock, lifetime=lifetime, max_attempts=attempts
    )
    return codes, mailbox, clock


def issued(codes: OneTimePasswords, mailbox: InMemoryMailbox) -> str:
    codes.request("root")
    return mailbox.messages[-1][1]


def wrong(code: str) -> str:
    return "0" * 8 if code != "0" * 8 else "1" * 8


class TestIssuing(unittest.TestCase):
    def test_a_request_writes_an_eight_digit_code_to_the_mailbox(self) -> None:
        codes, mailbox, _ = an_office()
        code = issued(codes, mailbox)
        self.assertEqual("root", mailbox.messages[-1][0])
        self.assertRegex(code, r"^\d{8}$")

    def test_an_unknown_admin_gets_nothing_and_is_not_told(self) -> None:
        codes, mailbox, _ = an_office()
        self.assertIsNone(codes.request("mallory"))
        self.assertEqual([], mailbox.messages)
        self.assertIsInstance(codes.redeem("mallory", "00000000"), Refusal)

    def test_names_are_not_case_sensitive(self) -> None:
        codes, mailbox, _ = an_office()
        codes.request("ROOT")
        self.assertIsNone(codes.redeem("Root", mailbox.messages[-1][1]))

    def test_a_new_request_replaces_the_old_code(self) -> None:
        codes, mailbox, _ = an_office()
        old = issued(codes, mailbox)
        new = issued(codes, mailbox)
        if old != new:
            self.assertIsInstance(codes.redeem("root", old), Refusal)
        self.assertIsNone(codes.redeem("root", new))

    def test_a_mailbox_that_fails_leaves_no_code_behind(self) -> None:
        codes = OneTimePasswords(["root"], FailingMailbox())
        with self.assertRaises(OSError):
            codes.request("root")
        self.assertIsInstance(codes.redeem("root", "00000000"), Refusal)


class TestRedeeming(unittest.TestCase):
    def test_the_right_code_works_exactly_once(self) -> None:
        codes, mailbox, _ = an_office()
        code = issued(codes, mailbox)
        self.assertIsNone(codes.redeem("root", code))
        self.assertIsInstance(codes.redeem("root", code), Refusal)

    def test_a_code_works_just_before_it_expires_and_not_at_the_moment_it_does(self) -> None:
        codes, mailbox, clock = an_office(lifetime=300.0)
        code = issued(codes, mailbox)
        clock.now += 299
        self.assertIsNone(codes.redeem("root", code))
        code = issued(codes, mailbox)
        clock.now += 300
        self.assertIsInstance(codes.redeem("root", code), Refusal)

    def test_two_wrong_guesses_do_not_spoil_the_right_one(self) -> None:
        codes, mailbox, _ = an_office(attempts=3)
        code = issued(codes, mailbox)
        codes.redeem("root", wrong(code))
        codes.redeem("root", wrong(code))
        self.assertIsNone(codes.redeem("root", code))

    def test_three_wrong_guesses_kill_the_code_even_for_the_right_answer(self) -> None:
        codes, mailbox, _ = an_office(attempts=3)
        code = issued(codes, mailbox)
        for _ in range(3):
            codes.redeem("root", wrong(code))
        self.assertIsInstance(codes.redeem("root", code), Refusal)

    def test_every_failure_gets_the_same_refusal_with_all_three_parts(self) -> None:
        codes, mailbox, clock = an_office()
        none_issued = codes.redeem("root", "12345678").describe()
        code = issued(codes, mailbox)
        wrong_code = codes.redeem("root", wrong(code)).describe()
        clock.now += 1000
        expired = codes.redeem("root", code).describe()
        self.assertEqual({none_issued}, {none_issued, wrong_code, expired})
        for part in ("Refused", "Why:", "Next:"):
            self.assertIn(part, none_issued)

    def test_a_refusal_never_contains_the_code(self) -> None:
        codes, mailbox, _ = an_office()
        code = issued(codes, mailbox)
        self.assertNotIn(code, codes.redeem("root", wrong(code)).describe())

    def test_an_enormous_code_is_refused(self) -> None:
        codes, mailbox, _ = an_office()
        issued(codes, mailbox)
        self.assertIsInstance(codes.redeem("root", "9" * 100000), Refusal)


class TestFileMailbox(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)

    def test_the_code_is_written_to_the_file_and_the_newest_wins(self) -> None:
        path = self.directory / "mail" / "admin_mailbox.txt"
        mailbox = FileMailbox(path)
        mailbox.deliver("root", "11111111", 300)
        mailbox.deliver("root", "22222222", 300)
        text = path.read_text(encoding="utf-8")
        self.assertIn("root", text)
        self.assertIn("22222222", text)
        self.assertNotIn("11111111", text)

    def test_it_works_with_the_real_thing(self) -> None:
        path = self.directory / "box.txt"
        codes = OneTimePasswords(["root"], FileMailbox(path))
        codes.request("root")
        code = path.read_text(encoding="utf-8").split("Code: ")[1][:8]
        self.assertIsNone(codes.redeem("root", code))


class TestArguments(unittest.TestCase):
    def test_bad_arguments_are_refused(self) -> None:
        box = InMemoryMailbox()
        with self.assertRaisesRegex(TypeError, "must be"):
            OneTimePasswords(["root"], "mailbox")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            OneTimePasswords(["R"], box)
        with self.assertRaises(ValueError):
            OneTimePasswords(["root"], box, lifetime=0)
        with self.assertRaises(ValueError):
            OneTimePasswords(["root"], box, max_attempts=0)
        codes = OneTimePasswords(["root"], box)
        with self.assertRaisesRegex(TypeError, "must be"):
            codes.redeem("root", 12345678)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            FileMailbox("box.txt")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Mailbox()  # type: ignore[abstract]


if __name__ == "__main__":
    unittest.main()