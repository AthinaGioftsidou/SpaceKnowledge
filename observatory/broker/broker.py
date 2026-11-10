"""The Broker: owns players, inventories and resources, and asks the Universe
for every change to the world."""

from itertools import count

from observatory.broker.inventory_entry import InventoryEntry
from observatory.broker.inventory_repository import (
    InMemoryInventoryRepository,
    InventoryRepository,
)
from observatory.broker.player_inventory import PlayerInventory
from observatory.broker.resource_bag import ResourceBag
from observatory.common.messages import Request
from observatory.common.refusal import Refusal
from observatory.transport.channel import UniverseChannel


class Broker:
    """Holds each player's inventory and resource bag. Never touches the world
    directly: every change to the world goes through the channel as a Request.

    Loads its players from the repository when it starts, and saves after
    every change that is final.
    """

    def __init__(
        self, channel: UniverseChannel, repository: InventoryRepository | None = None
    ) -> None:
        if not isinstance(channel, UniverseChannel):
            raise TypeError(f"channel must be a UniverseChannel, not {type(channel).__name__}")
        if repository is not None and not isinstance(repository, InventoryRepository):
            raise TypeError(
                f"repository must be an InventoryRepository, not {type(repository).__name__}"
            )
        self._channel = channel
        self._repository = repository if repository is not None else InMemoryInventoryRepository()
        self._inventories: dict[str, PlayerInventory] = {}
        self._resources: dict[str, ResourceBag] = {}
        self._op_numbers = count(1)
        self._restore()

    def add_player(self, player_id: str) -> None:
        if not player_id:
            raise ValueError("player_id must not be empty")
        if player_id in self._inventories:
            raise ValueError(f"player {player_id} already exists")
        self._inventories[player_id] = PlayerInventory()
        self._resources[player_id] = ResourceBag()
        self._save()

    def inventory_of(self, player_id: str) -> PlayerInventory:
        """Raises KeyError for an unknown player."""
        return self._inventories[player_id]

    def resources_of(self, player_id: str) -> ResourceBag:
        """Raises KeyError for an unknown player."""
        return self._resources[player_id]

    def give(self, player_id: str, entry: InventoryEntry) -> None:
        if not isinstance(entry, InventoryEntry):
            raise TypeError(f"entry must be an InventoryEntry, not {type(entry).__name__}")
        self.inventory_of(player_id).add(entry)
        self._save()

    def drop(self, player_id: str, item_id: str) -> Refusal | None:
        """None if the item is now in the world, otherwise why not."""
        inventory = self._inventories.get(player_id)
        if inventory is None:
            return self._unknown_player(f"drop {item_id}", player_id)
        refusal = inventory.begin_drop(item_id)
        if refusal is not None:
            return refusal
        request = Request(self._next_op_id(), "add_item", player_id, item_id)
        response = self._channel.send(request)
        if response.ok:
            inventory.finish_drop(item_id)
            self._save()
            return None
        inventory.cancel_drop(item_id)
        return response.refusal

    def mine(self, player_id: str, resource: str, amount: int) -> Refusal | None:
        """None if the resource is now in the player's bag, otherwise why not.

        The bag grows only after the Universe has confirmed the mining.
        """
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise TypeError(f"amount must be an int, not {type(amount).__name__}")
        bag = self._resources.get(player_id)
        if bag is None:
            return self._unknown_player(f"mine {resource}", player_id)
        if amount < 1:
            return Refusal(
                f"mine {resource}", "the amount must be at least 1", "ask for 1 or more"
            )
        request = Request(self._next_op_id(), "mine", player_id, resource, amount)
        response = self._channel.send(request)
        if not response.ok:
            return response.refusal
        bag.add(resource, amount)
        self._save()
        return None

    def _unknown_player(self, what: str, player_id: str) -> Refusal:
        return Refusal(
            what,
            f"the Broker does not know a player called {player_id}",
            "log in, then try again",
        )

    def _next_op_id(self) -> str:
        return f"op{next(self._op_numbers)}"

    def _restore(self) -> None:
        resources = self._repository.load_resources()
        for player_id, records in self._repository.load().items():
            inventory = PlayerInventory()
            for item_id, name in records:
                inventory.add(InventoryEntry(item_id, name))
            bag = ResourceBag()
            for resource, amount in resources.get(player_id, {}).items():
                bag.add(resource, amount)
            self._inventories[player_id] = inventory
            self._resources[player_id] = bag

    def _save(self) -> None:
        items: dict[str, list[tuple[str, str]]] = {}
        for player_id, inventory in self._inventories.items():
            items[player_id] = [(entry.item_id, entry.name) for entry in inventory.entries()]
        bags = {player_id: bag.snapshot() for player_id, bag in self._resources.items()}
        self._repository.save(items, bags)