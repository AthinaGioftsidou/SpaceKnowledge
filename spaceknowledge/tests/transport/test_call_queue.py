"""Tests for PendingCall and CallQueue."""

import threading
import unittest

from spaceknowledge.common.messages import Response
from spaceknowledge.tests.transport.helpers import WAIT, add, in_thread
from spaceknowledge.transport.call_queue import CallQueue, PendingCall, ServerStoppedError


def a_call(op_id: str = "op1") -> PendingCall:
    return PendingCall(add(op_id))


def waiting_pop(queue: CallQueue) -> tuple[threading.Event, list[PendingCall | None]]:
    """Start a thread that pops once. Returns an event that is set when the
    pop has finished, and the list its result lands in."""
    got: list[PendingCall | None] = []
    done = threading.Event()

    def consume() -> None:
        got.append(queue.pop())
        done.set()

    in_thread(consume)
    return done, got


class TestPendingCall(unittest.TestCase):
    def test_an_answer_is_handed_over(self) -> None:
        call, response = a_call(), Response("op1")
        call.complete(response)
        self.assertIs(response, call.wait(WAIT))

    def test_an_answer_given_by_another_thread_is_waited_for(self) -> None:
        call, response = a_call(), Response("op1")
        in_thread(lambda: call.complete(response))
        self.assertIs(response, call.wait(WAIT))

    def test_a_failure_is_raised_in_the_waiting_thread(self) -> None:
        call = a_call()
        call.fail(RuntimeError("boom"))
        with self.assertRaisesRegex(RuntimeError, "boom"):
            call.wait(WAIT)

    def test_no_answer_in_time_is_a_timeout(self) -> None:
        with self.assertRaises(TimeoutError):
            a_call().wait(0.01)

    def test_a_string_is_refused_where_a_class_is_expected(self) -> None:
        call = a_call()
        bad = "not an object"
        calls = [
            ("PendingCall request", lambda: PendingCall(bad)),
            ("complete response", lambda: call.complete(bad)),
            ("fail error", lambda: call.fail(bad)),
        ]
        for label, attempt in calls:
            with self.subTest(label):
                with self.assertRaisesRegex(TypeError, "must be"):
                    attempt()


class TestCallQueue(unittest.TestCase):
    def test_a_new_queue_is_empty(self) -> None:
        self.assertEqual(0, CallQueue().size())

    def test_calls_come_out_first_in_first_out(self) -> None:
        queue, first, second = CallQueue(), a_call("op1"), a_call("op2")
        queue.push(first)
        queue.push(second)
        self.assertEqual(2, queue.size())
        self.assertIs(first, queue.pop())
        self.assertIs(second, queue.pop())

    def test_a_waiting_pop_receives_a_call_that_arrives_later(self) -> None:
        queue, call = CallQueue(), a_call()
        done, got = waiting_pop(queue)
        queue.push(call)
        self.assertTrue(done.wait(WAIT))
        self.assertIs(call, got[0])

    def test_closing_an_empty_queue_gives_none(self) -> None:
        queue = CallQueue()
        queue.close()
        self.assertIsNone(queue.pop())

    def test_closing_wakes_a_waiting_pop(self) -> None:
        queue = CallQueue()
        done, got = waiting_pop(queue)
        queue.close()
        self.assertTrue(done.wait(WAIT))
        self.assertEqual([None], got)

    def test_calls_queued_before_the_close_are_still_served(self) -> None:
        queue, call = CallQueue(), a_call()
        queue.push(call)
        queue.close()
        self.assertIs(call, queue.pop())
        self.assertIsNone(queue.pop())

    def test_pushing_after_the_close_is_refused_and_changes_nothing(self) -> None:
        queue = CallQueue()
        queue.close()
        with self.assertRaises(ServerStoppedError):
            queue.push(a_call())
        self.assertEqual(0, queue.size())

    def test_closing_twice_is_harmless(self) -> None:
        queue = CallQueue()
        queue.close()
        queue.close()

    def test_a_string_is_refused_where_a_call_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            CallQueue().push("call")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()