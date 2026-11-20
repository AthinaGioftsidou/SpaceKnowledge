"""A destination: a place a player can be. It holds items and leads elsewhere."""

from spaceknowledge.world.container import Container
from spaceknowledge.world.door import Door
from spaceknowledge.world.holder import AmbiguousName, ItemHolder
from spaceknowledge.world.item import Item


class Destination:
    """One place in the galaxy, such as a planet, a moon or a station."""

    def __init__(self, destination_id: str, name: str, description: str) -> None:
        if not destination_id:
            raise ValueError("destination_id must not be empty")
        if not name:
            raise ValueError("name must not be empty")
        self._destination_id = destination_id
        self._name = name
        self._description = description
        self._items = ItemHolder()
        self._exits: dict[str, Destination] = {}
        # Kept apart from exits: an exit is the map, a door is a rule on it.
        self._doors: dict[str, Door] = {}

    @property
    def destination_id(self) -> str:
        return self._destination_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    def add_item(self, item: Item) -> None:
        if not isinstance(item, Item):
            raise TypeError(f"item must be an Item, not {type(item).__name__}")
        self._items.add(item)

    def remove_item(self, item_id: str) -> Item:
        """Raises KeyError if the item is not here."""
        return self._items.remove(item_id)

    def find_item(self, item_id: str) -> Item | None:
        """None means absent, and absent is not an error."""
        return self._items.find(item_id)

    def item_count(self) -> int:
        return self._items.count()

    def match_item(self, term: str) -> Item | None:
        """Find by id or by display name: what a player typed, resolved."""
        return self._items.match(term)

    def open_container_holding(self, term: str) -> Container | None:
        """The container here that holds a match for `term`.

        An exact id wins. A name that two containers both answer to raises
        AmbiguousName, the same rule as ItemHolder.match one level up.
        """
        holding: list[Container] = []
        exact: list[Container] = []
        for item in self._items.contents():
            if isinstance(item, Container) and item.match(term) is not None:
                holding.append(item)
                if item.find(term) is not None:
                    exact.append(item)
        candidates = exact if exact else holding
        if len(candidates) > 1:
            raise AmbiguousName([box.match(term) for box in candidates])
        return candidates[0] if candidates else None

    def item_total(self) -> int:
        """Every item here, containers' contents included."""
        return self._items.total()

    def contents(self) -> list[Item]:
        """Items lying loose here. A copy."""
        return self._items.contents()

    def add_exit(
        self, direction: str, destination: Destination, door: Door | None = None
    ) -> None:
        """Connect this destination to another in ONE direction.

        A two-way route is two calls, which keeps one-way routes possible.
        Directions are stored in lower case because the parser lower-cases
        what is typed.
        """
        if not direction:
            raise ValueError("direction must not be empty")
        if not isinstance(destination, Destination):
            raise TypeError(
                f"destination must be a Destination, not {type(destination).__name__}"
            )
        if door is not None and not isinstance(door, Door):
            raise TypeError(f"door must be a Door, not {type(door).__name__}")
        direction = direction.lower()
        self._exits[direction] = destination
        if door is not None:
            self._doors[direction] = door

    def exit_to(self, direction: str) -> Destination | None:
        """Is there a route? Stays true when the route is locked: whether it
        may be USED is `door_to`, a deliberately different question."""
        return self._exits.get(direction.lower())

    def door_to(self, direction: str) -> Door | None:
        """The door on that route, or None if it is open."""
        return self._doors.get(direction.lower())

    def exits(self) -> list[str]:
        """Every direction with a route, sorted. Locked ones included."""
        return sorted(self._exits)

    def describe(self) -> str:
        """The text shown on arriving or on `look`."""
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