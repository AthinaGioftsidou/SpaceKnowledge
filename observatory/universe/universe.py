"""The Universe: owns the world and decides what happens in it."""

from observatory.common.messages import Request, Response
from observatory.common.refusal import Refusal
from observatory.world.item import PlainItem
from observatory.world.world import World


class Universe:
    """The authority on the world. The Broker asks; the Universe decides.

    Only the Universe thread touches the world, so the world needs no lock.
    It knows each player's location and nothing else about them.
    """

    def __init__(self, world: World) -> None:
        if not isinstance(world, World):
            raise TypeError(f"world must be a World, not {type(world).__name__}")
        self._world = world
        self._locations: dict[str, str] = {}
        self._answers: dict[str, Response] = {}

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
        if request.action == "add_item":
            return self._add_item(request)
        return self._refuse(
            request,
            f"the Universe does not know the action {request.action}",
            "send a supported action, such as add_item",
        )

    def _add_item(self, request: Request) -> Response:
        room_id = self._locations.get(request.player_id)
        if room_id is None:
            return self._refuse(
                request,
                f"the Universe does not know where {request.player_id} is",
                "log in again, then retry",
            )
        room = self._world.room(room_id)
        if room.find_item(request.item_id) is not None:
            return self._refuse(
                request,
                f"there is already a {request.item_id} in {room.name}",
                "pick a different item, or pick the existing one up first",
            )
        room.add_item(PlainItem(request.item_id, request.item_id, f"a {request.item_id}"))
        return Response(request.op_id)

    def _refuse(self, request: Request, why: str, next_step: str) -> Response:
        refusal = Refusal(f"{request.action} {request.item_id}", why, next_step)
        return Response(request.op_id, refusal)