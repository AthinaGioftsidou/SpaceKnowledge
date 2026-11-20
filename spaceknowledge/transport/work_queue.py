"""A generic ticket and queue, shared by the Universe thread and the Broker thread."""

import threading
from collections import deque
from typing import cast


class ServerStoppedError(ConnectionError):
    """A thread is not taking work: it was never started, or it has stopped.
    A ConnectionError, so callers can treat it like any other lost connection."""


class Ticket[Q, A]:
    """A piece of work waiting for its answer."""

    def __init__(self, payload: Q) -> None:
        self._payload = payload
        self._done = threading.Event()
        self._answer: A | None = None
        self._error: Exception | None = None

    @property
    def payload(self) -> Q:
        return self._payload

    def complete(self, answer: A) -> None:
        """Called by the consumer thread: here is the answer."""
        self._answer = answer
        self._done.set()

    def fail(self, error: Exception) -> None:
        """Called by the consumer thread: it could not answer."""
        if not isinstance(error, Exception):
            raise TypeError(f"error must be an Exception, not {type(error).__name__}")
        self._error = error
        self._done.set()

    def wait(self, timeout: float) -> A:
        """Called by the producer thread. Returns the answer, re-raises the
        consumer's error, or raises TimeoutError if neither arrives in time."""
        if not self._done.wait(timeout):
            raise TimeoutError(f"no answer within {timeout} seconds")
        if self._error is not None:
            raise self._error
        # The event guarantees that one of the two was set. `cast` only tells
        # the type checker so; it does nothing when the program runs.
        return cast("A", self._answer)


class WorkQueue[W]:
    """First in, first out, and every access takes the lock.

    `pop` waits for work instead of polling. When the queue is closed, work
    already queued is still served; only then does `pop` return None.
    """

    def __init__(self) -> None:
        self._items: deque[W] = deque()
        self._condition = threading.Condition()
        self._closed = False

    def push(self, item: W) -> None:
        with self._condition:
            if self._closed:
                raise ServerStoppedError("the server is not taking work")
            self._items.append(item)
            self._condition.notify()

    def pop(self) -> W | None:
        """The next item, waiting for one if needed. None only when the queue
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