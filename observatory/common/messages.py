"""The two messages that cross between the Broker and the Universe."""

from observatory.common.refusal import Refusal
from dataclasses import dataclass


class Request:
    """What the Broker asks the Universe to do. Read-only once made."""

    def __init__(
        self, op_id: str, action: str, player_id: str, item_id: str, amount: int = 1
    ) -> None:
        if not op_id:
            raise ValueError("op_id must not be empty")
        if not action:
            raise ValueError("action must not be empty")
        if not player_id:
            raise ValueError("player_id must not be empty")
        if not item_id:
            raise ValueError("item_id must not be empty")
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise TypeError(f"amount must be an int, not {type(amount).__name__}")
        if amount < 1:
            raise ValueError("amount must be at least 1")
        self._op_id = op_id
        self._action = action
        self._player_id = player_id
        self._item_id = item_id
        self._amount = amount

    @property
    def op_id(self) -> str:
        return self._op_id

    @property
    def action(self) -> str:
        return self._action

    @property
    def player_id(self) -> str:
        return self._player_id

    @property
    def item_id(self) -> str:
        return self._item_id

    @property
    def amount(self) -> int:
        return self._amount

@dataclass(frozen=True)
class ItemInfo:
    """Plain data about one item, so objects never cross between the servers.
    Read-only."""

    item_id: str
    name: str
    description: str

    def __post_init__(self) -> None:
        for label, value in (("item_id", self.item_id), ("name", self.name),
                             ("description", self.description)):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{label} must not be empty")

class Response:
    """The Universe's answer: OK (with optional item data), or a Refusal."""

    def __init__(
        self, op_id: str, refusal: Refusal | None = None, items: tuple[ItemInfo, ...] = ()
    ) -> None:
        if not op_id:
            raise ValueError("op_id must not be empty")
        if refusal is not None and not isinstance(refusal, Refusal):
            raise TypeError(f"refusal must be a Refusal, not {type(refusal).__name__}")
        if not isinstance(items, tuple) or not all(isinstance(i, ItemInfo) for i in items):
            raise TypeError("items must be a tuple of ItemInfo")
        if refusal is not None and items:
            raise ValueError("a refusal carries no items")
        self._op_id = op_id
        self._refusal = refusal
        self._items = items

    @property
    def op_id(self) -> str:
        return self._op_id

    @property
    def ok(self) -> bool:
        return self._refusal is None

    @property
    def refusal(self) -> Refusal | None:
        return self._refusal

    @property
    def items(self) -> tuple[ItemInfo, ...]:
        return self._items