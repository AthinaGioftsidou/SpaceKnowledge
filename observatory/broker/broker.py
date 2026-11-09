"""The Broker: owns players and inventories, and asks the Universe for changes."""

from itertools import count

from observatory.broker.inventory_entry import InventoryEntry
from observatory.broker.player_inventory import PlayerInventory
from observatory.common.messages import Request
from observatory.common.refusal import Refusal
from observatory.transport.channel import UniverseChannel


class Broker:
    """Holds each player's inventory. Never touches the world directly:
    every change to the world goes through the channel as a Request."""

    def __init__(self, channel: UniverseChannel) -> None:
        if not isinstance(channel, UniverseChannel):
            raise TypeError(f"channel must be a UniverseChannel, not {type(channel).__name__}")
        self._channel = channel
        self._inventories: dict[str, PlayerInventory] = {}
        self._op_numbers = count(1)

    def add_player(self, player_id: str) -> None:
        if not player_id:
            raise ValueError("player_id must not be empty")
        if player_id in self._inventories:
            raise ValueError(f"player {player_id} already exists")
        self._inventories[player_id] = PlayerInventory()

    def inventory_of(self, player_id: str) -> PlayerInventory:
        """Raises KeyError for an unknown player."""
        return self._inventories[player_id]

    def give(self, player_id: str, entry: InventoryEntry) -> None:
        if not isinstance(entry, InventoryEntry):
            raise TypeError(f"entry must be an InventoryEntry, not {type(entry).__name__}")
        self.inventory_of(player_id).add(entry)

    def drop(self, player_id: str, item_id: str) -> Refusal | None:
        """None if the item is now in the world, otherwise why not."""
        inventory = self._inventories.get(player_id)
        if inventory is None:
            return Refusal(
                f"drop {item_id}",
                f"the Broker does not know a player called {player_id}",
                "log in, then try again",
            )
        refusal = inventory.begin_drop(item_id)
        if refusal is not None:
            return refusal
        request = Request(self._next_op_id(), "add_item", player_id, item_id)
        response = self._channel.send(request)
        if response.ok:
            inventory.finish_drop(item_id)
            return None
        inventory.cancel_drop(item_id)
        return response.refusal

    def _next_op_id(self) -> str:
        return f"op{next(self._op_numbers)}"