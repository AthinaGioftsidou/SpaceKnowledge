"""Tests for Parser, which turns typed text into a Command."""

import unittest

from spaceknowledge.broker.command import DropCommand, InventoryCommand, LookCommand, PickCommand
from spaceknowledge.broker.parser import ParseError, Parser
from spaceknowledge.broker.command import DropCommand, InventoryCommand, MineCommand


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

class TestParsingMine(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = Parser()

    def test_mine_with_an_amount(self) -> None:
        command = self.parser.parse("mine iron 3")
        self.assertIsInstance(command, MineCommand)
        self.assertEqual("iron", command.resource)
        self.assertEqual(3, command.amount)

    def test_the_amount_defaults_to_one(self) -> None:
        self.assertEqual(1, self.parser.parse("mine iron").amount)

    def test_articles_are_ignored(self) -> None:
        self.assertEqual("iron", self.parser.parse("mine the iron 2").resource)

    def test_a_resource_name_may_have_two_words(self) -> None:
        command = self.parser.parse("mine heavy water 4")
        self.assertEqual("heavy water", command.resource)
        self.assertEqual(4, command.amount)

    def test_mine_with_nothing_after_it_is_refused(self) -> None:
        with self.assertRaises(ParseError):
            self.parser.parse("mine")

    def test_an_amount_with_no_resource_is_refused(self) -> None:
        with self.assertRaises(ParseError):
            self.parser.parse("mine 3")

    def test_an_amount_of_zero_is_refused(self) -> None:
        with self.assertRaises(ParseError):
            self.parser.parse("mine iron 0")

    def test_mine_is_listed_in_the_verbs(self) -> None:
        self.assertIn("mine", self.parser.verbs())

class TestParsingLookAndPick(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = Parser()

    def test_look_and_its_abbreviation(self) -> None:
        self.assertIsInstance(self.parser.parse("look"), LookCommand)
        self.assertIsInstance(self.parser.parse("l"), LookCommand)

    def test_pick_in_its_forms(self) -> None:
        for line in ("pick torch", "pick up torch", "pick up the torch", "take torch", "get torch"):
            with self.subTest(line=line):
                command = self.parser.parse(line)
                self.assertIsInstance(command, PickCommand)
                self.assertEqual("torch", command.target)

    def test_pick_with_nothing_after_it_is_refused(self) -> None:
        for line in ("pick", "pick up"):
            with self.subTest(line=line):
                with self.assertRaises(ParseError):
                    self.parser.parse(line)

    def test_look_with_something_after_it_is_refused(self) -> None:
        with self.assertRaises(ParseError):
            self.parser.parse("look at the torch")


if __name__ == "__main__":
    unittest.main()