"""The galaxy: every destination, and the routes between them."""

from spaceknowledge.world.destination import Destination


class World:
    """Owns the destinations. Nothing else holds the collection."""

    def __init__(self, destinations: dict[str, Destination], start_destination_id: str) -> None:
        if not destinations:
            raise ValueError("a world must have at least one destination")
        if start_destination_id not in destinations:
            raise ValueError(f"start destination {start_destination_id} is not in the world")
        # Copied, so the caller cannot change our destinations afterwards.
        self._destinations = dict(destinations)
        self._start_destination_id = start_destination_id

    @property
    def start_destination(self) -> Destination:
        return self._destinations[self._start_destination_id]

    def destination(self, destination_id: str) -> Destination:
        """Raises KeyError if absent: an unknown id is a caller's mistake."""
        found = self._destinations.get(destination_id)
        if found is None:
            raise KeyError(destination_id)
        return found

    def item_total(self) -> int:
        """Every item in every destination, containers' contents included."""
        return sum(d.item_total() for d in self._destinations.values())

    def destination_count(self) -> int:
        return len(self._destinations)

    def destination_ids(self) -> list[str]:
        """Sorted, so callers and tests get a stable order."""
        return sorted(self._destinations)