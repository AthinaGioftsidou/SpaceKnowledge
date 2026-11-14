"""The Broker: owns players, inventories and resources, and asks the Universe
for every change to the world."""

from itertools import count
from uuid import uuid4

from observatory.broker.inventory_entry import InventoryEntry
from observatory.broker.inventory_repository import (
    CorruptStoreError,
    InMemoryInventoryRepository,
    InventoryRepository,
)
from observatory.broker.player_inventory import PlayerInventory
from observatory.broker.resource_bag import ResourceBag
from observatory.common.messages import Request, Response
from observatory.common.refusal import Refusal
from observatory.transport.channel import UniverseChannel

ACTIONS = ("add_item", "mine", "join")

# What a brand new player is given, so that `drop` has something to drop.
STARTING_ITEMS = (("torch", "torch"),)


class Broker:
    """Holds each player's inventory and resource bag. Never touches the world
    directly: every change to the world goes through the channel as a Request.

    A drop moves the item round its cycle: Owned, BeingDropped, and OnGround
    once the Universe says yes. A mine has no phases: the Universe is asked,
    and the bag grows only if it says yes.

    Every request is written down as "pending" BEFORE it is sent, and crossed
    off only when its answer has been applied. After a crash, `recover` sends
    the unfinished ones again with their original op_id, and the Universe's
    remembered answers make that safe.
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
        self._pending: dict[str, Request] = {}
        self._run_id = uuid4().hex[:8]
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

    def has_player(self, player_id: str) -> bool:
        return player_id in self._inventories

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
        return self._send(Request(self._next_op_id(), "add_item", player_id, item_id))

    def mine(self, player_id: str, resource: str, amount: int) -> Refusal | None:
        """None if the resource is now in the player's bag, otherwise why not.

        The bag grows only after the Universe has confirmed the mining.
        """
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise TypeError(f"amount must be an int, not {type(amount).__name__}")
        if player_id not in self._resources:
            return self._unknown_player(f"mine {resource}", player_id)
        if amount < 1:
            return Refusal(
                f"mine {resource}", "the amount must be at least 1", "ask for 1 or more"
            )
        return self._send(Request(self._next_op_id(), "mine", player_id, resource, amount))

    def join(self, player_id: str, destination: str) -> Refusal | None:
        """Make sure the player exists here and has a place in the Universe.

        A new player gets a record and the starting items. Joining again
        changes nothing, because the Universe leaves a placed player where
        they are. None if all is well, otherwise why not.
        """
        if not player_id:
            raise ValueError("player_id must not be empty")
        if not destination:
            raise ValueError("destination must not be empty")
        if player_id not in self._inventories:
            self.add_player(player_id)
            for item_id, name in STARTING_ITEMS:
                self.give(player_id, InventoryEntry(item_id, name))
        return self._send(Request(self._next_op_id(), "join", player_id, destination))

    def pending_count(self) -> int:
        """How many operations were sent and have not been settled yet."""
        return len(self._pending)

    def recover(self) -> int:
        """Send every unfinished operation again, with its original op_id.

        Call this once after starting. Returns how many were settled. If the
        channel fails, the rest stay pending and `recover` can be called again.
        """
        settled = 0
        for request in list(self._pending.values()):
            self._settle(request, self._channel.send(request))
            settled += 1
        return settled

    def _send(self, request: Request) -> Refusal | None:
        """Write the intention down, ask the Universe, then settle."""
        self._pending[request.op_id] = request
        try:
            self._save()
        except OSError:
            # Not on disk, so it must not be sent: take the intention back.
            del self._pending[request.op_id]
            if request.action == "add_item":
                self._inventories[request.player_id].cancel_drop(request.item_id)
            raise
        response = self._channel.send(request)
        return self._settle(request, response)

    def _settle(self, request: Request, response: Response) -> Refusal | None:
        """Apply the answer, cross the intention off, and save both together."""
        if request.action == "add_item":
            inventory = self._inventories[request.player_id]
            if response.ok:
                inventory.finish_drop(request.item_id)
            else:
                inventory.cancel_drop(request.item_id)
        elif request.action == "mine" and response.ok:
            self._resources[request.player_id].add(request.item_id, request.amount)
        del self._pending[request.op_id]
        self._save()
        return response.refusal

    def _unknown_player(self, what: str, player_id: str) -> Refusal:
        return Refusal(
            what,
            f"the Broker does not know a player called {player_id}",
            "log in, then try again",
        )

    def _next_op_id(self) -> str:
        """Unique across runs: the Universe remembers answers by op_id, so a
        restarted Broker counting from 1 again would be told old answers."""
        return f"{self._run_id}-op{next(self._op_numbers)}"

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
        for request in self._repository.load_pending():
            self._restore_pending(request)

    def _restore_pending(self, request: Request) -> None:
        if request.action not in ACTIONS:
            raise CorruptStoreError(
                f"pending operation {request.op_id} has an unknown action {request.action}"
            )
        if request.action == "add_item":
            # The saved item is still in the inventory, so move it back to
            # BeingDropped: it must stay locked until the drop is settled.
            refusal = self._inventories[request.player_id].begin_drop(request.item_id)
            if refusal is not None:
                raise CorruptStoreError(
                    f"pending drop {request.op_id} names {request.item_id}, "
                    f"which {request.player_id} cannot be dropping"
                )
        self._pending[request.op_id] = request

    def _save(self) -> None:
        items: dict[str, list[tuple[str, str]]] = {}
        for player_id, inventory in self._inventories.items():
            items[player_id] = [(entry.item_id, entry.name) for entry in inventory.entries()]
        bags = {player_id: bag.snapshot() for player_id, bag in self._resources.items()}
        self._repository.save(items, bags, list(self._pending.values()))