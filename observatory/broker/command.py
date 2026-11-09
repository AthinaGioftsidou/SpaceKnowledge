"""COMMAND. A verb turned into an object that the Broker can run."""

from abc import ABC, abstractmethod

from observatory.broker.broker import Broker
from observatory.common.refusal import Refusal


class Command(ABC):
    """Something a player asked for. Executing returns the text they see."""

    @abstractmethod
    def execute(self, broker: Broker, player_id: str) -> str:
        """Carry it out and return the reply."""


class InventoryCommand(Command):
    def execute(self, broker: Broker, player_id: str) -> str:
        if not isinstance(broker, Broker):
            raise TypeError(f"broker must be a Broker, not {type(broker).__name__}")
        try:
            inventory = broker.inventory_of(player_id)
        except KeyError:
            return Refusal(
                "show the inventory",
                f"the Broker does not know a player called {player_id}",
                "log in, then try again",
            ).describe()
        entries = inventory.entries()
        if len(entries) == 0:
            return "You are carrying nothing."
        names = []
        for entry in entries:
            names.append(entry.name)
        return "You are carrying: " + ", ".join(names)


class DropCommand(Command):
    def __init__(self, target: str) -> None:
        if not target:
            raise ValueError("target must not be empty")
        self._target = target

    def execute(self, broker: Broker, player_id: str) -> str:
        if not isinstance(broker, Broker):
            raise TypeError(f"broker must be a Broker, not {type(broker).__name__}")
        refusal = broker.drop(player_id, self._target)
        if refusal is not None:
            return refusal.describe()
        return f"You drop the {self._target}."