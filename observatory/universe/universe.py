"""The Universe: owns the world and decides what happens in it."""

from observatory.common.item_cycle import PICK, ItemCycle
from observatory.common.messages import ItemInfo, Request, Response
from observatory.common.refusal import Refusal
from observatory.universe.deposits import Deposits
from observatory.universe.universe_repository import (
    CorruptStateError,
    InMemoryUniverseRepository,
    UniverseRepository,
    UniverseState,
)
from observatory.world.container import Container
from observatory.world.item import Item, PlainItem
from observatory.world.room import Room
from observatory.world.world import World

# Questions that change nothing. Their answers are not remembered or saved.
READ_ONLY = ("look",)


class Universe:
    """The authority on the world. The Broker asks; the Universe decides.

    Only the Universe thread touches the world, so the world needs no lock.
    It knows each player's location and nothing else about them. Every item
    lying on the ground is an ItemCycle in the PICK process, held by the
    Universe until a pick finishes.

    Loads its state from the repository when it starts, and saves after every
    request it decides, so a restart picks up where it stopped.
    """

    def __init__(
        self,
        world: World,
        deposits: Deposits | None = None,
        repository: UniverseRepository | None = None,
    ) -> None:
        if not isinstance(world, World):
            raise TypeError(f"world must be a World, not {type(world).__name__}")
        if deposits is not None and not isinstance(deposits, Deposits):
            raise TypeError(f"deposits must be Deposits, not {type(deposits).__name__}")
        if repository is not None and not isinstance(repository, UniverseRepository):
            raise TypeError(
                f"repository must be a UniverseRepository, not {type(repository).__name__}"
            )
        self._world = world
        self._deposits = deposits if deposits is not None else Deposits({})
        self._repository = repository if repository is not None else InMemoryUniverseRepository()
        self._locations: dict[str, str] = {}
        self._dropped: dict[str, list[str]] = {}
        self._ground: dict[str, dict[str, ItemCycle]] = {}
        self._answers: dict[str, Response] = {}
        # One row per action. Adding an action is one row and one method.
        self._handlers = {
            "add_item": self._add_item,
            "mine": self._mine,
            "join": self._join,
            "look": self._look,
            "pick": self._pick,
        }
        self._restore()

    def place_player(self, player_id: str, room_id: str) -> None:
        if not player_id:
            raise ValueError("player_id must not be empty")
        try:
            self._world.room(room_id)
        except KeyError:
            raise ValueError(f"unknown room {room_id}") from None
        self._locations[player_id] = room_id
        self._save()

    def location_of(self, player_id: str) -> str | None:
        """The id of the destination the player is in, or None if unknown."""
        return self._locations.get(player_id)

    def handle(self, request: Request) -> Response:
        if not isinstance(request, Request):
            raise TypeError(f"request must be a Request, not {type(request).__name__}")
        if request.action in READ_ONLY:
            return self._decide(request)
        earlier = self._answers.get(request.op_id)
        if earlier is not None:
            return earlier
        response = self._decide(request)
        self._answers[request.op_id] = response
        self._save()
        return response

    def _decide(self, request: Request) -> Response:
        handler = self._handlers.get(request.action)
        if handler is None:
            known = ", ".join(sorted(self._handlers))
            return self._refuse(
                request,
                f"the Universe does not know the action {request.action}",
                f"send one of: {known}",
            )
        return handler(request)

    def _room_of(self, request: Request) -> Room | None:
        room_id = self._locations.get(request.player_id)
        if room_id is None:
            return None
        return self._world.room(room_id)

    def _unknown_player(self, request: Request) -> Response:
        return self._refuse(
            request,
            f"the Universe does not know where {request.player_id} is",
            "log in again, then retry",
        )

    @staticmethod
    def _put_item(room: Room, item_id: str) -> None:
        room.add_item(PlainItem(item_id, item_id, f"a {item_id}"))

    @staticmethod
    def _info(item: Item) -> ItemInfo:
        return ItemInfo(item.item_id, item.name, item.describe())

    def _join(self, request: Request) -> Response:
        """Place a player at the destination named in `item_id`. A player who
        is already somewhere stays there, so repeating a join is harmless."""
        destination = request.item_id
        try:
            self._world.room(destination)
        except KeyError:
            return self._refuse(
                request,
                f"there is no destination called {destination}",
                "ask the administrator which destination to start from",
            )
        self._locations.setdefault(request.player_id, destination)
        return Response(request.op_id)

    def _add_item(self, request: Request) -> Response:
        room = self._room_of(request)
        if room is None:
            return self._unknown_player(request)
        if room.find_item(request.item_id) is not None:
            return self._refuse(
                request,
                f"there is already a {request.item_id} in {room.name}",
                "pick a different item, or pick the existing one up first",
            )
        self._put_item(room, request.item_id)
        self._dropped.setdefault(room.room_id, []).append(request.item_id)
        self._ground.setdefault(room.room_id, {})[request.item_id] = ItemCycle(
            request.item_id, PICK
        )
        return Response(request.op_id)

    def _look(self, request: Request) -> Response:
        """What lies here, as plain data. Changes nothing."""
        room = self._room_of(request)
        if room is None:
            return self._unknown_player(request)
        items = sorted(room.contents(), key=lambda item: item.item_id)
        return Response(request.op_id, items=tuple(self._info(item) for item in items))

    def _pick(self, request: Request) -> Response:
        """Is it ok to pick this up? If yes, the real item leaves the world and
        its data goes to the Broker. The queue makes the first request win."""
        room = self._room_of(request)
        if room is None:
            return self._unknown_player(request)
        item = room.find_item(request.item_id)
        if item is None:
            return self._refuse(
                request,
                f"there is no {request.item_id} on the ground in {room.name}, "
                "it may already have been picked up",
                "type look to see what lies here",
            )
        if isinstance(item, Container):
            return self._refuse(
                request,
                f"the {item.name} is a container, and only single items can be picked up",
                "leave it, or pick up something else",
            )
        cycles = self._ground.setdefault(room.room_id, {})
        cycle = cycles.get(item.item_id)
        if cycle is None:
            cycle = ItemCycle(item.item_id, PICK)
        refusal = cycle.begin(PICK)  # reserved: nobody else can take it now
        if refusal is not None:
            return Response(request.op_id, refusal)
        room.remove_item(item.item_id)
        cycle.finish(PICK)  # done: the Broker holds it
        cycles.pop(item.item_id, None)
        lying = self._dropped.get(room.room_id, [])
        if item.item_id in lying:
            lying.remove(item.item_id)
        return Response(request.op_id, items=(self._info(item),))

    def _mine(self, request: Request) -> Response:
        room = self._room_of(request)
        if room is None:
            return self._unknown_player(request)
        left = self._deposits.available(room.room_id, request.item_id)
        if left == 0:
            return self._refuse(
                request,
                f"there is no {request.item_id} to mine on {room.name}",
                "travel to a destination that has it, or mine something else",
            )
        if request.amount > left:
            return self._refuse(
                request,
                f"{room.name} has only {left} {request.item_id} left, "
                f"and you asked for {request.amount}",
                f"ask for {left} or fewer",
            )
        self._deposits.remove(room.room_id, request.item_id, request.amount)
        return Response(request.op_id)

    def _refuse(self, request: Request, why: str, next_step: str) -> Response:
        refusal = Refusal(f"{request.action} {request.item_id}", why, next_step)
        return Response(request.op_id, refusal)

    def _restore(self) -> None:
        state = self._repository.load()
        if state is None:
            return
        # Check everything first, so a bad file changes nothing at all.
        self._check_against_world(state)
        self._deposits.restore(state.stock)
        for room_id, item_ids in state.dropped.items():
            for item_id in item_ids:
                self._put_item(self._world.room(room_id), item_id)
                self._ground.setdefault(room_id, {})[item_id] = ItemCycle(item_id, PICK)
        self._locations = dict(state.locations)
        self._dropped = {room_id: list(ids) for room_id, ids in state.dropped.items()}
        self._answers = dict(state.answers)

    def _check_against_world(self, state: UniverseState) -> None:
        named = [*state.locations.values(), *state.stock, *state.dropped]
        for room_id in named:
            try:
                self._world.room(room_id)
            except KeyError:
                raise CorruptStateError(
                    f"the saved state names {room_id}, which is not in this world"
                ) from None
        for room_id, item_ids in state.dropped.items():
            room = self._world.room(room_id)
            for item_id in item_ids:
                if room.find_item(item_id) is not None:
                    raise CorruptStateError(
                        f"the saved state drops {item_id} in {room.name}, where one already lies"
                    )

    def _save(self) -> None:
        self._repository.save(
            UniverseState(
                dict(self._locations),
                self._deposits.snapshot(),
                {room_id: list(ids) for room_id, ids in self._dropped.items()},
                dict(self._answers),
            )
        )