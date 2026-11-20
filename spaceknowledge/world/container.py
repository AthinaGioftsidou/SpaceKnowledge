"""A container is an item that holds other items, including other containers."""

from spaceknowledge.world.holder import ItemHolder
from spaceknowledge.world.item import Item


class Container(Item):
    """The composite node: an Item that can hold Items.

    Because a Container is an Item, anything that accepts an item accepts a
    container, and containers can nest to any depth.
    """

    def __init__(self, item_id: str, name: str, description: str) -> None:
        super().__init__(item_id, name)
        if not description:
            raise ValueError("description must not be empty")
        self._description = description
        self._contents = ItemHolder()

    def add(self, item: Item) -> None:
        """Put an item inside. Refuses a duplicate id and direct self-containment.
        An indirect cycle (a in b in a) is deliberately not detected."""
        if not isinstance(item, Item):
            raise TypeError(f"item must be an Item, not {type(item).__name__}")
        if item is self:
            raise ValueError("a container cannot contain itself")
        self._contents.add(item)

    def remove(self, item_id: str) -> Item:
        """Raises KeyError if the item is not directly inside."""
        return self._contents.remove(item_id)

    def find(self, item_id: str) -> Item | None:
        """One level only. Absent is None."""
        return self._contents.find(item_id)

    def count(self) -> int:
        """Direct contents only: a chest holding a box holding a key counts 1."""
        return self._contents.count()

    def match(self, term: str) -> Item | None:
        """Find by id or name, one level."""
        return self._contents.match(term)

    def find_deep(self, item_id: str) -> Item | None:
        """Search this container and every container inside it."""
        for item in self._contents.contents():
            if item.item_id == item_id:
                return item
            if isinstance(item, Container):
                found = item.find_deep(item_id)
                if found is not None:
                    return found
        return None

    def total_inside(self) -> int:
        return self._contents.total()

    def contents(self) -> list[Item]:
        """What is directly inside. A copy."""
        return self._contents.contents()

    def describe(self) -> str:
        """Recursive, so nested containers describe their contents too."""
        if self._contents.count() == 0:
            return f"{self._description}, empty"
        inner = ", ".join(item.describe() for item in self._contents.contents())
        return f"{self._description}, holding {inner}"