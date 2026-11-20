"""Tests for UniverseServer: the Universe on its own thread."""

import threading
import unittest

from spaceknowledge.common.messages import Request, Response
from spaceknowledge.tests.transport.helpers import (
    WAIT,
    GatedUniverse,
    a_universe,
    add,
    in_thread,
    started,
)
from spaceknowledge.transport.call_queue import ServerStoppedError
from spaceknowledge.transport.universe_server import UniverseServer
from spaceknowledge.universe.universe import Universe
from spaceknowledge.world.world import World

LOGGER = "spaceknowledge.transport.universe_server"


class RecordingUniverse(Universe):
    """Remembers which thread each request was handled on."""

    def __init__(self, world: World) -> None:
        super().__init__(world)
        self.threads: list[str] = []

    def handle(self, request: Request) -> Response:
        self.threads.append(threading.current_thread().name)
        return super().handle(request)


class FlakyUniverse(Universe):
    """Fails once, with an error nobody planned for."""

    def __init__(self, world: World) -> None:
        super().__init__(world)
        self.fail_next = True

    def handle(self, request: Request) -> Response:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("boom")
        return super().handle(request)


class TestServing(unittest.TestCase):
    def test_a_request_is_answered_and_the_world_changes(self) -> None:
        universe, hall = a_universe(Universe)
        server = started(self, universe)
        self.assertTrue(server.call(add(), WAIT).ok)
        self.assertIsNotNone(hall.find_item("torch"))

    def test_the_universe_runs_on_its_own_thread(self) -> None:
        universe, _ = a_universe(RecordingUniverse)
        server = started(self, universe)
        server.call(add(), WAIT)
        self.assertEqual(["universe"], universe.threads)
        self.assertTrue(server.is_running())

    def test_many_callers_at_once_are_all_answered_by_the_one_thread(self) -> None:
        universe, hall = a_universe(RecordingUniverse)
        server = started(self, universe)
        answers: list[bool] = []

        def ask(number: int) -> None:
            answers.append(server.call(add(f"op{number}", f"item{number}"), WAIT).ok)

        callers = [in_thread(lambda n=n: ask(n)) for n in range(5)]
        for caller in callers:
            caller.join(WAIT)
        self.assertEqual([True] * 5, answers)
        self.assertEqual(5, hall.item_count())
        self.assertEqual(["universe"] * 5, universe.threads)

    def test_every_request_is_logged_once_by_the_universe_thread(self) -> None:
        universe, _ = a_universe(Universe)
        server = started(self, universe)
        with self.assertLogs(LOGGER, level="INFO") as logs:
            server.call(add(), WAIT)
        self.assertTrue(any("add_item torch by ada: ok" in line for line in logs.output))


class TestUnexpectedErrors(unittest.TestCase):
    def test_the_caller_gets_the_error_it_is_logged_and_the_thread_survives(self) -> None:
        universe, _ = a_universe(FlakyUniverse)
        server = started(self, universe)
        with self.assertLogs(LOGGER, level="ERROR") as logs:
            with self.assertRaisesRegex(RuntimeError, "boom"):
                server.call(add("op1"), WAIT)
        self.assertIn("op1", logs.output[0])
        self.assertTrue(server.is_running())
        self.assertTrue(server.call(add("op2"), WAIT).ok)


class TestLifecycle(unittest.TestCase):
    def test_stopping_ends_the_thread(self) -> None:
        universe, _ = a_universe(Universe)
        server = started(self, universe)
        server.stop()
        self.assertFalse(server.is_running())

    def test_stopping_twice_is_harmless(self) -> None:
        universe, _ = a_universe(Universe)
        server = started(self, universe)
        server.stop()
        server.stop()

    def test_a_call_after_the_stop_is_refused(self) -> None:
        universe, _ = a_universe(Universe)
        server = started(self, universe)
        server.stop()
        with self.assertRaises(ServerStoppedError):
            server.call(add(), WAIT)

    def test_a_call_before_the_start_is_refused(self) -> None:
        universe, _ = a_universe(Universe)
        with self.assertRaises(ServerStoppedError):
            UniverseServer(universe).call(add(), WAIT)

    def test_it_can_only_be_started_once(self) -> None:
        universe, _ = a_universe(Universe)
        server = started(self, universe)
        with self.assertRaises(RuntimeError):
            server.start()

    def test_a_stopped_server_cannot_be_started_again(self) -> None:
        universe, _ = a_universe(Universe)
        server = started(self, universe)
        server.stop()
        with self.assertRaises(RuntimeError):
            server.start()

    def test_a_stop_that_cannot_finish_says_so(self) -> None:
        universe, _ = a_universe(GatedUniverse)
        server = started(self, universe)
        self.addCleanup(universe.release.set)  # runs before the stop above
        caller = in_thread(lambda: server.call(add(), WAIT))
        self.assertTrue(universe.entered.wait(WAIT))
        with self.assertRaisesRegex(RuntimeError, "did not stop"):
            server.stop(timeout=0.05)
        universe.release.set()
        caller.join(WAIT)
        server.stop()
        self.assertFalse(server.is_running())

    def test_a_string_is_refused_where_a_class_is_expected(self) -> None:
        universe, _ = a_universe(Universe)
        server = started(self, universe)
        calls = [
            ("UniverseServer universe", lambda: UniverseServer("universe")),
            ("call request", lambda: server.call("request", WAIT)),
        ]
        for label, attempt in calls:
            with self.subTest(label):
                with self.assertRaisesRegex(TypeError, "must be"):
                    attempt()


if __name__ == "__main__":
    unittest.main()