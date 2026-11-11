"""TRANSITION. The three phases every action goes through.

    start --begin--> in flight --confirm--> done
      ^                  |
      +------ cancel ----+

Drop, mine and add all reuse this one machine and differ only in their words.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from observatory.common.refusal import Refusal


@dataclass(frozen=True)
class TransitionKind:
    """The words one action uses for its three phases. Read-only."""

    verb: str
    start: str
    in_flight: str
    done: str

    def __post_init__(self) -> None:
        for label in (self.verb, self.start, self.in_flight, self.done):
            if not label:
                raise ValueError("every word of a transition kind must be filled in")
        if len({self.start, self.in_flight, self.done}) != 3:
            raise ValueError("the three phases need three different names")


DROP = TransitionKind("drop", "owned", "being_dropped", "dropped")
MINE = TransitionKind("mine", "available", "being_mined", "in_bag")
ADD = TransitionKind("add", "wanted", "being_added", "added")


class Phase(ABC):
    """STATE. One class per phase, so Transition never asks which one it is in.

    Each move returns the next phase and a Refusal or None. The default is to
    refuse and stay, so a phase lists only the moves it ALLOWS.
    """

    def __init__(self, kind: TransitionKind) -> None:
        self._kind = kind

    @abstractmethod
    def name(self) -> str:
        """The word for this phase, taken from the kind."""

    @abstractmethod
    def advice(self) -> str:
        """What to do next when a move is refused here."""

    def begin(self, subject: str) -> tuple["Phase", Refusal | None]:
        return self, self._refuse(self._kind.verb, subject)

    def confirm(self, subject: str) -> tuple["Phase", Refusal | None]:
        return self, self._refuse(f"finish {self._kind.verb}", subject)

    def cancel(self, subject: str) -> tuple["Phase", Refusal | None]:
        return self, self._refuse(f"cancel {self._kind.verb}", subject)

    def _refuse(self, move: str, subject: str) -> Refusal:
        """TEMPLATE METHOD: the refusal is built one way for every phase and
        every action. A phase only supplies its name and its advice."""
        return Refusal(f"{move} {subject}", f"the {subject} is {self.name()}", self.advice())


class StartPhase(Phase):
    def name(self) -> str:
        return self._kind.start

    def advice(self) -> str:
        return "begin the action first"

    def begin(self, subject: str) -> tuple[Phase, Refusal | None]:
        return InFlightPhase(self._kind), None


class InFlightPhase(Phase):
    def name(self) -> str:
        return self._kind.in_flight

    def advice(self) -> str:
        return "wait for the current action to finish, then try again"

    def confirm(self, subject: str) -> tuple[Phase, Refusal | None]:
        return DonePhase(self._kind), None

    def cancel(self, subject: str) -> tuple[Phase, Refusal | None]:
        return StartPhase(self._kind), None


class DonePhase(Phase):
    """Final. It defines no moves, so every move is refused."""

    def name(self) -> str:
        return self._kind.done

    def advice(self) -> str:
        return "this action is finished, so start a new one"


class Transition:
    """One action on one subject, moving through the three phases."""

    def __init__(self, kind: TransitionKind, subject: str) -> None:
        if not isinstance(kind, TransitionKind):
            raise TypeError(f"kind must be a TransitionKind, not {type(kind).__name__}")
        if not subject:
            raise ValueError("subject must not be empty")
        self._kind = kind
        self._subject = subject
        self._phase: Phase = StartPhase(kind)

    @property
    def kind(self) -> TransitionKind:
        return self._kind

    @property
    def subject(self) -> str:
        return self._subject

    def phase_name(self) -> str:
        return self._phase.name()

    def is_at_start(self) -> bool:
        return isinstance(self._phase, StartPhase)

    def is_in_flight(self) -> bool:
        return isinstance(self._phase, InFlightPhase)

    def is_done(self) -> bool:
        return isinstance(self._phase, DonePhase)

    # The only place _phase is assigned: the phase decides, Transition applies.
    def begin(self) -> Refusal | None:
        self._phase, refusal = self._phase.begin(self._subject)
        return refusal

    def confirm(self) -> Refusal | None:
        self._phase, refusal = self._phase.confirm(self._subject)
        return refusal

    def cancel(self) -> Refusal | None:
        self._phase, refusal = self._phase.cancel(self._subject)
        return refusal