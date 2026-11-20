"""PROXY. The Broker's stand-in for an item that lives in the Universe."""

from collections.abc import Callable

from spaceknowledge.common.item_cycle import PICK, ItemCycle
from spaceknowledge.common.messages import ItemInfo
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.world.item import Item

# What a proxy calls when it is asked to pick itself up: (proxy, player) -> why not.
Picker = Callable[["ItemProxy", str], Refusal | None]


class ItemProxy(Item):
    """Looks like an item and holds none. It copies only the item's description.
    The real item exists only in the Universe.

    While the item lies on the ground, the proxy is `owned` and held by the
    Universe. A pick moves it to `flight`, and when the Universe says yes it
    reaches `done`, held by the Broker. The Broker then deletes the proxy and
    creates a real inventory entry.
    """

    def __init__(self, info: ItemInfo, picker: Picker) -> None:
        if not isinstance(info, ItemInfo):
            raise TypeError(f"info must be an ItemInfo, not {type(info).__name__}")
        if not callable(picker):
            raise TypeError("picker must be callable")
        super().__init__(info.item_id, info.name)
        self._description = info.description
        self._picker = picker
        self._cycle = ItemCycle(info.name, PICK)

    def describe(self) -> str:
        return self._description

    def state(self) -> str:
        return self._cycle.state()

    def holder(self) -> str:
        return self._cycle.holder()

    def pick(self, player_id: str) -> Refusal | None:
        """Ask the Universe, through the UniverseProxy, to let `player_id`
        have the real item. None if it worked, otherwise why not."""
        return self._picker(self, player_id)

    def begin_pick(self) -> Refusal | None:
        return self._cycle.begin(PICK)

    def finish_pick(self) -> Refusal | None:
        return self._cycle.finish(PICK)

    def cancel_pick(self) -> Refusal | None:
        return self._cycle.cancel(PICK)