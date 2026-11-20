"""Shared helpers for the threading tests. Not a test module itself."""

import threading
import unittest
from collections.abc import Callable
from typing import TypeVar

from spaceknowledge.common.messages import Request, Response
from spaceknowledge.transport.universe_server import UniverseServer
from spaceknowledge.universe.universe import Universe
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World

# Seconds. A test only ever waits this long when it is already failing.
WAIT = 5

U = TypeVar("U", bound=Universe)


def add(op_id: str = "op1", item: str = "torch") -> Request:
    return Request(op_id, "add_item", "ada", item)


def a_universe(kind: type[U]) -> tuple[U, Destination]:
    """A one-destination Universe with ada in it. `kind` lets a test pass a
    subclass that records or blocks."""
    hall = Destination("hall", "Hall", "Cold and tiled.")
    universe = kind(World({"hall": hall}, "hall"))
    universe.place_player("ada", "hall")
    return universe, hall


def started(test: unittest.TestCase, universe: Universe) -> UniverseServer:
    """Start a server and promise to stop it, however the test ends."""
    server = UniverseServer(universe)
    server.start()
    test.addCleanup(server.stop)
    return server


def in_thread(target: Callable[[], object]) -> threading.Thread:
    """Run `target` on a helper thread. Daemon, so a failing test can never
    keep the test run alive."""
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread


class GatedUniverse(Universe):
    """A Universe that stops inside `handle` until the test lets it go.

    While it is stopped there, a request is "in flight": exactly the moment
    the professor's example is about.
    """

    def __init__(self, world: World) -> None:
        super().__init__(world)
        self.entered = threading.Event()
        self.release = threading.Event()

    def handle(self, request: Request) -> Response:
        self.entered.set()
        self.release.wait(WAIT)
        return super().handle(request)