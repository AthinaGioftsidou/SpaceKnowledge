"""The quantities of each resource one player holds."""


class ResourceBag:
    """resource name -> how many the player has. Never stores zero."""

    def __init__(self) -> None:
        self._amounts: dict[str, int] = {}

    def add(self, resource: str, amount: int) -> None:
        if not resource:
            raise ValueError("resource must not be empty")
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise TypeError(f"amount must be an int, not {type(amount).__name__}")
        if amount < 1:
            raise ValueError("amount must be at least 1")
        self._amounts[resource] = self._amounts.get(resource, 0) + amount

    def amount_of(self, resource: str) -> int:
        return self._amounts.get(resource, 0)

    def is_empty(self) -> bool:
        return len(self._amounts) == 0

    def snapshot(self) -> dict[str, int]:
        """A copy, for saving and for showing."""
        return dict(self._amounts)