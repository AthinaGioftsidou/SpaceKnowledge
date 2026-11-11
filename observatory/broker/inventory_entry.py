"""An item in a player's inventory. Its drop is a Transition."""

from observatory.common.refusal import Refusal
from observatory.common.transition import DROP, Transition


class InventoryEntry:
    """One item a player holds, with the state of its drop. The Broker's own
    record, not the Universe's Item."""

    def __init__(self, item_id: str, name: str) -> None:
        if not item_id:
            raise ValueError("item_id must not be empty")
        if not name:
            raise ValueError("name must not be empty")
        self._item_id = item_id
        self._name = name
        self._drop = Transition(DROP, name)

    @property
    def item_id(self) -> str:
        return self._item_id

    @property
    def name(self) -> str:
        return self._name

    def state_name(self) -> str:
        return self._drop.phase_name()

    def is_usable(self) -> bool:
        """Only an item that is not mid-drop (or finished dropping) is usable."""
        return self._drop.is_at_start()

    def begin_drop(self) -> Refusal | None:
        return self._drop.begin()

    def finish_drop(self) -> Refusal | None:
        return self._drop.confirm()

    def cancel_drop(self) -> Refusal | None:
        return self._drop.cancel()