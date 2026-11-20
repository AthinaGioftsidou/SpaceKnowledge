"""A door and the three states it can be in: locked, unlocked or broken.

A door is the first thing that can refuse a player. Because there are three
states and the rules differ in each, every state is its own class (the State
pattern) and the door never asks which one it is in. In the full game a door
is how a destination stays closed until a mission is complete.
"""

from abc import ABC, abstractmethod


class DoorState(ABC):
    """One class per state. A transition RETURNS the next state and the message.

    The default is to refuse and stay where we are, so a state lists only the
    moves it allows. A state that says nothing about a move has said no, which
    is the safe way to fail.
    """

    @abstractmethod
    def name(self) -> str:
        """One word, used in messages and tests."""

    @abstractmethod
    def is_passable(self) -> bool:
        """Whether a player may walk through right now."""

    def refusal(self, door: Door) -> str:
        if not isinstance(door, Door):
            raise TypeError(f"door must be a Door, not {type(door).__name__}")
        return f"The {door.name} is {self.name()}."

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


class LockedState(DoorState):
    def name(self) -> str:
        return "locked"

    def is_passable(self) -> bool:
        return False

    def unlock(self, door: Door, key_id: str) -> tuple[DoorState, str]:
        if not isinstance(door, Door):
            raise TypeError(f"door must be a Door, not {type(door).__name__}")
        if key_id != door.key_id:
            return self, "That key does not fit."
        return UnlockedState(), f"The {door.name} unlocks."

    def force(self, door: Door) -> tuple[DoorState, str]:
        """The one move that cannot be undone: see BrokenState."""
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


class BrokenState(DoorState):
    """Final: it defines no moves at all.

    Two booleans could say "broken" but could not say it is permanent, because
    a flag that was set can be cleared. Here the guarantee is that no method
    exists to leave this state.
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
    """A barrier on an exit. Two destinations share one Door object, so
    unlocking from one side unlocks it from the other.

    It owns its key id. It knows nothing about tools such as a crowbar: what a
    player holds is the caller's business, what that permits is the door's.
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
        """Why the player may not pass."""
        return self._state.refusal(self)

    # Each move is the same two lines: the state decides, the door applies it.
    def unlock(self, key_id: str) -> str:
        self._state, message = self._state.unlock(self, key_id)
        return message

    def lock(self, key_id: str) -> str:
        self._state, message = self._state.lock(self, key_id)
        return message

    def force(self) -> str:
        self._state, message = self._state.force(self)
        return message