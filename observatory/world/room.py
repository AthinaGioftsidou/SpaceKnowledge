"""A room is a place a player can occupy. It holds items and leads to other rooms."""

from observatory.world.container import Container
from observatory.world.door import Door
from observatory.world.holder import AmbiguousName
from observatory.world.holder import ItemHolder
from observatory.world.item import Item


class Room:
    """One location in the Observatory."""

    def __init__(self, room_id: str, name: str, description: str) -> None:
        # Same rule as Item: reject the arguments that would make this unusable.
        if not room_id:
            raise ValueError("room_id must not be empty")
        if not name:
            raise ValueError("name must not be empty")
        self._room_id = room_id
        self._name = name
        self._description = description
        # Composition, not inheritance: a Room is not an Item. Week 2 extracted
        # this from identical copies here and in Container.
        self._items = ItemHolder()
        self._exits: dict[str, Room] = {}
        # Separate from _exits: an exit is topology, a door is policy.
        self._doors: dict[str, Door] = {}

    @property
    def room_id(self) -> str:
        return self._room_id

    @property
    def name(self) -> str:
        return self._name


    def add_item(self, item: Item) -> None:
        """Place an item here. Delegates the collection rules to ItemHolder."""
        if not isinstance(item, Item):
            raise TypeError(f"item must be an Item, not {type(item).__name__}")
        self._items.add(item)

    def remove_item(self, item_id: str) -> Item:
        """Take an item out and return it. Raises if it is not here."""
        return self._items.remove(item_id)

    def find_item(self, item_id: str) -> Item | None:
        """Return the item, or None. None means absent, and absent is not an error."""
        return self._items.find(item_id)

    def item_count(self) -> int:
        return self._items.count()

    def match_item(self, term: str) -> Item | None:
        """Find by id or by display name. What a player typed, resolved."""
        return self._items.match(term)

    def open_container_holding(self, term: str) -> Container | None:
        """The container here holding a match for `term`.

        Until week 4 `take` reached only loose items, so the brass key had been
        sealed in the pigeonhole since week 2. The first locked door found it.
        """
        holding: list[Container] = []
        exact: list[Container] = []
        for item in self._items.contents():
            if isinstance(item, Container) and item.match(term) is not None:
                holding.append(item)
                if item.find(term) is not None:
                    exact.append(item)
        # The same rule as ItemHolder.match, one level up: an exact id wins,
        # and a name two containers both answer to is refused, not guessed.
        candidates = holding
        if len(exact) > 0:
            candidates = exact
        if len(candidates) > 1:
            matches: list[Item] = []
            for box in candidates:
                matches.append(box.match(term))
            raise AmbiguousName(matches)
        if len(candidates) == 1:
            return candidates[0]
        return None


    def item_total(self) -> int:
        """Every item in the room, containers' contents included."""
        return self._items.total()

    def contents(self) -> list[Item]:
        """Items lying loose here. A copy."""
        return self._items.contents()

    # Unquoted `Room` below: NameError on 3.13 and earlier, fine on 3.14.
    def add_exit(
        self, direction: str, destination: Room, door: Door | None = None
    ) -> None:
        """Connect this room to another in one direction only.
        Two-way exits are two calls, which keeps one-way passages possible.
        Directions are stored lower case: the parser lowercases what is typed,
        so an exit named `NORTH` could otherwise never be taken."""
        if not direction:
            raise ValueError("direction must not be empty")
        direction = direction.lower()
        if not isinstance(destination, Room):
            raise TypeError(f"destination must be a Room, not {type(destination).__name__}")
        if door is not None and not isinstance(door, Door):
            raise TypeError(f"door must be a Door, not {type(door).__name__}")
        self._exits[direction] = destination
        if door is not None:
            self._doors[direction] = door

    def exit_to(self, direction: str) -> Room | None:
        """Is there a way, which stays true when the way is locked. Whether you
        may USE it is `door_to`, deliberately a different question."""
        return self._exits.get(direction.lower())

    def door_to(self, direction: str) -> Door | None:
        """The barrier on that exit, or None if the way is open."""
        return self._doors.get(direction.lower())

    def exits(self) -> list[str]:
        """Every direction with an exit, sorted. A copy; locked ones included."""
        return sorted(self._exits)

    def describe(self) -> str:
        """The full text a player sees on entering or on typing `look`."""
        lines = [self._name, self._description]
        for item in self._items.contents():
            lines.append(f"There is {item.describe()} here.")
        if self._exits:
            lines.append("Exits: " + ", ".join(sorted(self._exits)))
        for direction in sorted(self._doors):
            door = self._doors[direction]
            if not door.is_passable():
                lines.append(f"The {door.name} {direction} is {door.state_name()}.")
        return "\n".join(lines)
