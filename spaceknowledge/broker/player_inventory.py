"""One player's inventory, as the Broker sees it."""

from spaceknowledge.broker.inventory_entry import InventoryEntry
from spaceknowledge.common.refusal import Refusal


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
        """Exact id only. Ids are unique."""
        for entry in self._entries:
            if entry.item_id == item_id:
                return entry
        return None

    def resolve(self, term: str) -> InventoryEntry | None:
        """What a player typed, resolved: an exact id first, then a display name
        (any case). Several items may share a name, so among those the first
        usable one wins, then the first by id. Type an id to pick one exactly."""
        exact = self.find(term)
        if exact is not None:
            return exact
        wanted = term.strip().lower()
        named = sorted(
            (entry for entry in self._entries if entry.name.lower() == wanted),
            key=lambda entry: entry.item_id,
        )
        for entry in named:
            if entry.is_usable():
                return entry
        return named[0] if named else None

    def count(self) -> int:
        return len(self._entries)

    def entries(self) -> list[InventoryEntry]:
        """A copy, so callers cannot change the real list."""
        return list(self._entries)

    def check_usable(self, item_id: str) -> Refusal | None:
        """None if the player may use the item now, otherwise why not."""
        entry = self.find(item_id)
        if entry is None:
            return self.not_carried("use", item_id)
        if not entry.is_usable():
            return Refusal(
                f"use {entry.name}",
                f"the {entry.name} cannot be used in state {entry.state()}",
                "wait for the current action to finish, then try again",
            )
        return None

    def begin_drop(self, item_id: str) -> Refusal | None:
        entry = self.find(item_id)
        if entry is None:
            return self.not_carried("drop", item_id)
        return entry.begin_drop()

    def finish_drop(self, item_id: str) -> Refusal | None:
        """The Universe said OK: the item leaves the inventory for good."""
        entry = self.find(item_id)
        if entry is None:
            return self.not_carried("finish dropping", item_id)
        refusal = entry.finish_drop()
        if refusal is None:
            self._entries.remove(entry)
        return refusal

    def cancel_drop(self, item_id: str) -> Refusal | None:
        """The Universe said no: the item becomes usable again."""
        entry = self.find(item_id)
        if entry is None:
            return self.not_carried("cancel the drop of", item_id)
        return entry.cancel_drop()

    def not_carried(self, verb: str, term: str) -> Refusal:
        return Refusal(
            f"{verb} {term}",
            f"you are not carrying {term}",
            "type inventory to see what you carry",
        )