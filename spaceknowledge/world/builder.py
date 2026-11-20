"""Assembling a Destination one piece at a time instead of in one long call."""

from spaceknowledge.world.destination import Destination
from spaceknowledge.world.item import Item


class DestinationBuilder:
    """Collects the parts of a Destination, then produces a valid one.

    Single use: a builder that has produced a destination refuses to produce
    another, because a reused builder would leak the first one's items into the
    second.
    """

    def __init__(self, destination_id: str) -> None:
        if not destination_id:
            raise ValueError("destination_id must not be empty")
        self._destination_id = destination_id
        self._name: str | None = None
        self._description = ""
        self._items: list[Item] = []
        self._built = False

    # Each fluent method returns the builder, so calls can be chained.
    def named(self, name: str) -> DestinationBuilder:
        self._name = name
        return self

    def described(self, description: str) -> DestinationBuilder:
        self._description = description
        return self

    def holding(self, item: Item) -> DestinationBuilder:
        if not isinstance(item, Item):
            raise TypeError(f"item must be an Item, not {type(item).__name__}")
        self._items.append(item)
        return self

    def build(self) -> Destination:
        """Produce the destination, or refuse if something required is missing."""
        if self._built:
            raise ValueError("this builder has already produced a destination")
        if self._name is None:
            raise ValueError(f"destination {self._destination_id} was never named")
        destination = Destination(self._destination_id, self._name, self._description)
        for item in self._items:
            destination.add_item(item)
        self._built = True
        return destination