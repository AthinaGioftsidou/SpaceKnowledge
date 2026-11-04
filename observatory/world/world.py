"""The World is the aggregate root: every room, and the way between them."""

from observatory.world.room import Room


class World:
    """Owns the rooms. Nothing else is allowed to hold the collection."""

    def __init__(self, rooms: dict[str, Room], start_room_id: str) -> None:
        if not rooms:
            raise ValueError("a world must have at least one room")
        if start_room_id not in rooms:
            raise ValueError(f"start room {start_room_id} is not in the world")
        # Copy, so the caller cannot mutate our rooms after construction.
        # Valid on construction is worth nothing if the caller keeps a handle.
        self._rooms = dict(rooms)
        self._start_room_id = start_room_id

    @property
    def start_room(self) -> Room:
        return self._rooms[self._start_room_id]

    def room(self, room_id: str) -> Room:
        """Raises if absent. A room id that does not exist is a caller mistake,
        not a question with a legitimate negative answer."""
        room = self._rooms.get(room_id)
        if room is None:
            raise KeyError(room_id)
        return room


    def item_total(self) -> int:
        """Every item in every room, containers' contents included."""
        total = 0
        for room in self._rooms.values():
            total += room.item_total()
        return total

    def room_count(self) -> int:
        return len(self._rooms)

    def room_ids(self) -> list[str]:
        """Sorted, so callers and tests get a stable order without depending on
        insertion order or on dict internals."""
        return sorted(self._rooms)
