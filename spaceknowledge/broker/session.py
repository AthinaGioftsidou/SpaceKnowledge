"""One player's conversation with the Broker: text in, text out."""

from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.parser import ParseError, Parser
from spaceknowledge.common.refusal import Refusal


class Session:
    """The only thing a client needs: `submit(line)` returns the reply.

    A console client and a Tkinter window can both use it unchanged.
    """

    def __init__(self, broker: Broker, parser: Parser, player_id: str) -> None:
        if not isinstance(broker, Broker):
            raise TypeError(f"broker must be a Broker, not {type(broker).__name__}")
        if not isinstance(parser, Parser):
            raise TypeError(f"parser must be a Parser, not {type(parser).__name__}")
        if not player_id:
            raise ValueError("player_id must not be empty")
        self._broker = broker
        self._parser = parser
        self._player_id = player_id

    def submit(self, line: str) -> str:
        if line.strip().lower() == "help":
            return "You can: " + ", ".join(self._parser.verbs() + ["help"])
        try:
            command = self._parser.parse(line)
        except ParseError as problem:
            return Refusal(
                line.strip() or "an empty line",
                str(problem),
                "type help to see what you can do",
            ).describe()
        return command.execute(self._broker, self._player_id)