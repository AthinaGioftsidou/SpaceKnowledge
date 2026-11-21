"""The Universe: the authority on the world. It decides what happens in it."""

from spaceknowledge.common.item_cycle import PICK, ItemCycle
from spaceknowledge.common.messages import ItemInfo, Request, Response
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.missions import COMPLETE, Mission, MissionBook, MissionError
from spaceknowledge.universe.universe_repository import (
    CorruptStateError,
    InMemoryUniverseRepository,
    UniverseRepository,
    UniverseState,
)
from spaceknowledge.world.container import Container
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.item import Item, PlainItem
from spaceknowledge.world.world import World

# Questions that change nothing. Their answers are not remembered or saved.
READ_ONLY = ("look", "where", "mission")

# How many answered operations are remembered. It must be larger than the
# number of operations that can be unfinished at once, because an answer that
# has been forgotten is decided again.
DEFAULT_MAX_ANSWERS = 1000


class Universe:
    """The Broker asks; the Universe decides.

    Only one request at a time changes the world (the listener holds a lock
    around `handle`), so the world needs no lock of its own. It knows each
    player's location and nothing else about them. Every item lying on the
    ground has an ItemCycle in the PICK process, held by the Universe until a
    pick finishes. Missions are shared: everybody's mining counts, and a
    finished mission opens a gate for everybody.

    State is loaded from the repository at start and saved after every request
    it decides, so a restart picks up where it stopped.
    """

    def __init__(
        self,
        world: World,
        deposits: Deposits | None = None,
        repository: UniverseRepository | None = None,
        max_answers: int = DEFAULT_MAX_ANSWERS,
        missions: MissionBook | None = None,
    ) -> None:
        if not isinstance(world, World):
            raise TypeError(f"world must be a World, not {type(world).__name__}")
        if deposits is not None and not isinstance(deposits, Deposits):
            raise TypeError(f"deposits must be Deposits, not {type(deposits).__name__}")
        if repository is not None and not isinstance(repository, UniverseRepository):
            raise TypeError(
                f"repository must be a UniverseRepository, not {type(repository).__name__}"
            )
        if isinstance(max_answers, bool) or not isinstance(max_answers, int):
            raise TypeError(f"max_answers must be an int, not {type(max_answers).__name__}")
        if max_answers < 1:
            raise ValueError("max_answers must be at least 1")
        if missions is not None and not isinstance(missions, MissionBook):
            raise TypeError(f"missions must be a MissionBook, not {type(missions).__name__}")
        self._world = world
        self._deposits = deposits if deposits is not None else Deposits({})
        self._repository = repository if repository is not None else InMemoryUniverseRepository()
        self._max_answers = max_answers
        self._missions = missions if missions is not None else MissionBook()
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
            "where": self._where,
            "pick": self._pick,
            "fly": self._fly,
            "mission": self._mission,
            "answer": self._answer,
        }
        self._check_missions_fit_the_world()
        self._restore()

    def place_player(self, player_id: str, destination_id: str) -> None:
        if not player_id:
            raise ValueError("player_id must not be empty")
        try:
            self._world.destination(destination_id)
        except KeyError:
            raise ValueError(f"unknown destination {destination_id}") from None
        self._locations[player_id] = destination_id
        self._save()

    def location_of(self, player_id: str) -> str | None:
        """The id of the destination the player is in, or None if unknown."""
        return self._locations.get(player_id)

    def answer_count(self) -> int:
        """How many answered operations are remembered. For tests and, later,
        the admin view."""
        return len(self._answers)

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
        self._forget_old_answers()
        self._save()
        return response

    def _forget_old_answers(self) -> None:
        """Keep the newest answers only. A dict keeps insertion order, so the
        first key is always the oldest."""
        while len(self._answers) > self._max_answers:
            del self._answers[next(iter(self._answers))]

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

    def _destination_of(self, request: Request) -> Destination | None:
        destination_id = self._locations.get(request.player_id)
        if destination_id is None:
            return None
        return self._world.destination(destination_id)

    def _unknown_player(self, request: Request) -> Response:
        return self._refuse(
            request,
            f"the Universe does not know where {request.player_id} is",
            "log in again, then retry",
        )

    @staticmethod
    def _put_item(destination: Destination, item_id: str, name: str) -> None:
        destination.add_item(PlainItem(item_id, name, f"a {name}"))

    @staticmethod
    def _info(item: Item) -> ItemInfo:
        return ItemInfo(item.item_id, item.name, item.describe())

    @staticmethod
    def _place(destination: Destination) -> ItemInfo:
        """A destination as plain data: an id, a name and a description."""
        return ItemInfo(
            destination.destination_id,
            destination.name,
            destination.description or destination.name,
        )

    def _join(self, request: Request) -> Response:
        """Place a player at the destination named in `item_id`. A player who
        is already somewhere stays there, so repeating a join is harmless."""
        destination = request.item_id
        try:
            self._world.destination(destination)
        except KeyError:
            return self._refuse(
                request,
                f"there is no destination called {destination}",
                "ask the administrator which destination to start from",
            )
        self._locations.setdefault(request.player_id, destination)
        return Response(request.op_id)

    def _add_item(self, request: Request) -> Response:
        destination = self._destination_of(request)
        if destination is None:
            return self._unknown_player(request)
        if destination.find_item(request.item_id) is not None:
            return self._refuse(
                request,
                f"there is already a {request.display_name} with that id in {destination.name}",
                "pick a different item, or pick the existing one up first",
            )
        self._put_item(destination, request.item_id, request.display_name)
        self._dropped.setdefault(destination.destination_id, []).append(request.item_id)
        self._ground.setdefault(destination.destination_id, {})[request.item_id] = ItemCycle(
            request.item_id, PICK
        )
        return Response(request.op_id)

    def _look(self, request: Request) -> Response:
        """What lies here, as plain data. Changes nothing."""
        destination = self._destination_of(request)
        if destination is None:
            return self._unknown_player(request)
        items = sorted(destination.contents(), key=lambda item: item.item_id)
        return Response(request.op_id, items=tuple(self._info(item) for item in items))

    def _where(self, request: Request) -> Response:
        """Where the player is, as plain place data. Changes nothing."""
        destination = self._destination_of(request)
        if destination is None:
            return self._unknown_player(request)
        return Response(request.op_id, items=(self._place(destination),))

    def _fly(self, request: Request) -> Response:
        """Move the player along a route, if there is one and its door is open.
        The answer names the place arrived at."""
        here = self._destination_of(request)
        if here is None:
            return self._unknown_player(request)
        target = here.exit_to(request.item_id)
        routes = ", ".join(here.exits())
        if target is None:
            return self._refuse(
                request,
                f"there is no route to {request.item_id} from {here.name}",
                f"fly to one of: {routes}" if routes
                else f"{here.name} has no routes, so stay here",
            )
        door = here.door_to(request.item_id)
        if door is not None and not door.is_passable():
            return self._refuse(
                request,
                f"the way to {target.name} is shut ({door.refusal()})",
                "complete what opens it, or fly somewhere else",
            )
        self._locations[request.player_id] = target.destination_id
        return Response(request.op_id, items=(self._place(target),))

    def _pick(self, request: Request) -> Response:
        """Is it ok to pick this up? If yes, the real item leaves the world and
        its data goes to the Broker. The queue makes the first request win."""
        destination = self._destination_of(request)
        if destination is None:
            return self._unknown_player(request)
        item = destination.find_item(request.item_id)
        if item is None:
            return self._refuse(
                request,
                f"there is no {request.item_id} on the ground in {destination.name}, "
                "it may already have been picked up",
                "type look to see what lies here",
            )
        if isinstance(item, Container):
            return self._refuse(
                request,
                f"the {item.name} is a container, and only single items can be picked up",
                "leave it, or pick up something else",
            )
        cycles = self._ground.setdefault(destination.destination_id, {})
        cycle = cycles.get(item.item_id)
        if cycle is None:
            cycle = ItemCycle(item.item_id, PICK)
        refusal = cycle.begin(PICK)  # reserved: nobody else can take it now
        if refusal is not None:
            return Response(request.op_id, refusal)
        destination.remove_item(item.item_id)
        cycle.finish(PICK)  # done: the Broker holds it
        cycles.pop(item.item_id, None)
        lying = self._dropped.get(destination.destination_id, [])
        if item.item_id in lying:
            lying.remove(item.item_id)
        return Response(request.op_id, items=(self._info(item),))

    def _mine(self, request: Request) -> Response:
        destination = self._destination_of(request)
        if destination is None:
            return self._unknown_player(request)
        left = self._deposits.available(destination.destination_id, request.item_id)
        if left == 0:
            return self._refuse(
                request,
                f"there is no {request.item_id} to mine on {destination.name}",
                "travel to a destination that has it, or mine something else",
            )
        if request.amount > left:
            return self._refuse(
                request,
                f"{destination.name} has only {left} {request.item_id} left, "
                f"and you asked for {request.amount}",
                f"ask for {left} or fewer",
            )
        self._deposits.remove(destination.destination_id, request.item_id, request.amount)
        # The Universe saw the mining itself, so it counts it for the mission.
        self._missions.record_mining(
            destination.destination_id, request.item_id, request.amount
        )
        return Response(request.op_id)

    def _mission_info(self, mission: Mission) -> ItemInfo:
        """A mission as plain data: its status, its title and what to tell the
        player."""
        return ItemInfo(
            self._missions.status(mission.mission_id), mission.title, self._missions.text(mission)
        )

    def _mission(self, request: Request) -> Response:
        """The current mission and how far it has got. Changes nothing."""
        if self._locations.get(request.player_id) is None:
            return self._unknown_player(request)
        mission = self._missions.current()
        if mission is None:
            return self._refuse(
                request, "there is no mission in this galaxy yet", "explore, and check back later"
            )
        return Response(request.op_id, items=(self._mission_info(mission),))

    def _answer(self, request: Request) -> Response:
        """Answer the question the current mission is waiting on. A right answer
        completes the mission and opens its gate for everybody."""
        if self._locations.get(request.player_id) is None:
            return self._unknown_player(request)
        result = self._missions.answer(request.item_id)
        if result is None:
            return self._refuse(
                request,
                "there is no question waiting for an answer",
                "type mission to see what needs doing",
            )
        mission, correct = result
        if not correct:
            return self._refuse(request, "that is not the answer", f"think again: {mission.hint}")
        self._open_way(mission)
        return Response(request.op_id, items=(self._mission_info(mission),))

    def _open_way(self, mission: Mission) -> None:
        """Unlock the gate that this mission opens."""
        door = self._world.destination(mission.opens_from).door_to(mission.opens_direction)
        if door is not None:
            door.unlock(door.key_id)

    def _check_missions_fit_the_world(self) -> None:
        """Every mission must open a gate that exists and that only it can open."""
        for mission in self._missions.all():
            try:
                door = self._world.destination(mission.opens_from).door_to(mission.opens_direction)
            except KeyError:
                raise ValueError(
                    f"the mission {mission.mission_id} opens a route from "
                    f"{mission.opens_from}, which is not in this world"
                ) from None
            if door is None or door.key_id != mission.key():
                raise ValueError(
                    f"the mission {mission.mission_id} needs a door on {mission.opens_from} "
                    f"{mission.opens_direction} whose key is {mission.key()}"
                )

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
        for destination_id, item_ids in state.dropped.items():
            for item_id in item_ids:
                self._put_item(
                    self._world.destination(destination_id),
                    item_id,
                    state.names.get(item_id, item_id),
                )
                self._ground.setdefault(destination_id, {})[item_id] = ItemCycle(item_id, PICK)
        self._locations = dict(state.locations)
        self._dropped = {d: list(ids) for d, ids in state.dropped.items()}
        self._answers = dict(state.answers)
        self._forget_old_answers()
        self._missions.restore(state.missions)
        # Doors are not saved: a finished mission simply opens its gate again.
        for mission in self._missions.all():
            if self._missions.status(mission.mission_id) == COMPLETE:
                self._open_way(mission)

    def _check_against_world(self, state: UniverseState) -> None:
        named = [*state.locations.values(), *state.stock, *state.dropped]
        for destination_id in named:
            try:
                self._world.destination(destination_id)
            except KeyError:
                raise CorruptStateError(
                    f"the saved state names {destination_id}, which is not in this world"
                ) from None
        for destination_id, item_ids in state.dropped.items():
            destination = self._world.destination(destination_id)
            for item_id in item_ids:
                if destination.find_item(item_id) is not None:
                    raise CorruptStateError(
                        f"the saved state drops {item_id} in {destination.name}, "
                        "where one already lies"
                    )
        try:
            self._missions.check(state.missions)
        except MissionError as problem:
            raise CorruptStateError(str(problem)) from None

    def _dropped_names(self) -> dict[str, str]:
        """The display name of every dropped item still lying in the world."""
        names: dict[str, str] = {}
        for destination_id, item_ids in self._dropped.items():
            destination = self._world.destination(destination_id)
            for item_id in item_ids:
                item = destination.find_item(item_id)
                if item is not None:
                    names[item_id] = item.name
        return names

    def _save(self) -> None:
        self._repository.save(
            UniverseState(
                dict(self._locations),
                self._deposits.snapshot(),
                {d: list(ids) for d, ids in self._dropped.items()},
                dict(self._answers),
                self._dropped_names(),
                self._missions.snapshot(),
            )
        )