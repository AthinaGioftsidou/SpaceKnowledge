"""An item in a player's inventory. Its drop goes through the item cycle."""

from spaceknowledge.common.item_cycle import DROP, ItemCycle
from spaceknowledge.common.refusal import Refusal


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
        self._cycle = ItemCycle(name)

    @property
    def item_id(self) -> str:
        return self._item_id

    @property
    def name(self) -> str:
        return self._name

    def process_name(self) -> str:
        return self._cycle.process_name()

    def state(self) -> str:
        return self._cycle.state()

    def holder(self) -> str:
        return self._cycle.holder()

    def is_usable(self) -> bool:
        return self._cycle.is_usable()

    def begin_drop(self) -> Refusal | None:
        return self._cycle.begin(DROP)

    def finish_drop(self) -> Refusal | None:
        return self._cycle.finish(DROP)

    def cancel_drop(self) -> Refusal | None:
        return self._cycle.cancel(DROP)