"""One implementation of "a thing that holds items, addressed by id".

Extracted in week 2. Before that, `Room` and `Container` each had their own copy
of add, remove, find and count, and the four bodies were identical.

Held by composition rather than inherited, so a Room is not an Item and a
Container does not need two base classes.
"""

from observatory.world.item import Item


class AmbiguousName(Exception):
    """More than one item answers to what the player typed.

    The message lists their ids, which are unique, so typing one of them picks
    exactly one item. Raised before anything moves, so a refusal changes nothing.
    """

    def __init__(self, items: list[Item]) -> None:
        ids = []
        for item in items:
            ids.append(item.item_id)
        ids.sort()
        super().__init__(f"Which {items[0].name}? {', '.join(ids)}")


class ItemHolder:
    """A collection of items with unique ids. Not an Item itself."""

    def __init__(self) -> None:
        self._items: list[Item] = []

    def add(self, item: Item) -> None:
        """Duplicate ids are refused rather than merged, because two items
        sharing an id cannot be told apart by any verb that names one."""
        if not isinstance(item, Item):
            raise TypeError(f"item must be an Item, not {type(item).__name__}")
        if self.find(item.item_id) is not None:
            raise ValueError(f"already holds an item with id {item.item_id}")
        self._items.append(item)

    def remove(self, item_id: str) -> Item:
        """Raises if absent. Removing something not here is a caller mistake."""
        item = self.find(item_id)
        if item is None:
            raise KeyError(item_id)
        self._items.remove(item)
        return item

    def find(self, item_id: str) -> Item | None:
        """Absent is None, not an error. Asking is a fair question."""
        for item in self._items:
            if item.item_id == item_id:
                return item
        return None

    def match(self, term: str) -> Item | None:
        """Find by id, or failing that by name, case insensitive.

        Added in week 3. Until now every lookup was by id, so a player had to
        type `brass_key` rather than `brass key`. Ids are tried first so an
        exact id can never be shadowed by someone else's display name.

        Ids are unique and names are not. Two items sharing the name raise
        AmbiguousName rather than one of them being picked silently.
        """
        exact = self.find(term)
        if exact is not None:
            return exact
        wanted = term.strip().lower()
        named: list[Item] = []
        for item in self._items:
            if item.name.lower() == wanted:
                named.append(item)
        if len(named) > 1:
            raise AmbiguousName(named)
        if len(named) == 1:
            return named[0]
        return None

    def total(self) -> int:
        """Every item here, and every item inside those, at every depth."""
        total = 0
        for item in self._items:
            total += 1 + item.total_inside()
        return total

    def count(self) -> int:
        return len(self._items)

    def contents(self) -> list[Item]:
        """A copy. Callers may iterate it freely without reaching our list."""
        return list(self._items)
