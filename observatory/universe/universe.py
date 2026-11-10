"""The Universe: owns the world and decides what happens in it."""

from observatory.common.messages import Request, Response
from observatory.common.refusal import Refusal
from observatory.universe.deposits import Deposits
from observatory.universe.universe_repository import (
    CorruptStateError,
    InMemoryUniverseRepository,
    UniverseRepository,
    UniverseState,
)
from observatory.world.item import PlainItem
from observatory.world.room import Room
from observatory.world.world import World


class Universe:
    """The authority on the world. The Broker asks; the Universe decides.

    Only the Universe thread touches the world, so the world needs no lock.
    It knows each player's location and nothing else about them.

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
        self._answers: dict[str, Response] = {}
        # One row per action. Adding an action is one row and one method.
        self._handlers = {"add_item": self._add_item, "mine": self._mine}
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

    def handle(self, request: Request) -> Response:
        if not isinstance(request, Request):
            raise TypeError(f"request must be a Request, not {type(request).__name__}")
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
        return Response(request.op_id)

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