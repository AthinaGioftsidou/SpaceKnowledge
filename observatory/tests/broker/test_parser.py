"""Tests for Parser, which turns typed text into a Command."""

import unittest

from observatory.broker.command import DropCommand, InventoryCommand
from observatory.broker.parser import ParseError, Parser


class TestParsingVerbs(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = Parser()

    def test_inventory_and_its_abbreviation(self) -> None:
        self.assertIsInstance(self.parser.parse("inventory"), InventoryCommand)
        self.assertIsInstance(self.parser.parse("i"), InventoryCommand)

    def test_drop(self) -> None:
        self.assertIsInstance(self.parser.parse("drop torch"), DropCommand)

    def test_case_and_padding_do_not_matter(self) -> None:
        self.assertIsInstance(self.parser.parse("  DROP Torch  "), DropCommand)

    def test_articles_are_ignored(self) -> None:
        self.assertEqual(
            type(self.parser.parse("drop the torch")), type(self.parser.parse("drop torch"))
        )


class TestParsingRefusals(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = Parser()

    def test_nothing_at_all(self) -> None:
        with self.assertRaises(ParseError):
            self.parser.parse("   ")

    def test_an_unknown_verb(self) -> None:
        with self.assertRaises(ParseError):
            self.parser.parse("juggle torch")

    def test_a_verb_that_needs_an_argument_and_has_none(self) -> None:
        with self.assertRaises(ParseError):
            self.parser.parse("drop")

    def test_a_verb_that_takes_no_argument_and_was_given_one(self) -> None:
        with self.assertRaises(ParseError):
            self.parser.parse("inventory please")


class TestHelpCannotDrift(unittest.TestCase):
    def test_verbs_lists_everything_the_parser_accepts(self) -> None:
        verbs = Parser().verbs()
        for word in ("drop", "inventory", "i"):
            self.assertIn(word, verbs)


if __name__ == "__main__":
    unittest.main()