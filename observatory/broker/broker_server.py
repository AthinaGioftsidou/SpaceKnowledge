"""The Broker on its own thread."""

import logging
import threading
from dataclasses import dataclass

from observatory.broker.broker import Broker
from observatory.broker.parser import Parser
from observatory.broker.session import Session
from observatory.common.refusal import Refusal
from observatory.transport.work_queue import ServerStoppedError, Ticket, WorkQueue

# Where these lines go is decided once, by the program that opens the log.
# The NullHandler keeps this logger silent when no log file is open.
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


@dataclass(frozen=True)
class Line:
    """What one player typed. Read-only."""

    player_id: str
    text: str


class BrokerServer:
    """Runs a Broker on its own thread and feeds it from a queue of lines.

    A consumer of player lines, and, through the Broker's channel, a producer
    for the Universe thread. After `start`, only this thread touches the
    Broker, so the Broker needs no lock. Set the Broker up (players, recover)
    BEFORE starting. Stop this server BEFORE the Universe server, because it
    may still be waiting on the Universe while it drains its queue.
    """

    THREAD_NAME = "broker"

    def __init__(self, broker: Broker, parser: Parser | None = None) -> None:
        if not isinstance(broker, Broker):
            raise TypeError(f"broker must be a Broker, not {type(broker).__name__}")
        if parser is not None and not isinstance(parser, Parser):
            raise TypeError(f"parser must be a Parser, not {type(parser).__name__}")
        self._broker = broker
        self._parser = parser if parser is not None else Parser()
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

    def submit(self, player_id: str, text: str, timeout: float = 5.0) -> str:
        """The producer side. Runs on the CALLER's thread: queue the line, then
        wait for the Broker thread to answer it."""
        if not player_id:
            raise ValueError("player_id must not be empty")
        if not isinstance(text, str):
            raise TypeError(f"text must be a str, not {type(text).__name__}")
        if self._thread is None:
            raise ServerStoppedError("the Broker server has not been started")
        ticket: Ticket[Line, str] = Ticket(Line(player_id, text))
        self._queue.push(ticket)
        return ticket.wait(timeout)

    def _run(self) -> None:
        """The consume loop. Ends when the queue is closed and empty."""
        while True:
            ticket = self._queue.pop()
            if ticket is None:
                return
            self._serve(ticket)

    def _serve(self, ticket: Ticket[Line, str]) -> None:
        line = ticket.payload
        try:
            reply = Session(self._broker, self._parser, line.player_id).submit(line.text)
        except (ConnectionError, TimeoutError) as lost:
            # The Universe did not answer. The operation is saved as pending,
            # so it is not lost; the player is told what happened.
            log.warning("%s: the Universe did not answer (%s)", line.player_id, lost)
            reply = Refusal(
                line.text.strip() or "an empty line",
                "the Universe did not answer",
                "your action is saved and will be finished the next time the game starts",
            ).describe()
        except Exception as error:
            # The top of this thread, so the one place a broad catch belongs.
            # It logs with context and hands the error to the waiting caller.
            log.exception("%s typed %r and it failed", line.player_id, line.text.strip())
            ticket.fail(error)
            return
        log.info("%s typed %r, reply: %s", line.player_id, line.text.strip(), reply.split("\n", 1)[0])
        ticket.complete(reply)