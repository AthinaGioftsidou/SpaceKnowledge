"""COMMAND. A verb turned into an object that the Broker can run."""

from abc import ABC, abstractmethod

from spaceknowledge.broker.broker import Broker
from spaceknowledge.common.refusal import Refusal


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
            entries = broker.inventory_of(player_id).entries()
            resources = broker.resources_of(player_id).snapshot()
        except KeyError:
            return Refusal(
                "show the inventory",
                f"the Broker does not know a player called {player_id}",
                "log in, then try again",
            ).describe()
        lines = []
        if entries:
            lines.append("You are carrying: " + ", ".join(entry.name for entry in entries))
        if resources:
            parts = [f"{name} {amount}" for name, amount in sorted(resources.items())]
            lines.append("Resources: " + ", ".join(parts))
        if not lines:
            return "You are carrying nothing."
        return "\n".join(lines)


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


class MineCommand(Command):
    def __init__(self, resource: str, amount: int = 1) -> None:
        if not resource:
            raise ValueError("resource must not be empty")
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise TypeError(f"amount must be an int, not {type(amount).__name__}")
        if amount < 1:
            raise ValueError("amount must be at least 1")
        self._resource = resource
        self._amount = amount

    @property
    def resource(self) -> str:
        return self._resource

    @property
    def amount(self) -> int:
        return self._amount

    def execute(self, broker: Broker, player_id: str) -> str:
        if not isinstance(broker, Broker):
            raise TypeError(f"broker must be a Broker, not {type(broker).__name__}")
        refusal = broker.mine(player_id, self._resource, self._amount)
        if refusal is not None:
            return refusal.describe()
        return f"You mine {self._amount} {self._resource}."


class LookCommand(Command):
    def execute(self, broker: Broker, player_id: str) -> str:
        if not isinstance(broker, Broker):
            raise TypeError(f"broker must be a Broker, not {type(broker).__name__}")
        result = broker.look(player_id)
        if isinstance(result, Refusal):
            return result.describe()
        if not result:
            return "Nothing lies on the ground here."
        return "On the ground here: " + ", ".join(proxy.name for proxy in result)


class PickCommand(Command):
    def __init__(self, target: str) -> None:
        if not target:
            raise ValueError("target must not be empty")
        self._target = target

    @property
    def target(self) -> str:
        return self._target

    def execute(self, broker: Broker, player_id: str) -> str:
        if not isinstance(broker, Broker):
            raise TypeError(f"broker must be a Broker, not {type(broker).__name__}")
        refusal = broker.pick(player_id, self._target)
        if refusal is not None:
            return refusal.describe()
        return f"You pick up the {self._target}."

class WhereCommand(Command):
    def execute(self, broker: Broker, player_id: str) -> str:
        if not isinstance(broker, Broker):
            raise TypeError(f"broker must be a Broker, not {type(broker).__name__}")
        result = broker.where(player_id)
        if isinstance(result, Refusal):
            return result.describe()
        return f"You are at {result[1]}."

class FlyCommand(Command):
    def __init__(self, target: str) -> None:
        if not target:
            raise ValueError("target must not be empty")
        self._target = target

    @property
    def target(self) -> str:
        return self._target

    def execute(self, broker: Broker, player_id: str) -> str:
        if not isinstance(broker, Broker):
            raise TypeError(f"broker must be a Broker, not {type(broker).__name__}")
        result = broker.fly(player_id, self._target)
        if isinstance(result, Refusal):
            return result.describe()
        if result.description == result.name:
            return f"You fly to {result.name}."
        return f"You fly to {result.name}.\n{result.description}"

class MissionCommand(Command):
    def execute(self, broker: Broker, player_id: str) -> str:
        if not isinstance(broker, Broker):
            raise TypeError(f"broker must be a Broker, not {type(broker).__name__}")
        result = broker.mission(player_id)
        if isinstance(result, Refusal):
            return result.describe()
        return f"Mission: {result.name} ({result.item_id})\n{result.description}"


class AnswerCommand(Command):
    def __init__(self, target: str) -> None:
        if not target:
            raise ValueError("target must not be empty")
        self._target = target

    @property
    def target(self) -> str:
        return self._target

    def execute(self, broker: Broker, player_id: str) -> str:
        if not isinstance(broker, Broker):
            raise TypeError(f"broker must be a Broker, not {type(broker).__name__}")
        result = broker.answer(player_id, self._target)
        if isinstance(result, Refusal):
            return result.describe()
        return f"Correct! You have completed {result.name}.\n{result.description}"