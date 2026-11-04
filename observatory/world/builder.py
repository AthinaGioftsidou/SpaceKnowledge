"""Assembling a Room a piece at a time, instead of in one long call.

`Room.__init__` takes three arguments today. By week 4 a room also carries a
lock, a visited flag and a puzzle marker, and a six-argument positional call is
unreadable and easy to get wrong by one position.
"""

from observatory.world.item import Item
from observatory.world.room import Room


class RoomBuilder:
    """Collects the parts of a Room, then produces one that is valid.

    Single use. A builder that has produced a room refuses to produce another,
    because reuse is almost always a mistake and a shared builder silently
    leaks the previous room's items into the next one.
    """

    def __init__(self, room_id: str) -> None:
        if not room_id:
            raise ValueError("room_id must not be empty")
        self._room_id = room_id
        self._name: str | None = None
        self._description = ""
        self._items: list[Item] = []
        self._built = False

    # Fluent methods return the builder, which is the unquoted forward
    # reference from week 1. On 3.13 each of these needs "RoomBuilder".
    def named(self, name: str) -> RoomBuilder:
        self._name = name
        return self

    def described(self, description: str) -> RoomBuilder:
        self._description = description
        return self

    def holding(self, item: Item) -> RoomBuilder:
        if not isinstance(item, Item):
            raise TypeError(f"item must be an Item, not {type(item).__name__}")
        self._items.append(item)
        return self

    def _refuse_reuse(self) -> None:
        """A builder that has produced a room may not produce another."""
        if self._built:
            raise ValueError("this builder has already produced a room")

    def build(self) -> Room:
        """Produce the room. Refuses if anything required is missing."""
        # --- INSTRUCTOR SWAP 04 : week 02 : defect in the CODE ---------------
        #   pass                                                     # BROKEN
        self._refuse_reuse()
        # --- END INSTRUCTOR SWAP 04 -------------------------------------------
        if self._name is None:
            raise ValueError(f"room {self._room_id} was never named")
        room = Room(self._room_id, self._name, self._description)
        for item in self._items:
            room.add_item(item)
        self._built = True
        return room
