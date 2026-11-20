"""Items: the things that can lie in a destination or be carried by a player."""

from abc import ABC, abstractmethod


class Item(ABC):
    """Anything a destination can hold.

    Abstract: a concrete kind must say how it describes itself, so a bare Item
    can never exist.
    """

    def __init__(self, item_id: str, name: str) -> None:
        # Checked here so an unusable item can never be created.
        if not item_id:
            raise ValueError("item_id must not be empty")
        if not name:
            raise ValueError("name must not be empty")
        self._item_id = item_id
        self._name = name

    @property
    def item_id(self) -> str:
        """The item's identity. Unique within one holder."""
        return self._item_id

    @property
    def name(self) -> str:
        """The label a player types and reads, for example "brass key"."""
        return self._name

    def total_inside(self) -> int:
        """Items held inside this one, at every depth. A plain item holds none."""
        return 0

    @abstractmethod
    def describe(self) -> str:
        """The single line shown when a player looks at this item."""


class PlainItem(Item):
    """An item with a fixed description and no behaviour of its own."""

    def __init__(self, item_id: str, name: str, description: str) -> None:
        super().__init__(item_id, name)
        if not description:
            raise ValueError("description must not be empty")
        self._description = description

    def describe(self) -> str:
        return self._description