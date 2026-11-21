"""The Broker on its own thread."""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.metrics import BrokerMetrics
from spaceknowledge.broker.parser import Parser
from spaceknowledge.broker.session import Session
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.transport.work_queue import ServerStoppedError, Ticket, WorkQueue

# Where these lines go is decided once, by the program that opens the log.
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


@dataclass(frozen=True)
class Line:
    """What one player sent. Read-only. A typed line has text; a join has a
    destination instead."""

    player_id: str
    text: str
    join_to: str | None = None


class BrokerServer:
    """Runs a Broker on its own thread and feeds it from a queue of lines.

    A consumer of player lines, and, through the Broker's channel, a producer
    for the world behind it. After `start`, only this thread touches the
    Broker, so the Broker needs no lock. Set the Broker up (recover) BEFORE
    starting. Stop this server BEFORE the world behind it, because it may still
    be waiting on it while it drains its queue.

    Every line is timed and counted in `BrokerMetrics`, which the admin reads
    through `stats`. The clock is a parameter so tests never sleep.
    """

    THREAD_NAME = "broker"

    def __init__(
        self,
        broker: Broker,
        parser: Parser | None = None,
        metrics: BrokerMetrics | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(broker, Broker):
            raise TypeError(f"broker must be a Broker, not {type(broker).__name__}")
        if parser is not None and not isinstance(parser, Parser):
            raise TypeError(f"parser must be a Parser, not {type(parser).__name__}")
        if metrics is not None and not isinstance(metrics, BrokerMetrics):
            raise TypeError(f"metrics must be a BrokerMetrics, not {type(metrics).__name__}")
        self._broker = broker
        self._parser = parser if parser is not None else Parser()
        self._metrics = metrics if metrics is not None else BrokerMetrics()
        self._clock = clock
        self._queue: WorkQueue[Ticket[Line, str]] = WorkQueue()
        self._thread: threading.Thread | None = None
        self._stopped = False

    def start(self) -> None:
        if self._thread is not None or self._stopped:
            raise RuntimeError("the Broker server can only be started once")
        self._thread = threading.Thread(target=self._run, name=self.THREAD_NAME)
        self._thread.start()
        log.info("started")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop taking lines, answer the ones already queued, and wait for the
        thread to end. Raises RuntimeError if it does not end in time."""
        self._stopped = True
        self._queue.close()
        thread = self._thread
        if thread is None:
            return
        thread.join(timeout)
        if thread.is_alive():
            raise RuntimeError(f"the Broker thread did not stop within {timeout} seconds")
        log.info("stopped")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stats(self) -> dict[str, Any]:
        """What the admin sees: the counters and latency, plus the queue depth
        (how many lines are waiting) and whether the thread is alive."""
        snapshot = self._metrics.snapshot()
        snapshot["queue_depth"] = self._queue.size()
        snapshot["broker_thread_running"] = self.is_running()
        return snapshot

    def submit(self, player_id: str, text: str, timeout: float = 5.0) -> str:
        """The producer side. Runs on the CALLER's thread: queue the line, then
        wait for the Broker thread to answer it."""
        if not player_id:
            raise ValueError("player_id must not be empty")
        if not isinstance(text, str):
            raise TypeError(f"text must be a str, not {type(text).__name__}")
        return self._ask(Line(player_id, text), timeout)

    def join(self, player_id: str, destination: str, timeout: float = 5.0) -> str:
        """Create the player if new and place them at `destination`, on the
        Broker thread. Returns "" if all is well, otherwise the refusal text."""
        if not player_id:
            raise ValueError("player_id must not be empty")
        if not destination:
            raise ValueError("destination must not be empty")
        return self._ask(Line(player_id, "", destination), timeout)

    def _ask(self, line: Line, timeout: float) -> str:
        if self._thread is None:
            raise ServerStoppedError("the Broker server has not been started")
        ticket: Ticket[Line, str] = Ticket(line)
        self._queue.push(ticket)
        return ticket.wait(timeout)

    def _run(self) -> None:
        """The consume loop. Ends when the queue is closed and empty."""
        while True:
            ticket = self._queue.pop()
            if ticket is None:
                return
            self._serve(ticket)

    def _reply(self, line: Line) -> str:
        if line.join_to is not None:
            refusal = self._broker.join(line.player_id, line.join_to)
            return "" if refusal is None else refusal.describe()
        return Session(self._broker, self._parser, line.player_id).submit(line.text)

    def _finish(self, started: float, outcome: str) -> None:
        """Record the numbers BEFORE the caller is answered, so a client that
        asks for the stats right after its reply always sees this line counted."""
        self._metrics.record((self._clock() - started) * 1000, outcome)
        self._metrics.set_pending(self._broker.pending_count())

    def _serve(self, ticket: Ticket[Line, str]) -> None:
        line = ticket.payload
        what = f"join {line.join_to}" if line.join_to is not None else line.text.strip()
        started = self._clock()
        outcome = "served"
        try:
            reply = self._reply(line)
        except (ConnectionError, TimeoutError) as lost:
            # The world did not answer. The operation is saved as pending, so it
            # is not lost; the player is told what happened.
            outcome = "lost"
            log.warning("%s: the Universe did not answer (%s)", line.player_id, lost)
            reply = Refusal(
                what or "an empty line",
                "the Universe did not answer",
                "if it changed anything, it is saved and will be finished the next time the game starts",
            ).describe()
        except Exception as error:
            # The top of this thread, so the one place a broad catch belongs.
            # It logs with context and hands the error to the waiting caller.
            log.exception("%s sent %r and it failed", line.player_id, what)
            self._finish(started, "failed")
            ticket.fail(error)
            return
        self._finish(started, outcome)
        log.info("%s sent %r, reply: %s", line.player_id, what, reply.split("\n", 1)[0])
        ticket.complete(reply)