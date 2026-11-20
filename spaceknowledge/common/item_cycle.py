"""THE ITEM CYCLE. Three states, two processes.

    DROP:  owned(Broker) -> flight(Broker) -> done(Universe)
                                                 |  the item lies on the ground
    PICK:                                     owned(Universe) -> flight(Universe) -> done(Broker)
                                                                                         |
                                                                       back to the start of DROP

A STATE says where an item is in a process:
    owned   at rest, before the process begins
    flight  between the servers, waiting for the Universe's answer, locked
    done    the process has finished

A PROCESS (drop or pick) says who holds the item in each state. The end of one
process is the start of the next, so the loop closes.

Only drop and pick use this. Mining is a plain request with no states.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from spaceknowledge.common.refusal import Refusal

BROKER = "broker"
UNIVERSE = "universe"

OWNED = "owned"
FLIGHT = "flight"
DONE = "done"


@dataclass(frozen=True)
class Process:
    """One process: its words, who holds the item in each state, and the advice
    to give when a move is refused. Read-only."""

    name: str
    label: str
    owned_by: str
    flight_by: str
    done_by: str
    owned_advice: str
    done_advice: str

    def __post_init__(self) -> None:
        for text in (self.name, self.label, self.owned_advice, self.done_advice):
            if not text:
                raise ValueError("every word of a process must be filled in")
        for holder in (self.owned_by, self.flight_by, self.done_by):
            if holder not in (BROKER, UNIVERSE):
                raise ValueError(f"a holder must be {BROKER} or {UNIVERSE}, not {holder}")

    def holder(self, state: str) -> str:
        """BROKER or UNIVERSE: who holds the item in this state."""
        return {OWNED: self.owned_by, FLIGHT: self.flight_by, DONE: self.done_by}[state]


DROP = Process(
    "drop", "drop", BROKER, BROKER, UNIVERSE,
    "the item is yours, so you can drop it",
    "the item is lying on the ground, so pick it up to own it",
)
PICK = Process(
    "pick", "pick up", UNIVERSE, UNIVERSE, BROKER,
    "the item is lying on the ground, so pick it up to own it",
    "the item is yours again, so you can drop it",
)

# What follows each process once it is done.
_NEXT = {DROP.name: PICK, PICK.name: DROP}


class State(ABC):
    """One class per state, so ItemCycle never asks which one it is in.

    Each move returns the next state and a Refusal or None. The default is to
    refuse and stay, so a state lists only the moves it ALLOWS.
    """

    @abstractmethod
    def name(self) -> str:
        """OWNED, FLIGHT or DONE."""

    @abstractmethod
    def advice(self, process: Process) -> str:
        """What the player can do next when a move is refused here."""

    def begin(self, process: Process, subject: str) -> tuple[State, Refusal | None]:
        return self, self.refuse("begin", process, subject, process)

    def finish(self, process: Process, subject: str) -> tuple[State, Refusal | None]:
        return self, self.refuse("finish", process, subject, process)

    def cancel(self, process: Process, subject: str) -> tuple[State, Refusal | None]:
        return self, self.refuse("cancel", process, subject, process)

    def refuse(self, move: str, wanted: Process, subject: str, current: Process) -> Refusal:
        """TEMPLATE METHOD: every refusal is built one way. `wanted` is the
        process that was asked for, `current` the one the item is in."""
        what = {
            "begin": f"{wanted.label} {subject}",
            "finish": f"finish the {wanted.label} of {subject}",
            "cancel": f"cancel the {wanted.label} of {subject}",
        }[move]
        why = (
            f"the {subject} is {self.name()} in the {current.name} process, "
            f"held by the {current.holder(self.name())}"
        )
        return Refusal(what, why, self.advice(current))


class OwnedState(State):
    def name(self) -> str:
        return OWNED

    def advice(self, process: Process) -> str:
        return process.owned_advice

    def begin(self, process: Process, subject: str) -> tuple[State, Refusal | None]:
        return FlightState(), None


class FlightState(State):
    def name(self) -> str:
        return FLIGHT

    def advice(self, process: Process) -> str:
        return "wait for the Universe to answer, then try again"

    def finish(self, process: Process, subject: str) -> tuple[State, Refusal | None]:
        return DoneState(), None

    def cancel(self, process: Process, subject: str) -> tuple[State, Refusal | None]:
        return OwnedState(), None


class DoneState(State):
    """It defines no moves, so every move is refused. Only ItemCycle can leave
    it, by rolling over to the next process."""

    def name(self) -> str:
        return DONE

    def advice(self, process: Process) -> str:
        return process.done_advice


class ItemCycle:
    """One item going round the loop of drop and pick."""

    def __init__(self, subject: str, process: Process = DROP) -> None:
        if not subject:
            raise ValueError("subject must not be empty")
        if not isinstance(process, Process):
            raise TypeError(f"process must be a Process, not {type(process).__name__}")
        self._subject = subject
        self._process = process
        self._state: State = OwnedState()

    @property
    def subject(self) -> str:
        return self._subject

    def process_name(self) -> str:
        return self._process.name

    def state(self) -> str:
        return self._state.name()

    def holder(self) -> str:
        return self._process.holder(self._state.name())

    def is_usable(self) -> bool:
        """The Broker holds it, and it is not in flight."""
        return self.holder() == BROKER and self.state() != FLIGHT

    def begin(self, process: Process) -> Refusal | None:
        self._require(process)
        # A finished process hands the item to the next one, at its start.
        if self._state.name() == DONE and process == _NEXT[self._process.name]:
            self._process = process
            self._state = OwnedState()
        if process != self._process:
            return self._mismatch("begin", process)
        self._state, refusal = self._state.begin(process, self._subject)
        return refusal

    def finish(self, process: Process) -> Refusal | None:
        self._require(process)
        if process != self._process:
            return self._mismatch("finish", process)
        self._state, refusal = self._state.finish(process, self._subject)
        return refusal

    def cancel(self, process: Process) -> Refusal | None:
        self._require(process)
        if process != self._process:
            return self._mismatch("cancel", process)
        self._state, refusal = self._state.cancel(process, self._subject)
        return refusal

    @staticmethod
    def _require(process: Process) -> None:
        if not isinstance(process, Process):
            raise TypeError(f"process must be a Process, not {type(process).__name__}")

    def _mismatch(self, move: str, wanted: Process) -> Refusal:
        """The wrong process for where the item is: say where it really is."""
        return self._state.refuse(move, wanted, self._subject, self._process)