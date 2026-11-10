"""Resources lying in each destination, and how much of each is left."""

from typing import Any

Stock = dict[str, dict[str, int]]


class Deposits:
    """destination id -> resource name -> quantity left.

    Knows nothing about players or requests. The Universe decides whether a
    request is allowed, then calls `remove`.
    """

    def __init__(self, stock: Stock) -> None:
        self._stock: Stock = {}
        for room_id, resources in stock.items():
            if not room_id:
                raise ValueError("destination id must not be empty")
            self._stock[room_id] = {}
            for resource, quantity in resources.items():
                self._check(resource, quantity)
                self._stock[room_id][resource] = quantity

    @staticmethod
    def _check(resource: str, quantity: Any) -> None:
        if not resource:
            raise ValueError("resource name must not be empty")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise ValueError(f"quantity of {resource} must be a whole number, 0 or more")

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "Deposits":
        """Read the optional "resources" of each room in a world file."""
        stock: dict[str, Any] = {}
        for spec in raw.get("rooms", []):
            resources = spec.get("resources")
            if resources is None:
                continue
            if not isinstance(resources, dict):
                raise ValueError(f"resources of {spec['id']} must be an object")
            stock[spec["id"]] = resources
        return cls(stock)

    def available(self, room_id: str, resource: str) -> int:
        return self._stock.get(room_id, {}).get(resource, 0)

    def remove(self, room_id: str, resource: str, amount: int) -> None:
        if amount < 1:
            raise ValueError("amount must be at least 1")
        left = self.available(room_id, resource)
        if amount > left:
            raise ValueError(f"only {left} {resource} left in {room_id}")
        self._stock[room_id][resource] = left - amount

    def snapshot(self) -> Stock:
        """A copy of everything, for saving later."""
        return {room_id: dict(resources) for room_id, resources in self._stock.items()}