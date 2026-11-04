"""Items are the things that exist inside a room."""

from abc import ABC, abstractmethod


class Item(ABC):
    """Base type for anything a room can hold.

    This is an abstract class in the same sense as Java's `abstract class` or
    C#'s `abstract class`. It cannot be instantiated and it declares one method
    that every subclass must supply.
    """

    def __init__(self, item_id: str, name: str) -> None:
        # Checked here, not by the caller, so an unusable Item can never exist.
        # Java and C# call this an invariant established by the constructor.
        if not item_id:
            raise ValueError("item_id must not be empty")
        if not name:
            raise ValueError("name must not be empty")
        self._item_id = item_id
        self._name = name

    @property
    def item_id(self) -> str:
        """Stable identifier. Two items in one room may not share one."""
        return self._item_id

    @property
    def name(self) -> str:
        """Short label a player types, for example "brass key"."""
        return self._name

    def total_inside(self) -> int:
        """Items held inside this one, at every depth. A plain item holds none."""
        return 0

    @abstractmethod
    def describe(self) -> str:
        """Return the single line shown when a player looks at this item."""


class PlainItem(Item):
    """An item with a fixed description and no behaviour of its own."""

    def __init__(self, item_id: str, name: str, description: str) -> None:
        # super() first, so the base invariant holds before we add to it.
        super().__init__(item_id, name)
        if not description:
            raise ValueError("description must not be empty")
        self._description = description

    def describe(self) -> str:
        return self._description
