"""Tests for the generic Ticket and WorkQueue."""

import threading
import unittest

from observatory.tests.transport.helpers import WAIT, in_thread
from observatory.transport.work_queue import ServerStoppedError, Ticket, WorkQueue


def waiting_pop(queue: WorkQueue[str]) -> tuple[threading.Event, list[str | None]]:
    got: list[str | None] = []
    done = threading.Event()

    def consume() -> None:
        got.append(queue.pop())
        done.set()

    in_thread(consume)
    return done, got


class TestTicket(unittest.TestCase):
    def test_it_keeps_its_payload(self) -> None:
        self.assertEqual("line", Ticket[str, str]("line").payload)

    def test_an_answer_given_by_another_thread_is_waited_for(self) -> None:
        ticket = Ticket[str, str]("line")
        in_thread(lambda: ticket.complete("reply"))
        self.assertEqual("reply", ticket.wait(WAIT))

    def test_a_failure_is_raised_in_the_waiting_thread(self) -> None:
        ticket = Ticket[str, str]("line")
        ticket.fail(RuntimeError("boom"))
        with self.assertRaisesRegex(RuntimeError, "boom"):
            ticket.wait(WAIT)

    def test_no_answer_in_time_is_a_timeout(self) -> None:
        with self.assertRaises(TimeoutError):
            Ticket[str, str]("line").wait(0.01)

    def test_a_string_is_refused_where_an_error_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            Ticket[str, str]("line").fail("boom")  # type: ignore[arg-type]


class TestWorkQueue(unittest.TestCase):
    def test_first_in_first_out(self) -> None:
        queue = WorkQueue[str]()
        queue.push("a")
        queue.push("b")
        self.assertEqual(2, queue.size())
        self.assertEqual("a", queue.pop())
        self.assertEqual("b", queue.pop())

    def test_a_waiting_pop_receives_work_that_arrives_later(self) -> None:
        queue = WorkQueue[str]()
        done, got = waiting_pop(queue)
        queue.push("a")
        self.assertTrue(done.wait(WAIT))
        self.assertEqual(["a"], got)

    def test_closing_wakes_a_waiting_pop_with_none(self) -> None:
        queue = WorkQueue[str]()
        done, got = waiting_pop(queue)
        queue.close()
        self.assertTrue(done.wait(WAIT))
        self.assertEqual([None], got)

    def test_work_queued_before_the_close_is_still_served(self) -> None:
        queue = WorkQueue[str]()
        queue.push("a")
        queue.close()
        self.assertEqual("a", queue.pop())
        self.assertIsNone(queue.pop())

    def test_pushing_after_the_close_is_refused(self) -> None:
        queue = WorkQueue[str]()
        queue.close()
        with self.assertRaises(ServerStoppedError):
            queue.push("a")
        self.assertEqual(0, queue.size())


if __name__ == "__main__":
    unittest.main()