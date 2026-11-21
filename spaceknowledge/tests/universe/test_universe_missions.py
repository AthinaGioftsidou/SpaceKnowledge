"""Tests for the Universe's mission and answer actions."""

import unittest

from spaceknowledge.common.messages import Request
from spaceknowledge.tests.universe.galaxy import a_galaxy
from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.missions import Mission, MissionBook
from spaceknowledge.universe.universe import Universe
from spaceknowledge.universe.universe_repository import (
    CorruptStateError,
    InMemoryUniverseRepository,
    UniverseState,
)
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.door import Door
from spaceknowledge.world.world import World


def a_mission() -> Mission:
    return Mission(
        "ship", "Upgrade the ship", "iron", 5, "earth", "Mine iron.", "Which metal?",
        ("iron", "rust"), "think about it", "Well done.", "earth", "mars",
    )


def a_ship(repository: InMemoryUniverseRepository | None = None,
           place: bool = True) -> tuple[Universe, Door]:
    door = Door("gate", "launch gate", "mission:ship")
    universe = a_galaxy(
        door, repository, Deposits({"earth": {"iron": 100, "wood": 100}}), place,
        MissionBook([a_mission()]),
    )
    return universe, door


def mine(op: str, amount: int, resource: str = "iron", player: str = "ada") -> Request:
    return Request(op, "mine", player, resource, amount)


def mission(op: str = "q1", player: str = "ada") -> Request:
    return Request(op, "mission", player, "here")


def answer(op: str, text: str, player: str = "ada") -> Request:
    return Request(op, "answer", player, text)


def fly(op: str, target: str = "mars", player: str = "bob") -> Request:
    return Request(op, "fly", player, target)


def ready_for_the_question() -> tuple[Universe, Door]:
    universe, door = a_ship()
    universe.handle(mine("m1", 5))
    return universe, door


class TestTheMission(unittest.TestCase):
    def test_it_starts_collecting_and_says_how_much_is_needed(self) -> None:
        universe, _ = a_ship()
        info = universe.handle(mission()).items[0]
        self.assertEqual(("collecting", "Upgrade the ship"), (info.item_id, info.name))
        self.assertIn("Collected 0 of 5 iron.", info.description)
        self.assertIn("Mine iron.", info.description)

    def test_mining_here_counts_and_other_resources_do_not(self) -> None:
        universe, _ = a_ship()
        universe.handle(mine("m1", 3))
        universe.handle(mine("m2", 4, "wood"))
        self.assertIn("Collected 3 of 5 iron.", universe.handle(mission()).items[0].description)

    def test_everyones_mining_counts_towards_the_goal(self) -> None:
        universe, _ = a_ship()
        universe.handle(mine("m1", 3))
        universe.handle(mine("m2", 2, player="bob"))
        self.assertEqual("question", universe.handle(mission()).items[0].item_id)

    def test_enough_iron_turns_it_into_a_question(self) -> None:
        universe, _ = ready_for_the_question()
        info = universe.handle(mission()).items[0]
        self.assertEqual("question", info.item_id)
        self.assertIn("Which metal?", info.description)
        self.assertIn("answer", info.description)

    def test_a_refused_mine_counts_for_nothing(self) -> None:
        universe, _ = a_ship()
        universe.handle(mine("m1", 1000))
        self.assertIn("Collected 0 of 5", universe.handle(mission()).items[0].description)

    def test_asking_is_never_remembered(self) -> None:
        universe, _ = a_ship()
        before = universe.answer_count()
        universe.handle(mission("q1"))
        universe.handle(mission("q2"))
        self.assertEqual(before, universe.answer_count())

    def test_a_stranger_is_refused(self) -> None:
        universe, _ = ready_for_the_question()
        self.assertFalse(universe.handle(mission(player="eve")).ok)
        self.assertFalse(universe.handle(answer("a1", "iron", "eve")).ok)

    def test_a_galaxy_without_missions_says_so(self) -> None:
        refusal = a_galaxy().handle(mission()).refusal
        self.assertIn("no mission", refusal.describe())


class TestAnswering(unittest.TestCase):
    def test_before_the_goal_there_is_no_question_waiting(self) -> None:
        universe, _ = a_ship()
        refusal = universe.handle(answer("a1", "iron")).refusal
        self.assertIn("no question waiting", refusal.describe())

    def test_a_wrong_answer_gets_the_hint_and_the_gate_stays_shut(self) -> None:
        universe, door = ready_for_the_question()
        response = universe.handle(answer("a1", "copper"))
        self.assertFalse(response.ok)
        self.assertIn("think about it", response.refusal.describe())
        self.assertFalse(door.is_passable())
        self.assertFalse(universe.handle(fly("f1")).ok)

    def test_the_right_answer_completes_it_and_opens_the_way_for_everybody(self) -> None:
        universe, door = ready_for_the_question()
        response = universe.handle(answer("a1", "I think it is iron!"))
        self.assertTrue(response.ok)
        self.assertEqual(("complete", "Upgrade the ship", "Well done."),
                         (response.items[0].item_id, response.items[0].name,
                          response.items[0].description))
        self.assertTrue(door.is_passable())
        self.assertTrue(universe.handle(fly("f1", player="bob")).ok)
        self.assertEqual("mars", universe.location_of("bob"))

    def test_a_finished_mission_shows_its_success_text_and_takes_no_more_answers(self) -> None:
        universe, _ = ready_for_the_question()
        universe.handle(answer("a1", "iron"))
        self.assertEqual("Well done.", universe.handle(mission()).items[0].description)
        self.assertFalse(universe.handle(answer("a2", "iron")).ok)

    def test_a_repeated_op_id_gives_the_same_answer(self) -> None:
        universe, _ = ready_for_the_question()
        first = universe.handle(answer("a1", "iron"))
        self.assertIs(first, universe.handle(answer("a1", "iron")))


class TestRemembering(unittest.TestCase):
    def test_progress_survives_a_restart(self) -> None:
        repository = InMemoryUniverseRepository()
        universe, _ = a_ship(repository)
        universe.handle(mine("m1", 3))
        again, _ = a_ship(repository, place=False)
        self.assertIn("Collected 3 of 5 iron.", again.handle(mission()).items[0].description)

    def test_a_completed_mission_reopens_its_gate_after_a_restart(self) -> None:
        repository = InMemoryUniverseRepository()
        universe, _ = a_ship(repository)
        universe.handle(mine("m1", 5))
        universe.handle(answer("a1", "iron"))
        again, door = a_ship(repository, place=False)   # a fresh, locked door
        self.assertTrue(door.is_passable())
        self.assertTrue(again.handle(fly("f1")).ok)

    def test_saved_progress_for_an_unknown_mission_is_refused(self) -> None:
        repository = InMemoryUniverseRepository()
        repository.save(UniverseState({}, {}, {}, {}, {},
                                      {"nope": {"collected": 0, "complete": False}}))
        with self.assertRaises(CorruptStateError):
            a_ship(repository, place=False)


class TestTheMissionMustFitTheWorld(unittest.TestCase):
    def test_a_mission_whose_gate_does_not_exist_is_refused(self) -> None:
        world = World({"earth": Destination("earth", "Earth", "Home.")}, "earth")
        with self.assertRaises(ValueError):
            Universe(world, missions=MissionBook([a_mission()]))

    def test_a_gate_that_this_mission_cannot_open_is_refused(self) -> None:
        earth, mars = Destination("earth", "Earth", "Home."), Destination("mars", "Mars", "Red.")
        earth.add_exit("mars", mars, Door("gate", "gate", "some_key"))
        with self.assertRaises(ValueError):
            Universe(World({"earth": earth, "mars": mars}, "earth"),
                     missions=MissionBook([a_mission()]))

    def test_a_string_is_refused_where_missions_are_expected(self) -> None:
        world = World({"earth": Destination("earth", "Earth", "Home.")}, "earth")
        with self.assertRaisesRegex(TypeError, "must be"):
            Universe(world, missions="missions")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()