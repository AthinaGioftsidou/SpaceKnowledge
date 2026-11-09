"""Turning what a player typed into a Command."""

from observatory.broker.command import Command, DropCommand, InventoryCommand


class ParseError(Exception):
    """The player typed something this game has no verb for."""


# One row per verb. Adding a verb is one row, not an edit to a branch.
_NO_ARGUMENT = {
    "inventory": InventoryCommand,
    "i": InventoryCommand,
}

_ONE_ARGUMENT = {
    "drop": DropCommand,
}

_ARTICLES = ("the ", "a ", "an ")


class Parser:
    """The vocabulary lives here. What each verb means lives in the Commands."""

    def parse(self, line: str) -> Command:
        words = line.strip().lower().split()
        if not words:
            raise ParseError("nothing was typed")
        verb, rest = words[0], " ".join(words[1:])
        if verb in _NO_ARGUMENT:
            if rest:
                raise ParseError(f"'{verb}' does not take anything after it")
            return _NO_ARGUMENT[verb]()
        if verb in _ONE_ARGUMENT:
            if not rest:
                raise ParseError(f"'{verb}' needs to know which item")
            for article in _ARTICLES:
                if rest.startswith(article):
                    rest = rest[len(article):]
                    break
            return _ONE_ARGUMENT[verb](rest)
        raise ParseError(f"there is no verb called '{verb}'")

    def verbs(self) -> list[str]:
        """Every word the parser accepts, so help cannot drift from it."""
        return sorted(set(_NO_ARGUMENT) | set(_ONE_ARGUMENT))