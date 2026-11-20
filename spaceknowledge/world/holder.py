"""One implementation of "something that holds items, addressed by id"."""

from spaceknowledge.world.item import Item


class AmbiguousName(Exception):
    """More than one item answers to what the player typed.

    The message lists their ids, which are unique, so typing one of them picks
    exactly one item. It is raised before anything moves, so refusing changes
    nothing.
    """

    def __init__(self, items: list[Item]) -> None:
        ids = sorted(item.item_id for item in items)
        super().__init__(f"Which {items[0].name}? {', '.join(ids)}")


class ItemHolder:
    """A collection of items with unique ids. Used by destinations and
    containers through composition, so neither needs a second base class."""

    def __init__(self) -> None:
        self._items: list[Item] = []

    def add(self, item: Item) -> None:
        """A duplicate id is refused, because two items with one id could not
        be told apart by anything that names an id."""
        if not isinstance(item, Item):
            raise TypeError(f"item must be an Item, not {type(item).__name__}")
        if self.find(item.item_id) is not None:
            raise ValueError(f"already holds an item with id {item.item_id}")
        self._items.append(item)

    def remove(self, item_id: str) -> Item:
        """Raises KeyError if absent: removing what is not here is a mistake."""
        item = self.find(item_id)
        if item is None:
            raise KeyError(item_id)
        self._items.remove(item)
        return item

    def find(self, item_id: str) -> Item | None:
        """Exact id. Absent is None, because asking is a fair question."""
        for item in self._items:
            if item.item_id == item_id:
                return item
        return None

    def match(self, term: str) -> Item | None:
        """Find by id first, then by name (any case).

        Ids come first so an exact id is never shadowed by another item's
        name. Names are not unique, so two items with the same name raise
        AmbiguousName instead of one being chosen silently.
        """
        exact = self.find(term)
        if exact is not None:
            return exact
        wanted = term.strip().lower()
        named = [item for item in self._items if item.name.lower() == wanted]
        if len(named) > 1:
            raise AmbiguousName(named)
        return named[0] if named else None

    def total(self) -> int:
        """Every item here and every item inside those, at every depth."""
        return sum(1 + item.total_inside() for item in self._items)

    def count(self) -> int:
        return len(self._items)

    def contents(self) -> list[Item]:
        """A copy, so callers cannot reach the real list."""
        return list(self._items)