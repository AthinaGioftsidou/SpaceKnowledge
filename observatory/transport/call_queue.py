"""The queue between the Broker's thread and the Universe's thread."""

import threading
from collections import deque
from typing import cast

from observatory.common.messages import Request, Response


class ServerStoppedError(ConnectionError):
    """The Universe thread is not taking requests: it was never started, or it
    has stopped. A ConnectionError, so callers can treat it like any other
    lost connection."""


class PendingCall:
    """A request waiting for its answer.

    The Broker's thread waits on it and the Universe's thread fills it in.
    Those two threads share only this object. The answer is stored BEFORE the
    event is set and read only AFTER the wait ends, which is what makes the
    hand-over safe without a lock.
    """

    def __init__(self, request: Request) -> None:
        if not isinstance(request, Request):
            raise TypeError(f"request must be a Request, not {type(request).__name__}")
        self._request = request
        self._done = threading.Event()
        self._response: Response | None = None
        self._error: Exception | None = None

    @property
    def request(self) -> Request:
        return self._request

    def complete(self, response: Response) -> None:
        """Called by the Universe thread: here is the answer."""
        if not isinstance(response, Response):
            raise TypeError(f"response must be a Response, not {type(response).__name__}")
        self._response = response
        self._done.set()

    def fail(self, error: Exception) -> None:
        """Called by the Universe thread: it could not answer."""
        if not isinstance(error, Exception):
            raise TypeError(f"error must be an Exception, not {type(error).__name__}")
        self._error = error
        self._done.set()

    def wait(self, timeout: float) -> Response:
        """Called by the Broker's thread. Returns the answer, re-raises the
        Universe's error, or raises TimeoutError if neither arrives in time."""
        if not self._done.wait(timeout):
            raise TimeoutError(f"no answer to {self._request.op_id} within {timeout} seconds")
        if self._error is not None:
            raise self._error
        # The event guarantees that one of the two was set. `cast` only tells
        # the type checker so; it does nothing when the program runs.
        return cast(Response, self._response)


class CallQueue:
    """First in, first out, and every access takes the lock.

    `pop` waits for work instead of polling. When the queue is closed, calls
    already queued are still served; only then does `pop` return None.
    """

    def __init__(self) -> None:
        self._items: deque[PendingCall] = deque()
        self._condition = threading.Condition()
        self._closed = False

    def push(self, call: PendingCall) -> None:
        if not isinstance(call, PendingCall):
            raise TypeError(f"call must be a PendingCall, not {type(call).__name__}")
        with self._condition:
            if self._closed:
                raise ServerStoppedError("the Universe server is not taking requests")
            self._items.append(call)
            self._condition.notify()

    def pop(self) -> PendingCall | None:
        """The next call, waiting for one if needed. None only when the queue
        is closed AND empty."""
        with self._condition:
            while not self._items and not self._closed:
                self._condition.wait()
            if self._items:
                return self._items.popleft()
            return None

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def size(self) -> int:
        with self._condition:
            return len(self._items)