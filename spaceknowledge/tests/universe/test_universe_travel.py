"""Tests for the Universe's fly action."""

import unittest

from spaceknowledge.common.messages import Request
from spaceknowledge.tests.universe.galaxy import a_galaxy
from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.universe_repository import InMemoryUniverseRepository
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.door import Door
from spaceknowledge.world.world import World
from spaceknowledge.universe.universe import Universe


def fly(op_id: str, target: str, player: str = "ada") -> Request:
    return Request(op_id, "fly", player, target)


class TestFlying(unittest.TestCase):
    def test_a_player_flies_along_a_route_and_the_answer_names_the_place(self) -> None:
        universe = a_galaxy()
        response = universe.handle(fly("f1", "moon"))
        self.assertTrue(response.ok)
        self.assertEqual([("moon", "The Moon", "Grey and airless.")],
                         [(i.item_id, i.name, i.description) for i in response.items])
        self.assertEqual("moon", universe.location_of("ada"))

    def test_only_the_traveller_moves(self) -> None:
        universe = a_galaxy()
        universe.handle(fly("f1", "moon"))
        self.assertEqual("earth", universe.location_of("bob"))

    def test_the_way_back_works_and_the_case_typed_does_not_matter(self) -> None:
        universe = a_galaxy()
        universe.handle(fly("f1", "MARS"))
        self.assertEqual("mars", universe.location_of("ada"))
        self.assertTrue(universe.handle(fly("f2", "earth")).ok)
        self.assertEqual("earth", universe.location_of("ada"))

    def test_a_place_with_no_route_is_refused_and_the_refusal_lists_the_routes(self) -> None:
        universe = a_galaxy()
        response = universe.handle(fly("f1", "sun"))
        self.assertFalse(response.ok)
        text = response.refusal.describe()
        self.assertIn("no route to sun", text)
        self.assertIn("fly to one of: mars, moon", text)
        self.assertEqual("earth", universe.location_of("ada"))

    def test_a_route_that_does_not_exist_from_here_is_refused(self) -> None:
        universe = a_galaxy()
        universe.handle(fly("f1", "moon"))
        self.assertFalse(universe.handle(fly("f2", "mars")).ok)   # the Moon only leads home
        self.assertEqual("moon", universe.location_of("ada"))

    def test_a_destination_with_no_routes_says_so(self) -> None:
        void = Destination("void", "The Void", "Nothing here.")
        universe = Universe(World({"void": void}, "void"))
        universe.place_player("ada", "void")
        refusal = universe.handle(fly("f1", "earth")).refusal
        self.assertIn("no routes", refusal.describe())

    def test_a_stranger_is_refused(self) -> None:
        self.assertFalse(a_galaxy().handle(fly("f1", "moon", "eve")).ok)


class TestDoors(unittest.TestCase):
    def test_a_locked_door_refuses_and_nobody_moves(self) -> None:
        universe = a_galaxy(Door("hatch", "hatch", "brass_key"))
        response = universe.handle(fly("f1", "mars"))
        self.assertFalse(response.ok)
        self.assertIn("locked", response.refusal.describe())
        self.assertEqual("earth", universe.location_of("ada"))

    def test_the_same_route_works_once_the_door_is_open(self) -> None:
        door = Door("hatch", "hatch", "brass_key")
        universe = a_galaxy(door)
        universe.handle(fly("f1", "mars"))
        door.unlock("brass_key")
        self.assertTrue(universe.handle(fly("f2", "mars")).ok)
        self.assertEqual("mars", universe.location_of("ada"))

    def test_a_broken_door_stays_shut(self) -> None:
        door = Door("hatch", "hatch", "brass_key")
        door.force()
        self.assertFalse(a_galaxy(door).handle(fly("f1", "mars")).ok)


class TestRemembering(unittest.TestCase):
    def test_a_repeated_op_id_gets_the_same_answer_and_does_not_fly_twice(self) -> None:
        universe = a_galaxy()
        first = universe.handle(fly("f1", "moon"))
        universe.handle(fly("f2", "earth"))
        self.assertIs(first, universe.handle(fly("f1", "moon")))
        self.assertEqual("earth", universe.location_of("ada"))

    def test_the_place_survives_a_restart(self) -> None:
        repository = InMemoryUniverseRepository()
        a_galaxy(repository=repository).handle(fly("f1", "moon"))
        again = a_galaxy(repository=repository, place=False)
        self.assertEqual("moon", again.location_of("ada"))
        self.assertEqual("earth", again.location_of("bob"))


class TestPlacesDiffer(unittest.TestCase):
    def test_mining_depends_on_where_the_player_is(self) -> None:
        deposits = Deposits({"earth": {"iron": 5}, "mars": {"nickel": 5}})
        universe = a_galaxy(deposits=deposits)
        mine = Request("m1", "mine", "ada", "nickel", 2)
        self.assertFalse(universe.handle(mine).ok)
        universe.handle(fly("f1", "mars"))
        self.assertTrue(universe.handle(Request("m2", "mine", "ada", "nickel", 2)).ok)
        self.assertEqual(3, deposits.available("mars", "nickel"))

    def test_an_item_stays_where_it_was_dropped(self) -> None:
        universe = a_galaxy()
        universe.handle(Request("d1", "add_item", "ada", "torch-1", name="torch"))
        universe.handle(fly("f1", "moon"))
        self.assertEqual((), universe.handle(Request("l1", "look", "ada", "here")).items)
        universe.handle(fly("f2", "earth"))
        self.assertEqual(1, len(universe.handle(Request("l2", "look", "ada", "here")).items))


if __name__ == "__main__":
    unittest.main()