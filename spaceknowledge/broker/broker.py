"""The Broker: owns players, inventories and resources, and asks the Universe
for every change to the world."""

from itertools import count
from uuid import uuid4

from spaceknowledge.broker.inventory_entry import InventoryEntry
from spaceknowledge.broker.inventory_repository import (
    CorruptStoreError,
    InMemoryInventoryRepository,
    InventoryRepository,
)
from spaceknowledge.broker.item_proxy import ItemProxy
from spaceknowledge.broker.player_inventory import PlayerInventory
from spaceknowledge.broker.resource_bag import ResourceBag
from spaceknowledge.broker.universe_proxy import UniverseProxy
from spaceknowledge.common.messages import ItemInfo, Request, Response
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.transport.channel import UniverseChannel

# The actions the Broker saves as pending. Looking is not one: it changes nothing.
ACTIONS = ("add_item", "mine", "join", "pick", "fly", "answer")

# What a brand new player is given, so that `drop` has something to drop.
STARTING_ITEMS = (("torch", "torch"),)


class Broker:
    """Holds each player's inventory and resource bag. Never touches the world
    directly: every change to the world goes through the channel as a Request.

    A drop moves the item round its cycle (owned, flight, done) and the real
    item then lives in the Universe. A pick goes through an ItemProxy: the
    Universe is asked, and only on yes does the Broker create a real entry and
    delete the proxy. A mine has no states: the bag grows only if the Universe
    says yes.

    Every change is written down as "pending" BEFORE it is sent, and crossed
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
        self._proxies: dict[str, ItemProxy] = {}  # op_id -> proxy of a pick in flight
        self._run_id = uuid4().hex[:8]
        self._op_numbers = count(1)
        self._universe = UniverseProxy(channel, self._next_op_id, self._send)
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

    def join(self, player_id: str, destination: str) -> Refusal | None:
        """Make sure the player exists here and has a place in the Universe.

        A new player gets a record and the starting items, each with its own
        unique id. Joining again changes nothing, because the Universe leaves a
        placed player where they are. None if all is well, otherwise why not.
        """
        if not player_id:
            raise ValueError("player_id must not be empty")
        if not destination:
            raise ValueError("destination must not be empty")
        if player_id not in self._inventories:
            self.add_player(player_id)
            for base_id, name in STARTING_ITEMS:
                unique_id = f"{base_id}-{uuid4().hex[:6]}"
                self.give(player_id, InventoryEntry(unique_id, name))
        return self._send(Request(self._next_op_id(), "join", player_id, destination))

    def drop(self, player_id: str, term: str) -> Refusal | None:
        """Drop what the player carries that is called `term` (an id or a name).
        None if the item is now in the world, otherwise why not."""
        inventory = self._inventories.get(player_id)
        if inventory is None:
            return self._unknown_player(f"drop {term}", player_id)
        entry = inventory.resolve(term)
        if entry is None:
            return inventory.not_carried("drop", term)
        refusal = inventory.begin_drop(entry.item_id)
        if refusal is not None:
            return refusal
        request = Request(
            self._next_op_id(), "add_item", player_id, entry.item_id, name=entry.name
        )
        return self._send(request)

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

    def look(self, player_id: str) -> list[ItemProxy] | Refusal:
        """A proxy for each item lying where the player is. Changes nothing."""
        if player_id not in self._inventories:
            return self._unknown_player("look", player_id)
        return self._universe.look(player_id)

    def where(self, player_id: str) -> tuple[str, str] | Refusal:
        """The (id, name) of the player's destination. Changes nothing."""
        if player_id not in self._inventories:
            return self._unknown_player("find out where you are", player_id)
        return self._universe.where(player_id)

    def fly(self, player_id: str, target: str) -> ItemInfo | Refusal:
        """Fly to the destination called `target`. The place arrived at, or why not."""
        if player_id not in self._inventories:
            return self._unknown_player(f"fly to {target}", player_id)
        wanted = target.strip().lower()
        if not wanted:
            return Refusal("fly", "no destination was given",
                           "type fly and the name of a destination")
        response = self._exchange(Request(self._next_op_id(), "fly", player_id, wanted))
        if response.refusal is not None:
            return response.refusal
        if len(response.items) != 1:
            return Refusal(f"fly to {wanted}", "the game gave an unexpected answer",
                           "type where to see where you are")
        return response.items[0]

    def mission(self, player_id: str) -> ItemInfo | Refusal:
        """The current mission as plain data. Changes nothing."""
        if player_id not in self._inventories:
            return self._unknown_player("read the mission", player_id)
        return self._universe.mission(player_id)

    def answer(self, player_id: str, text: str) -> ItemInfo | Refusal:
        """Answer the mission's question. The finished mission, or why not.
        Goes through the crash-safe path, because a right answer changes the world."""
        if player_id not in self._inventories:
            return self._unknown_player("answer", player_id)
        cleaned = " ".join(text.split())
        if not cleaned:
            return Refusal("answer", "no answer was given",
                           "type answer and then what you think it is")
        response = self._exchange(Request(self._next_op_id(), "answer", player_id, cleaned))
        return self._one_item(response, f"answer {cleaned}")

    @staticmethod
    def _one_item(response: Response, what: str) -> ItemInfo | Refusal:
        if response.refusal is not None:
            return response.refusal
        if len(response.items) != 1:
            return Refusal(what, "the game gave an unexpected answer", "try again in a moment")
        return response.items[0]

    def pick(self, player_id: str, term: str) -> Refusal | None:
        """Pick up what lies here and is called `term` (an id or a name).
        None if the item is now the player's, otherwise why not."""
        inventory = self._inventories.get(player_id)
        if inventory is None:
            return self._unknown_player(f"pick up {term}", player_id)
        seen = self._universe.look(player_id)
        if isinstance(seen, Refusal):
            return seen
        chosen = self._choose(seen, term)
        if isinstance(chosen, Refusal):
            return chosen
        if inventory.find(chosen.item_id) is not None:
            return Refusal(
                f"pick up {chosen.name}",
                f"you already carry a {chosen.name}",
                "drop yours first, or pick up something else",
            )
        return chosen.pick(player_id)

    def pending_count(self) -> int:
        """How many operations were sent and have not been settled yet."""
        return len(self._pending)

    def picks_in_flight(self) -> list[str]:
        """The state of every item proxy waiting for the Universe's answer."""
        return sorted(proxy.state() for proxy in self._proxies.values())

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

    @staticmethod
    def _choose(seen: list[ItemProxy], term: str) -> ItemProxy | Refusal:
        """The proxy that `term` means: an exact id first, then a name. Items
        that share a name are interchangeable, so the first by id is taken."""
        wanted = term.strip().lower()
        by_id = [proxy for proxy in seen if proxy.item_id.lower() == wanted]
        by_name = sorted(
            (proxy for proxy in seen if proxy.name.lower() == wanted),
            key=lambda proxy: proxy.item_id,
        )
        matches = by_id or by_name
        if not matches:
            return Refusal(
                f"pick up {term}",
                f"there is no {term} on the ground here",
                "type look to see what lies here",
            )
        return matches[0]

    def _send(self, request: Request, proxy: ItemProxy | None = None) -> Refusal | None:
        """Write the intention down, ask the Universe, then settle."""
        return self._exchange(request, proxy).refusal

    def _exchange(self, request: Request, proxy: ItemProxy | None = None) -> Response:
        """Like `_send`, but hands back the whole answer, for actions whose
        answer carries data."""
        if proxy is not None:
            self._proxies[request.op_id] = proxy
        self._pending[request.op_id] = request
        try:
            self._save()
        except OSError:
            # Not on disk, so it must not be sent: take the intention back.
            del self._pending[request.op_id]
            if request.action == "add_item":
                self._inventories[request.player_id].cancel_drop(request.item_id)
            waiting = self._proxies.pop(request.op_id, None)
            if waiting is not None:
                waiting.cancel_pick()
            raise
        response = self._channel.send(request)
        self._settle(request, response)
        return response

    def _settle(self, request: Request, response: Response) -> Refusal | None:
        """Apply the answer, cross the intention off, and save both together."""
        if request.action == "add_item":
            inventory = self._inventories[request.player_id]
            if response.ok:
                inventory.finish_drop(request.item_id)
            else:
                inventory.cancel_drop(request.item_id)
        elif request.action == "pick":
            self._settle_pick(request, response)
        elif request.action == "mine" and response.ok:
            self._resources[request.player_id].add(request.item_id, request.amount)
        del self._pending[request.op_id]
        self._save()
        return response.refusal

    def _settle_pick(self, request: Request, response: Response) -> None:
        # After a restart there is no proxy: the real entry is built from the
        # item data in the answer, which the Universe stored and replays.
        proxy = self._proxies.pop(request.op_id, None)
        if not response.ok:
            if proxy is not None:
                proxy.cancel_pick()
            return
        if proxy is not None:
            proxy.finish_pick()  # done: the proxy is now dropped from the Broker
        inventory = self._inventories[request.player_id]
        for info in response.items:
            if inventory.find(info.item_id) is None:
                inventory.add(InventoryEntry(info.item_id, info.name))

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
            # flight: it must stay locked until the drop is settled.
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