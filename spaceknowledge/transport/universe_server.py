"""The Universe on its own thread."""

import logging
import threading

from spaceknowledge.common.messages import Request, Response
from spaceknowledge.transport.call_queue import CallQueue, PendingCall, ServerStoppedError
from spaceknowledge.universe.universe import Universe

# Where these lines go is decided once, by the program that opens the log.
# The NullHandler keeps this logger silent when no log file is open.
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class UniverseServer:
    """Runs a Universe on its own thread and feeds it from a queue.

    The consumer side. After `start`, only the Universe thread touches the
    Universe, so the world needs no lock. Set the Universe up (place players,
    load its state) BEFORE starting. Always call `stop`: the thread is not a
    daemon, so a program that forgets will not exit.
    """

    THREAD_NAME = "universe"

    def __init__(self, universe: Universe) -> None:
        if not isinstance(universe, Universe):
            raise TypeError(f"universe must be a Universe, not {type(universe).__name__}")
        self._universe = universe
        self._queue = CallQueue()
        self._thread: threading.Thread | None = None
        self._stopped = False

    def start(self) -> None:
        if self._thread is not None or self._stopped:
            raise RuntimeError("the Universe server can only be started once")
        self._thread = threading.Thread(target=self._run, name=self.THREAD_NAME)
        self._thread.start()
        log.info("started")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop taking requests, answer the ones already queued, and wait for
        the thread to end. Raises RuntimeError if it does not end in time."""
        self._stopped = True
        self._queue.close()
        thread = self._thread
        if thread is None:
            return
        thread.join(timeout)
        if thread.is_alive():
            raise RuntimeError(f"the Universe thread did not stop within {timeout} seconds")
        log.info("stopped")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def call(self, request: Request, timeout: float) -> Response:
        if not isinstance(request, Request):
            raise TypeError(f"request must be a Request, not {type(request).__name__}")
        if self._thread is None:
            raise ServerStoppedError("the Universe server has not been started")
        pending = PendingCall(request)
        self._queue.push(pending)
        return pending.wait(timeout)

    def _run(self) -> None:
        while True:
            call = self._queue.pop()
            if call is None:
                return
            self._serve(call)

    def _serve(self, call: PendingCall) -> None:
        request = call.request
        try:
            response = self._universe.handle(request)
        except Exception as error:
            log.exception(
                "request %s (%s %s by %s) failed",
                request.op_id, request.action, request.item_id, request.player_id,
            )
            call.fail(error)
            return
        log.info(
            "%s %s by %s: %s",
            request.action, request.item_id, request.player_id,
            "ok" if response.ok else "refused",
        )
        call.complete(response)