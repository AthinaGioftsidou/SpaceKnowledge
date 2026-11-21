"""Tests for Broker.mission, Broker.answer, their commands and the parser."""

import unittest

from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.command import AnswerCommand, MissionCommand
from spaceknowledge.broker.inventory_repository import InMemoryInventoryRepository
from spaceknowledge.broker.parser import ParseError, Parser
from spaceknowledge.common.messages import ItemInfo, Request, Response
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.tests.universe.test_universe_missions import a_ship
from spaceknowledge.transport.channel import InMemoryChannel, UniverseChannel


class SwitchChannel(UniverseChannel):
    """Can lose the answer to an `answer` after the Universe has acted."""

    def __init__(self, inner: UniverseChannel) -> None:
        self._inner = inner
        self.lose_answers = False

    def send(self, request: Request) -> Response:
        response = self._inner.send(request)
        if self.lose_answers and request.action == "answer":
            raise ConnectionError("answer lost")
        return response


def a_broker() -> tuple[Broker, object]:
    universe, door = a_ship(place=False)
    broker = Broker(InMemoryChannel(universe))
    broker.join("ada", "earth")
    broker.join("bob", "earth")
    return broker, door


class TestTheMissionThroughTheBroker(unittest.TestCase):
    def test_the_whole_mission_from_collecting_to_flying(self) -> None:
        broker, door = a_broker()
        self.assertEqual("collecting", broker.mission("ada").item_id)
        self.assertIsNone(broker.mine("ada", "iron", 5))
        self.assertEqual("question", broker.mission("bob").item_id)
        self.assertIsInstance(broker.answer("ada", "copper"), Refusal)
        done = broker.answer("ada", "iron")
        self.assertIsInstance(done, ItemInfo)
        self.assertEqual("complete", done.item_id)
        self.assertTrue(door.is_passable())
        self.assertIsInstance(broker.fly("bob", "mars"), ItemInfo)

    def test_nothing_is_left_pending_after_asking_or_answering(self) -> None:
        broker, _ = a_broker()
        broker.mission("ada")
        broker.answer("ada", "iron")
        self.assertEqual(0, broker.pending_count())

    def test_a_stranger_and_an_empty_answer_are_refused(self) -> None:
        broker, _ = a_broker()
        self.assertIsInstance(broker.mission("eve"), Refusal)
        self.assertIsInstance(broker.answer("eve", "iron"), Refusal)
        self.assertIsInstance(broker.answer("ada", "   "), Refusal)


class TestAnAnswerAcrossACrash(unittest.TestCase):
    def test_an_answer_whose_reply_was_lost_is_finished_by_recovery(self) -> None:
        universe, door = a_ship(place=False)
        repository = InMemoryInventoryRepository()
        channel = SwitchChannel(InMemoryChannel(universe))
        broker = Broker(channel, repository)
        broker.join("ada", "earth")
        broker.mine("ada", "iron", 5)
        channel.lose_answers = True
        with self.assertRaises(ConnectionError):
            broker.answer("ada", "iron")
        self.assertTrue(door.is_passable())          # the Universe already did it
        self.assertEqual(1, broker.pending_count())

        again = Broker(InMemoryChannel(universe), repository)
        self.assertEqual(1, again.recover())
        self.assertEqual(0, again.pending_count())
        self.assertEqual("complete", again.mission("ada").item_id)


class TestTheCommands(unittest.TestCase):
    def test_the_mission_command_shows_title_status_and_text(self) -> None:
        broker, _ = a_broker()
        self.assertEqual(
            "Mission: Upgrade the ship (collecting)\nCollected 0 of 5 iron.\nMine iron.",
            MissionCommand().execute(broker, "ada"))

    def test_the_answer_command_explains_a_wrong_answer_and_celebrates_the_right_one(self) -> None:
        broker, _ = a_broker()
        broker.mine("ada", "iron", 5)
        wrong = AnswerCommand("copper").execute(broker, "ada")
        self.assertIn("Why:", wrong)
        self.assertIn("think about it", wrong)
        right = AnswerCommand("iron").execute(broker, "ada")
        self.assertEqual("Correct! You have completed Upgrade the ship.\nWell done.", right)

    def test_bad_arguments_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            AnswerCommand("")
        for command in (MissionCommand(), AnswerCommand("iron")):
            with self.assertRaisesRegex(TypeError, "must be"):
                command.execute("broker", "ada")  # type: ignore[arg-type]


class TestTheParser(unittest.TestCase):
    def test_mission_and_answer(self) -> None:
        self.assertIsInstance(Parser().parse("mission"), MissionCommand)
        command = Parser().parse("answer the Iron oxide")
        self.assertIsInstance(command, AnswerCommand)
        self.assertEqual("iron oxide", command.target)

    def test_missing_pieces_are_refused(self) -> None:
        for line in ("answer", "mission now"):
            with self.subTest(line=line):
                with self.assertRaises(ParseError):
                    Parser().parse(line)

    def test_help_lists_them(self) -> None:
        for word in ("mission", "answer"):
            self.assertIn(word, Parser().verbs())


if __name__ == "__main__":
    unittest.main()