"""One player's inventory, as the Broker sees it."""

from observatory.broker.inventory_entry import InventoryEntry
from observatory.common.refusal import Refusal


class PlayerInventory:
    """The entries one player holds, each with its own state.

    Owned only by the Broker. Every move that can be refused returns a
    Refusal, and None means it worked.
    """

    def __init__(self) -> None:
        self._entries: list[InventoryEntry] = []

    def add(self, entry: InventoryEntry) -> None:
        if not isinstance(entry, InventoryEntry):
            raise TypeError(f"entry must be an InventoryEntry, not {type(entry).__name__}")
        if self.find(entry.item_id) is not None:
            raise ValueError(f"already holds an item with id {entry.item_id}")
        self._entries.append(entry)

    def find(self, item_id: str) -> InventoryEntry | None:
        for entry in self._entries:
            if entry.item_id == item_id:
                return entry
        return None

    def count(self) -> int:
        return len(self._entries)

    def entries(self) -> list[InventoryEntry]:
        """A copy, so callers cannot change the real list."""
        return self._entries.copy()

    def check_usable(self, item_id: str) -> Refusal | None:
        """None if the player may use the item now, otherwise why not."""
        entry = self.find(item_id)
        if entry is None:
            return self._not_carried("use", item_id)
        if not entry.is_usable():
            return Refusal(
                f"use {entry.name}",
                f"the {entry.name} is {entry.phase_name()}",
                "wait for the current action to finish, then try again",
            )
        return None

    def begin_drop(self, item_id: str) -> Refusal | None:
        entry = self.find(item_id)
        if entry is None:
            return self._not_carried("drop", item_id)
        return entry.begin_drop()

    def finish_drop(self, item_id: str) -> Refusal | None:
        """The Universe said OK: the item leaves the inventory for good."""
        entry = self.find(item_id)
        if entry is None:
            return self._not_carried("finish dropping", item_id)
        refusal = entry.finish_drop()
        if refusal is None:
            self._entries.remove(entry)
        return refusal

    def cancel_drop(self, item_id: str) -> Refusal | None:
        """The Universe said no: the item becomes usable again."""
        entry = self.find(item_id)
        if entry is None:
            return self._not_carried("cancel the drop of", item_id)
        return entry.cancel_drop()

    def _not_carried(self, verb: str, item_id: str) -> Refusal:
        return Refusal(
            f"{verb} {item_id}",
            f"you are not carrying {item_id}",
            "type inventory to see what you carry",
        )