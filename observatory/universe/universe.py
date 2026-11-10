"""The Universe: owns the world and decides what happens in it."""

from observatory.common.messages import Request, Response
from observatory.common.refusal import Refusal
from observatory.universe.deposits import Deposits
from observatory.world.item import PlainItem
from observatory.world.room import Room
from observatory.world.world import World


class Universe:
    """The authority on the world. The Broker asks; the Universe decides.

    Only the Universe thread touches the world, so the world needs no lock.
    It knows each player's location and nothing else about them.
    """

    def __init__(self, world: World, deposits: Deposits | None = None) -> None:
        if not isinstance(world, World):
            raise TypeError(f"world must be a World, not {type(world).__name__}")
        if deposits is not None and not isinstance(deposits, Deposits):
            raise TypeError(f"deposits must be Deposits, not {type(deposits).__name__}")
        self._world = world
        self._deposits = deposits if deposits is not None else Deposits({})
        self._locations: dict[str, str] = {}
        self._answers: dict[str, Response] = {}
        # One row per action. Adding an action is one row and one method.
        self._handlers = {"add_item": self._add_item, "mine": self._mine}

    def place_player(self, player_id: str, room_id: str) -> None:
        if not player_id:
            raise ValueError("player_id must not be empty")
        try:
            self._world.room(room_id)
        except KeyError:
            raise ValueError(f"unknown room {room_id}") from None
        self._locations[player_id] = room_id

    def handle(self, request: Request) -> Response:
        if not isinstance(request, Request):
            raise TypeError(f"request must be a Request, not {type(request).__name__}")
        earlier = self._answers.get(request.op_id)
        if earlier is not None:
            return earlier
        response = self._decide(request)
        self._answers[request.op_id] = response
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
        room.add_item(PlainItem(request.item_id, request.item_id, f"a {request.item_id}"))
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