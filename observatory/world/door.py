"""STATE. A door, and the three it can be in.

The first thing here that can legitimately REFUSE you. Until now a verb worked
or found nothing, which is absence, not refusal. Every check in the second half
of the module is a more serious version of this one.

The obvious version is a boolean. Handout section 2 writes it and watches it rot
when the second requirement arrives.
"""

from abc import ABC, abstractmethod


# ##01 State: the abstract state; each transition returns the next state and the reply
class DoorState(ABC):
    """One class per state, so `Door` never asks which state it is in.

    Transitions RETURN the next state and the message. Returning `self` is a
    refusal and is the default, so a state writes down only what it ALLOWS.
    """

    @abstractmethod
    def name(self) -> str:
        """One word, used in messages and in tests."""

    @abstractmethod
    def is_passable(self) -> bool:
        """Whether a player may walk through right now."""

    def refusal(self, door: Door) -> str:
        """What the player is told when this state says no."""
        if not isinstance(door, Door):
            raise TypeError(f"door must be a Door, not {type(door).__name__}")
        return f"The {door.name} is {self.name()}."

    # Default is refuse and stay: a subclass silent about a move has said no,
    # which is the safe direction to fail.
    def unlock(self, door: Door, key_id: str) -> tuple[DoorState, str]:
        if not isinstance(door, Door):
            raise TypeError(f"door must be a Door, not {type(door).__name__}")
        return self, self.refusal(door)

    def lock(self, door: Door, key_id: str) -> tuple[DoorState, str]:
        if not isinstance(door, Door):
            raise TypeError(f"door must be a Door, not {type(door).__name__}")
        return self, self.refusal(door)

    def force(self, door: Door) -> tuple[DoorState, str]:
        if not isinstance(door, Door):
            raise TypeError(f"door must be a Door, not {type(door).__name__}")
        return self, self.refusal(door)


# ##02 State: concrete states override only the transitions they allow
class LockedState(DoorState):
    def name(self) -> str:
        return "locked"

    def is_passable(self) -> bool:
        return False

    def unlock(self, door: Door, key_id: str) -> tuple[DoorState, str]:
        if not isinstance(door, Door):
            raise TypeError(f"door must be a Door, not {type(door).__name__}")
        # --- INSTRUCTOR SWAP 06 : week 04 : defect in the CODE ----------------
        #   fits = True                                                # BROKEN
        fits = key_id == door.key_id
        # --- END INSTRUCTOR SWAP 06 -------------------------------------------
        if not fits:
            return self, "That key does not fit."
        return UnlockedState(), f"The {door.name} unlocks."

    def force(self, door: Door) -> tuple[DoorState, str]:
        """The one transition you cannot take back. See BrokenState."""
        if not isinstance(door, Door):
            raise TypeError(f"door must be a Door, not {type(door).__name__}")
        return BrokenState(), f"The {door.name} splinters. The mechanism is ruined."


class UnlockedState(DoorState):
    def name(self) -> str:
        return "unlocked"

    def is_passable(self) -> bool:
        return True

    def lock(self, door: Door, key_id: str) -> tuple[DoorState, str]:
        if not isinstance(door, Door):
            raise TypeError(f"door must be a Door, not {type(door).__name__}")
        if key_id != door.key_id:
            return self, "That key does not fit."
        return LockedState(), f"The {door.name} locks."


# ##02 State: a terminal state, with no transition out
class BrokenState(DoorState):
    """Terminal, and defines no transitions at all.

    Two booleans can say "broken". They cannot say broken is FINAL, because a
    boolean that was set can be cleared. Here the guarantee is the absence of
    methods: you cannot forget a check you never had to write.
    """

    def name(self) -> str:
        return "broken"

    def is_passable(self) -> bool:
        return False

    def refusal(self, door: Door) -> str:
        if not isinstance(door, Door):
            raise TypeError(f"door must be a Door, not {type(door).__name__}")
        return f"The {door.name} is ruined. Nothing will move it now."


class Door:
    """A barrier on an exit. Two rooms share one Door, so unlocking is not sided.

    Owns its key id, which is its own property. Knows nothing about crowbars,
    which are not. Who holds what is the caller's job; what that permits is this
    class's.
    """

    def __init__(
        self, door_id: str, name: str, key_id: str, state: DoorState | None = None
    ) -> None:
        if state is not None and not isinstance(state, DoorState):
            raise TypeError(f"state must be a DoorState, not {type(state).__name__}")
        if not door_id:
            raise ValueError("door_id must not be empty")
        if not name:
            raise ValueError("name must not be empty")
        if not key_id:
            raise ValueError("key_id must not be empty")
        self._door_id = door_id
        self._name = name
        self._key_id = key_id
        # A fresh instance per door. States hold no data so sharing would work
        # and save nothing worth the coupling. Week 7 revisits the temptation.
        self._state: DoorState = state or LockedState()

    @property
    def door_id(self) -> str:
        return self._door_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def key_id(self) -> str:
        return self._key_id

    def state_name(self) -> str:
        return self._state.name()


    def is_passable(self) -> bool:
        return self._state.is_passable()

    def refusal(self) -> str:
        """Why you may not pass. Asked by GoCommand, not by the player."""
        return self._state.refusal(self)

    # ##02 State: Door delegates; the only assignment to _state
    # Each the same two lines: the state makes the ruling, Door applies it.
    def unlock(self, key_id: str) -> str:
        self._state, message = self._state.unlock(self, key_id)
        return message

    def lock(self, key_id: str) -> str:
        self._state, message = self._state.lock(self, key_id)
        return message

    def force(self) -> str:
        self._state, message = self._state.force(self)
        return message
