"""Tests for Broker.fly, FlyCommand and the parser's travel words."""

import unittest

from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.command import FlyCommand
from spaceknowledge.broker.inventory_repository import InMemoryInventoryRepository
from spaceknowledge.broker.parser import ParseError, Parser
from spaceknowledge.common.messages import ItemInfo, Request, Response
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.tests.universe.galaxy import a_galaxy
from spaceknowledge.transport.channel import InMemoryChannel, UniverseChannel
from spaceknowledge.universe.universe import Universe


class SwitchChannel(UniverseChannel):
    """Can be made to lose requests, or to lose the answer after the Universe acted."""

    def __init__(self, inner: UniverseChannel) -> None:
        self._inner = inner
        self.down = False
        self.lose_answers = False

    def send(self, request: Request) -> Response:
        if self.down:
            raise ConnectionError("lost")
        response = self._inner.send(request)
        if self.lose_answers and request.action == "fly":
            raise ConnectionError("answer lost")
        return response


def a_broker() -> tuple[Broker, Universe]:
    universe = a_galaxy(place=False)
    broker = Broker(InMemoryChannel(universe))
    broker.join("ada", "earth")
    return broker, universe


class TestFly(unittest.TestCase):
    def test_it_returns_the_place_arrived_at(self) -> None:
        broker, universe = a_broker()
        arrived = broker.fly("ada", "moon")
        self.assertIsInstance(arrived, ItemInfo)
        self.assertEqual(("The Moon", "Grey and airless."), (arrived.name, arrived.description))
        self.assertEqual(("moon", "The Moon"), broker.where("ada"))
        self.assertEqual("moon", universe.location_of("ada"))

    def test_spaces_and_capitals_in_the_target_do_not_matter(self) -> None:
        broker, _ = a_broker()
        self.assertEqual("Mars", broker.fly("ada", "  Mars ").name)

    def test_a_refusal_changes_nothing_and_leaves_nothing_pending(self) -> None:
        broker, universe = a_broker()
        self.assertIsInstance(broker.fly("ada", "sun"), Refusal)
        self.assertEqual("earth", universe.location_of("ada"))
        self.assertEqual(0, broker.pending_count())

    def test_an_empty_target_or_a_stranger_is_refused(self) -> None:
        broker, _ = a_broker()
        self.assertIsInstance(broker.fly("ada", "   "), Refusal)
        self.assertIsInstance(broker.fly("eve", "moon"), Refusal)


class TestFlyAcrossACrash(unittest.TestCase):
    def setUp(self) -> None:
        self.universe = a_galaxy(place=False)
        self.repository = InMemoryInventoryRepository()
        self.channel = SwitchChannel(InMemoryChannel(self.universe))
        self.broker = Broker(self.channel, self.repository)
        self.broker.join("ada", "earth")

    def test_a_flight_whose_request_was_lost_is_finished_by_recovery(self) -> None:
        self.channel.down = True
        with self.assertRaises(ConnectionError):
            self.broker.fly("ada", "moon")
        self.assertEqual(1, self.broker.pending_count())
        self.assertEqual("earth", self.universe.location_of("ada"))
        self.channel.down = False
        self.assertEqual(1, self.broker.recover())
        self.assertEqual("moon", self.universe.location_of("ada"))
        self.assertEqual(0, self.broker.pending_count())

    def test_a_flight_whose_answer_was_lost_is_finished_after_a_restart_without_flying_twice(self) -> None:
        self.channel.lose_answers = True
        with self.assertRaises(ConnectionError):
            self.broker.fly("ada", "moon")
        self.assertEqual("moon", self.universe.location_of("ada"))   # the Universe already did it
        again = Broker(InMemoryChannel(self.universe), self.repository)
        self.assertEqual(1, again.pending_count())
        self.assertEqual(1, again.recover())
        self.assertEqual("moon", self.universe.location_of("ada"))


class TestTheCommand(unittest.TestCase):
    def test_the_reply_names_the_place_and_describes_it(self) -> None:
        broker, _ = a_broker()
        self.assertEqual("You fly to The Moon.\nGrey and airless.",
                         FlyCommand("moon").execute(broker, "ada"))

    def test_a_refusal_is_described_with_the_routes(self) -> None:
        broker, _ = a_broker()
        text = FlyCommand("sun").execute(broker, "ada")
        self.assertIn("fly to one of: mars, moon", text)

    def test_bad_arguments_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            FlyCommand("")
        with self.assertRaisesRegex(TypeError, "must be"):
            FlyCommand("moon").execute("broker", "ada")  # type: ignore[arg-type]


class TestTheParser(unittest.TestCase):
    def test_every_way_of_saying_it(self) -> None:
        for line in ("fly mars", "fly to mars", "fly to the mars", "go mars", "travel to mars",
                     "  FLY   To  Mars "):
            with self.subTest(line=line):
                command = Parser().parse(line)
                self.assertIsInstance(command, FlyCommand)
                self.assertEqual("mars", command.target)

    def test_a_name_with_an_article_loses_the_article(self) -> None:
        self.assertEqual("moon", Parser().parse("fly to the moon").target)

    def test_no_destination_is_refused_and_says_what_is_missing(self) -> None:
        for line in ("fly", "fly to", "go", "travel to"):
            with self.subTest(line=line):
                with self.assertRaises(ParseError) as caught:
                    Parser().parse(line)
                self.assertIn("destination", str(caught.exception))

    def test_help_lists_the_travel_words(self) -> None:
        for word in ("fly", "go", "travel"):
            self.assertIn(word, Parser().verbs())

    def test_the_other_verbs_still_work(self) -> None:
        for line in ("pick up the torch", "drop torch", "mine iron 3", "where", "look"):
            with self.subTest(line=line):
                Parser().parse(line)


if __name__ == "__main__":
    unittest.main()