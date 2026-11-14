"""THE ITEM CYCLE. Four phases, three states.

     Broker                            Universe
  Owned --drop--> BeingDropped --ok--> OnGround --pick--> BeingPicked --ok--> Owned
    ^                 |                   ^                   |                |
    |                 +--- no: Owned      |                   +-- no: OnGround |
    +---------------------------------------------------------------------------+

A PHASE is a step of the cycle. A STATE says what that phase means for the item:
    owned   at rest with the Broker, usable
    flight  between the servers, waiting for an answer, locked
    done    at rest with the Universe, the drop has finished

Only drop and pick use this. Mining is a plain request with no phases.
"""

from abc import ABC, abstractmethod

from observatory.common.refusal import Refusal

BROKER = "broker"
UNIVERSE = "universe"

"""STATE"""
OWNED = "owned"
FLIGHT = "flight"
DONE = "done"


class Phase(ABC):
    """One class per phase, so ItemCycle never asks which one it is in.

    Each move returns the next phase and a Refusal or None. The default is to
    refuse and stay, so a phase lists only the moves it ALLOWS.
    """

    @abstractmethod
    def name(self) -> str:
        """One word, used in messages, in tests and in the log."""

    @abstractmethod
    def owner(self) -> str:
        """BROKER or UNIVERSE: which side holds the item in this phase."""

    @abstractmethod
    def state(self) -> str:
        """OWNED, FLIGHT or DONE."""

    @abstractmethod
    def advice(self) -> str:
        """What the player can do next when a move is refused here."""

    def is_usable(self) -> bool:
        """Only an item in the owned state may be used."""
        return self.state() == OWNED

    def begin_drop(self, subject: str) -> tuple[Phase, Refusal | None]:
        return self, self._refuse("drop", subject)

    def finish_drop(self, subject: str) -> tuple[Phase, Refusal | None]:
        return self, self._refuse("finish dropping", subject)

    def cancel_drop(self, subject: str) -> tuple[Phase, Refusal | None]:
        return self, self._refuse("cancel the drop of", subject)

    def begin_pick(self, subject: str) -> tuple[Phase, Refusal | None]:
        return self, self._refuse("pick up", subject)

    def finish_pick(self, subject: str) -> tuple[Phase, Refusal | None]:
        return self, self._refuse("finish picking up", subject)

    def cancel_pick(self, subject: str) -> tuple[Phase, Refusal | None]:
        return self, self._refuse("cancel the pick up of", subject)

    def _refuse(self, move: str, subject: str) -> Refusal:
        """TEMPLATE METHOD: every refusal is built one way. A phase supplies
        only its name and its advice."""
        return Refusal(f"{move} {subject}", f"the {subject} is {self.name()}", self.advice())


class OwnedPhase(Phase):
    def name(self) -> str:
        return "owned"

    def owner(self) -> str:
        return BROKER

    def state(self) -> str:
        return OWNED

    def advice(self) -> str:
        return "the item is yours, so you can drop it"

    def begin_drop(self, subject: str) -> tuple[Phase, Refusal | None]:
        return BeingDroppedPhase(), None


class BeingDroppedPhase(Phase):
    def name(self) -> str:
        return "being_dropped"

    def owner(self) -> str:
        return BROKER

    def state(self) -> str:
        return FLIGHT

    def advice(self) -> str:
        return "wait for the Universe to answer, then try again"

    def finish_drop(self, subject: str) -> tuple[Phase, Refusal | None]:
        return OnGroundPhase(), None

    def cancel_drop(self, subject: str) -> tuple[Phase, Refusal | None]:
        return OwnedPhase(), None


class OnGroundPhase(Phase):
    def name(self) -> str:
        return "on_ground"

    def owner(self) -> str:
        return UNIVERSE

    def state(self) -> str:
        return DONE

    def advice(self) -> str:
        return "the item is lying on the ground, so pick it up to own it"

    def begin_pick(self, subject: str) -> tuple[Phase, Refusal | None]:
        return BeingPickedPhase(), None


class BeingPickedPhase(Phase):
    def name(self) -> str:
        return "being_picked"

    def owner(self) -> str:
        return UNIVERSE

    def state(self) -> str:
        return FLIGHT

    def advice(self) -> str:
        return "wait for the Universe to answer, then try again"

    def finish_pick(self, subject: str) -> tuple[Phase, Refusal | None]:
        return OwnedPhase(), None

    def cancel_pick(self, subject: str) -> tuple[Phase, Refusal | None]:
        return OnGroundPhase(), None


class ItemCycle:
    """One item going round the loop."""

    def __init__(self, subject: str, phase: Phase | None = None) -> None:
        if not subject:
            raise ValueError("subject must not be empty")
        if phase is not None and not isinstance(phase, Phase):
            raise TypeError(f"phase must be a Phase, not {type(phase).__name__}")
        self._subject = subject
        self._phase: Phase = phase if phase is not None else OwnedPhase()

    @property
    def subject(self) -> str:
        return self._subject

    def phase_name(self) -> str:
        return self._phase.name()

    def state(self) -> str:
        return self._phase.state()

    def owner(self) -> str:
        return self._phase.owner()

    def is_usable(self) -> bool:
        return self._phase.is_usable()

    # The only place _phase is assigned: the phase decides, ItemCycle applies.
    def begin_drop(self) -> Refusal | None:
        self._phase, refusal = self._phase.begin_drop(self._subject)
        return refusal

    def finish_drop(self) -> Refusal | None:
        self._phase, refusal = self._phase.finish_drop(self._subject)
        return refusal

    def cancel_drop(self) -> Refusal | None:
        self._phase, refusal = self._phase.cancel_drop(self._subject)
        return refusal

    def begin_pick(self) -> Refusal | None:
        self._phase, refusal = self._phase.begin_pick(self._subject)
        return refusal

    def finish_pick(self) -> Refusal | None:
        self._phase, refusal = self._phase.finish_pick(self._subject)
        return refusal

    def cancel_pick(self) -> Refusal | None:
        self._phase, refusal = self._phase.cancel_pick(self._subject)
        return refusal