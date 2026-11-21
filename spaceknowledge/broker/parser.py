"""Turning what a player typed into a Command."""

from spaceknowledge.broker.command import (
    AnswerCommand,
    Command,
    DropCommand,
    FlyCommand,
    InventoryCommand,
    LookCommand,
    MineCommand,
    MissionCommand,
    PickCommand,
    WhereCommand,
)


class ParseError(Exception):
    """The player typed something this game has no verb for."""


# One row per verb. Adding a verb is one row, not an edit to a branch.
_NO_ARGUMENT = {
    "inventory": InventoryCommand,
    "i": InventoryCommand,
    "look": LookCommand,
    "l": LookCommand,
    "where": WhereCommand,
    "mission": MissionCommand,
}

_ONE_ARGUMENT = {
    "drop": DropCommand,
    "pick": PickCommand,
    "take": PickCommand,
    "get": PickCommand,
    "fly": FlyCommand,
    "go": FlyCommand,
    "travel": FlyCommand,
    "answer": AnswerCommand,
}

# A word that may sit between the verb and what it is about:
# "pick UP the torch", "fly TO mars".
_FILLER = {"pick": "up", "fly": "to", "go": "to", "travel": "to"}

# What the verb is about, for the message when it is missing. Default: "item".
_NOUNS = {"fly": "destination", "go": "destination", "travel": "destination", "answer": "answer"}

# A name, then an optional whole number: "mine iron 3".
_WITH_AMOUNT = {
    "mine": MineCommand,
}

_ARTICLES = ("the ", "a ", "an ")


class Parser:
    """The vocabulary lives here. What each verb means lives in the Commands."""

    def parse(self, line: str) -> Command:
        words = line.strip().lower().split()
        if not words:
            raise ParseError("nothing was typed")
        verb, rest = words[0], words[1:]
        if verb in _NO_ARGUMENT:
            if rest:
                raise ParseError(f"'{verb}' does not take anything after it")
            return _NO_ARGUMENT[verb]()
        if verb in _ONE_ARGUMENT:
            if rest[:1] == [_FILLER.get(verb)]:
                rest = rest[1:]
            return _ONE_ARGUMENT[verb](self._name(verb, rest, _NOUNS.get(verb, "item")))
        if verb in _WITH_AMOUNT:
            return self._parse_with_amount(verb, rest)
        raise ParseError(f"there is no verb called '{verb}'")

    def verbs(self) -> list[str]:
        """Every word the parser accepts, so help cannot drift from it."""
        return sorted(set(_NO_ARGUMENT) | set(_ONE_ARGUMENT) | set(_WITH_AMOUNT))

    def _parse_with_amount(self, verb: str, words: list[str]) -> Command:
        amount = 1
        if words and words[-1].isdecimal():
            amount = int(words[-1])
            words = words[:-1]
        name = self._name(verb, words, "resource")
        if amount < 1:
            raise ParseError("the amount must be at least 1")
        return _WITH_AMOUNT[verb](name, amount)

    @staticmethod
    def _name(verb: str, words: list[str], noun: str) -> str:
        """The words joined into one name, with a leading article removed."""
        text = " ".join(words)
        if not text:
            raise ParseError(f"'{verb}' needs to know which {noun}")
        for article in _ARTICLES:
            if text.startswith(article):
                return text[len(article):]
        return text