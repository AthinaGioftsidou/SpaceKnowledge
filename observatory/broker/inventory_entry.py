"""STATE. An item in a player's inventory, and the three states it can be in."""

from abc import ABC, abstractmethod

from observatory.common.refusal import Refusal


class ItemState(ABC):
    """One class per state, so InventoryEntry never asks which state it is in.

    Each move returns the next state and a Refusal or None. The default is to
    refuse and stay, so a state lists only the moves it ALLOWS.
    """

    @abstractmethod
    def name(self) -> str:
        """One word, used in messages and in tests."""

    @abstractmethod
    def is_usable(self) -> bool:
        """Whether the player may use the item right now."""

    def begin_drop(self, entry: InventoryEntry) -> tuple[ItemState, Refusal | None]:
        return self, self._refuse("drop", entry)

    def finish_drop(self, entry: InventoryEntry) -> tuple[ItemState, Refusal | None]:
        return self, self._refuse("finish dropping", entry)

    def cancel_drop(self, entry: InventoryEntry) -> tuple[ItemState, Refusal | None]:
        return self, self._refuse("cancel the drop of", entry)

    def _refuse(self, verb: str, entry: InventoryEntry) -> Refusal:
        return Refusal(
            f"{verb} {entry.name}",
            f"the {entry.name} is {self.name()}",
            "wait for the current action to finish, then try again",
        )


class OwnedState(ItemState):
    def name(self) -> str:
        return "owned"

    def is_usable(self) -> bool:
        return True

    def begin_drop(self, entry: InventoryEntry) -> tuple[ItemState, Refusal | None]:
        return BeingDroppedState(), None


class BeingDroppedState(ItemState):
    def name(self) -> str:
        return "being_dropped"

    def is_usable(self) -> bool:
        return False

    def finish_drop(self, entry: InventoryEntry) -> tuple[ItemState, Refusal | None]:
        return DroppedState(), None

    def cancel_drop(self, entry: InventoryEntry) -> tuple[ItemState, Refusal | None]:
        return OwnedState(), None


class DroppedState(ItemState):
    """Final. It defines no moves, so every move is refused."""

    def name(self) -> str:
        return "dropped"

    def is_usable(self) -> bool:
        return False


class InventoryEntry:
    """One item a player holds, with its state. The Broker's own record,
    not the Universe's Item."""

    def __init__(self, item_id: str, name: str) -> None:
        if not item_id:
            raise ValueError("item_id must not be empty")
        if not name:
            raise ValueError("name must not be empty")
        self._item_id = item_id
        self._name = name
        self._state: ItemState = OwnedState()

    @property
    def item_id(self) -> str:
        return self._item_id

    @property
    def name(self) -> str:
        return self._name

    def state_name(self) -> str:
        return self._state.name()

    def is_usable(self) -> bool:
        return self._state.is_usable()

    # The only place _state is assigned: the state decides, the entry applies.
    def begin_drop(self) -> Refusal | None:
        self._state, refusal = self._state.begin_drop(self)
        return refusal

    def finish_drop(self) -> Refusal | None:
        self._state, refusal = self._state.finish_drop(self)
        return refusal

    def cancel_drop(self) -> Refusal | None:
        self._state, refusal = self._state.cancel_drop(self)
        return refusal