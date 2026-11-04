"""A container is an item that holds other items, including other containers."""

from observatory.world.holder import ItemHolder
from observatory.world.item import Item


class Container(Item):
    """The Composite node. `Item` is the leaf, and a Container is both.

    Because Container IS-A Item, any code that accepts an Item accepts a
    container, and a container can hold containers to any depth.
    """

    def __init__(self, item_id: str, name: str, description: str) -> None:
        super().__init__(item_id, name)
        if not description:
            raise ValueError("description must not be empty")
        self._description = description
        # Same ItemHolder that Room uses. Before week 2 these two classes each
        # had their own identical copy of add, remove, find and count.
        self._contents = ItemHolder()

    def add(self, item: Item) -> None:
        """Put an item inside. Refuses the two cases that would corrupt the tree."""
        if not isinstance(item, Item):
            raise TypeError(f"item must be an Item, not {type(item).__name__}")
        # Direct self-containment only. The indirect cycle a-in-b-in-a is NOT
        # caught here, and that limit is deliberate. See the handout, section 4.
        if item is self:
            raise ValueError("a container cannot contain itself")
        self._contents.add(item)

    def remove(self, item_id: str) -> Item:
        """Take an item out of this container. Raises if not directly inside."""
        return self._contents.remove(item_id)

    def find(self, item_id: str) -> Item | None:
        """Search this container only, one level. Absent is None, not an error."""
        return self._contents.find(item_id)

    def count(self) -> int:
        """Direct contents only. A chest holding a box holding a key counts 1."""
        return self._contents.count()

    def match(self, term: str) -> Item | None:
        """Find by id or display name, one level. What a player typed."""
        return self._contents.match(term)

    def find_deep(self, item_id: str) -> Item | None:
        """Search this container and every container inside it, to any depth."""
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
        """What is directly inside. A copy, from ItemHolder. Same name and same
        promise as `Room.contents`, so a caller that walks both writes it once."""
        return self._contents.contents()

    def describe(self) -> str:
        """Recursive, so a nested container describes its own contents too."""
        if self._contents.count() == 0:
            return f"{self._description}, empty"
        described = []
        for item in self._contents.contents():
            described.append(item.describe())
        inner = ", ".join(described)
        return f"{self._description}, holding {inner}"
