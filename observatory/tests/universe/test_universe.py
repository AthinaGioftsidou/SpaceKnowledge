"""Tests for Universe, which owns the world and answers the Broker."""

import unittest

from observatory.common.messages import Request, Response
from observatory.universe.universe import Universe
from observatory.world.room import Room
from observatory.world.world import World
from observatory.universe.deposits import Deposits
from observatory.universe.universe_repository import InMemoryUniverseRepository
from observatory.world.container import Container


def a_universe() -> tuple[Universe, Room]:
    hall = Room("hall", "Hall", "Cold and tiled.")
    universe = Universe(World({"hall": hall}, "hall"))
    universe.place_player("ada", "hall")
    return universe, hall


def add_torch(op_id: str = "op1", player_id: str = "ada") -> Request:
    return Request(op_id, "add_item", player_id, "torch")


class TestPlacingPlayers(unittest.TestCase):
    def test_a_room_that_does_not_exist_is_refused(self) -> None:
        universe, _ = a_universe()
        with self.assertRaises(ValueError):
            universe.place_player("ada", "nowhere")

    def test_an_empty_player_id_is_refused(self) -> None:
        universe, _ = a_universe()
        with self.assertRaises(ValueError):
            universe.place_player("", "hall")


class TestAddItem(unittest.TestCase):
    def test_the_item_appears_in_the_players_room(self) -> None:
        universe, hall = a_universe()
        response = universe.handle(add_torch())
        self.assertTrue(response.ok)
        self.assertIsNotNone(hall.find_item("torch"))

    def test_a_player_who_is_nowhere_is_refused_and_nothing_is_added(self) -> None:
        universe, hall = a_universe()
        response = universe.handle(add_torch(player_id="bob"))
        self.assertFalse(response.ok)
        self.assertIn("bob", response.refusal.describe())
        self.assertEqual(0, hall.item_count())

    def test_an_item_already_in_the_room_is_refused(self) -> None:
        universe, hall = a_universe()
        universe.handle(add_torch("op1"))
        response = universe.handle(add_torch("op2"))
        self.assertFalse(response.ok)
        self.assertEqual(1, hall.item_count())

    def test_an_unknown_action_is_refused(self) -> None:
        universe, _ = a_universe()
        response = universe.handle(Request("op1", "teleport", "ada", "torch"))
        self.assertFalse(response.ok)
        self.assertIn("teleport", response.refusal.describe())


class TestTheSameRequestTwice(unittest.TestCase):
    def test_a_repeated_op_id_gets_the_same_answer_and_changes_nothing(self) -> None:
        # The Broker may re-send after a crash. Doing it twice would be a bug.
        universe, hall = a_universe()
        first = universe.handle(add_torch("op1"))
        second = universe.handle(add_torch("op1"))
        self.assertIs(first, second)
        self.assertTrue(second.ok)
        self.assertEqual(1, hall.item_count())


class TestArgumentTypes(unittest.TestCase):
    def test_a_string_is_refused_where_a_class_is_expected(self) -> None:
        universe, _ = a_universe()
        bad = "not an object"
        calls = [
            ("Universe world", lambda: Universe(bad)),
            ("handle request", lambda: universe.handle(bad)),
        ]
        for label, call in calls:
            with self.subTest(label):
                with self.assertRaisesRegex(TypeError, "must be"):
                    call()

from pathlib import Path

from observatory.world.loader import StandardWorldLoader


SPACE_FILE = Path(__file__).resolve().parents[3] / "data" / "space.json"


class TestTheUniverseOnTheSpaceWorld(unittest.TestCase):
    def setUp(self) -> None:
        world = StandardWorldLoader().load(SPACE_FILE)
        self.universe = Universe(world)
        self.earth = world.room("earth")
        self.universe.place_player("ada", "earth")

    def test_a_dropped_item_lands_on_earth(self) -> None:
        response = self.universe.handle(add_torch())
        self.assertTrue(response.ok)
        self.assertIsNotNone(self.earth.find_item("torch"))

    def test_a_player_on_mars_drops_it_on_mars_not_on_earth(self) -> None:
        self.universe.place_player("bob", "mars")
        self.universe.handle(add_torch("op1", "bob"))
        self.assertIsNotNone(self.universe._world.room("mars").find_item("torch"))
        self.assertIsNone(self.earth.find_item("torch"))

def a_mining_universe() -> tuple[Universe, Deposits]:
    earth = Room("earth", "Earth", "Home.")
    mars = Room("mars", "Mars", "Red.")
    deposits = Deposits({"earth": {"iron": 10}, "mars": {"nickel": 4}})
    universe = Universe(World({"earth": earth, "mars": mars}, "earth"), deposits)
    universe.place_player("ada", "earth")
    universe.place_player("bob", "mars")
    return universe, deposits


def mine(op_id: str = "op1", resource: str = "iron", amount: int = 3,
         player_id: str = "ada") -> Request:
    return Request(op_id, "mine", player_id, resource, amount)


class TestMining(unittest.TestCase):
    def test_mining_succeeds_and_reduces_the_stock(self) -> None:
        universe, deposits = a_mining_universe()
        self.assertTrue(universe.handle(mine()).ok)
        self.assertEqual(7, deposits.available("earth", "iron"))

    def test_asking_for_more_than_is_left_is_refused_and_says_how_much_is_left(self) -> None:
        universe, deposits = a_mining_universe()
        response = universe.handle(mine(amount=11))
        self.assertFalse(response.ok)
        self.assertIn("only 10", response.refusal.describe())
        self.assertEqual(10, deposits.available("earth", "iron"))

    def test_a_resource_that_is_not_here_is_refused(self) -> None:
        universe, deposits = a_mining_universe()
        response = universe.handle(mine(resource="nickel"))
        self.assertFalse(response.ok)
        self.assertIn("Earth", response.refusal.describe())

    def test_a_player_who_is_nowhere_is_refused_and_nothing_is_mined(self) -> None:
        universe, deposits = a_mining_universe()
        response = universe.handle(mine(player_id="eve"))
        self.assertFalse(response.ok)
        self.assertEqual(10, deposits.available("earth", "iron"))

    def test_players_mine_where_they_are(self) -> None:
        universe, deposits = a_mining_universe()
        self.assertTrue(universe.handle(mine("op1", "nickel", 2, "bob")).ok)
        self.assertEqual(2, deposits.available("mars", "nickel"))
        self.assertEqual(10, deposits.available("earth", "iron"))

    def test_a_repeated_op_id_mines_only_once(self) -> None:
        universe, deposits = a_mining_universe()
        first = universe.handle(mine("op1"))
        second = universe.handle(mine("op1"))
        self.assertIs(first, second)
        self.assertEqual(7, deposits.available("earth", "iron"))

    def test_a_string_is_refused_where_deposits_are_expected(self) -> None:
        room = Room("earth", "Earth", "Home.")
        with self.assertRaisesRegex(TypeError, "must be"):
            Universe(World({"earth": room}, "earth"), "iron")  # type: ignore[arg-type]

class TestJoin(unittest.TestCase):
    def test_a_new_player_is_placed_at_the_named_destination(self) -> None:
        universe, _ = a_universe()
        self.assertTrue(universe.handle(Request("op9", "join", "bob", "hall")).ok)
        self.assertEqual("hall", universe.location_of("bob"))

    def test_a_player_who_is_already_somewhere_is_left_there(self) -> None:
        a, b = Room("a", "A", "First."), Room("b", "B", "Second.")
        universe = Universe(World({"a": a, "b": b}, "a"))
        universe.place_player("ada", "a")
        self.assertTrue(universe.handle(Request("op1", "join", "ada", "b")).ok)
        self.assertEqual("a", universe.location_of("ada"))

    def test_an_unknown_destination_is_refused_and_nobody_is_placed(self) -> None:
        universe, _ = a_universe()
        response = universe.handle(Request("op1", "join", "bob", "nowhere"))
        self.assertFalse(response.ok)
        self.assertIn("nowhere", response.refusal.describe())
        self.assertIsNone(universe.location_of("bob"))

    def test_a_stranger_has_no_location(self) -> None:
        universe, _ = a_universe()
        self.assertIsNone(universe.location_of("zed"))


def a_ground() -> tuple[Universe, Room]:
    hall = Room("hall", "Hall", "Cold and tiled.")
    universe = Universe(World({"hall": hall}, "hall"))
    universe.place_player("ada", "hall")
    universe.place_player("bob", "hall")
    return universe, hall


def pick(op_id: str = "p1", item: str = "torch", player: str = "bob") -> Request:
    return Request(op_id, "pick", player, item)


def look(op_id: str = "l1", player: str = "bob") -> Request:
    return Request(op_id, "look", player, "here")


class TestLook(unittest.TestCase):
    def test_an_empty_room_shows_nothing(self) -> None:
        universe, _ = a_ground()
        response = universe.handle(look())
        self.assertTrue(response.ok)
        self.assertEqual((), response.items)

    def test_a_dropped_item_is_listed_with_its_description(self) -> None:
        universe, _ = a_ground()
        universe.handle(add_torch("op1", "ada"))
        items = universe.handle(look()).items
        self.assertEqual([("torch", "torch", "a torch")],
                         [(i.item_id, i.name, i.description) for i in items])

    def test_a_look_is_never_remembered_so_the_same_op_id_sees_fresh_data(self) -> None:
        universe, _ = a_ground()
        self.assertEqual((), universe.handle(look("l1")).items)
        universe.handle(add_torch("op1", "ada"))
        self.assertEqual(1, len(universe.handle(look("l1")).items))

    def test_a_stranger_is_refused(self) -> None:
        universe, _ = a_ground()
        self.assertFalse(universe.handle(look(player="eve")).ok)


class TestPick(unittest.TestCase):
    def test_a_dropped_item_can_be_picked_and_leaves_the_world(self) -> None:
        universe, hall = a_ground()
        universe.handle(add_torch("op1", "ada"))
        response = universe.handle(pick())
        self.assertTrue(response.ok)
        self.assertEqual(["torch"], [i.item_id for i in response.items])
        self.assertIsNone(hall.find_item("torch"))

    def test_when_two_players_pick_the_first_request_wins(self) -> None:
        universe, _ = a_ground()
        universe.handle(add_torch("op1", "ada"))
        self.assertTrue(universe.handle(pick("p1", player="bob")).ok)
        second = universe.handle(pick("p2", player="ada"))
        self.assertFalse(second.ok)
        self.assertIn("already have been picked up", second.refusal.describe())

    def test_an_item_that_is_not_there_is_refused_with_advice(self) -> None:
        universe, _ = a_ground()
        refusal = universe.handle(pick(item="rope")).refusal
        self.assertIn("type look", refusal.describe())

    def test_a_container_is_refused_and_stays(self) -> None:
        universe, hall = a_ground()
        hall.add_item(Container("chest", "chest", "an oak chest"))
        response = universe.handle(pick(item="chest"))
        self.assertFalse(response.ok)
        self.assertIsNotNone(hall.find_item("chest"))

    def test_a_stranger_is_refused(self) -> None:
        universe, _ = a_ground()
        self.assertFalse(universe.handle(pick(player="eve")).ok)

    def test_a_repeated_op_id_gives_the_same_answer_and_picks_once(self) -> None:
        universe, _ = a_ground()
        universe.handle(add_torch("op1", "ada"))
        first = universe.handle(pick("p1"))
        self.assertIs(first, universe.handle(pick("p1")))

    def test_a_picked_item_can_be_dropped_again(self) -> None:
        universe, hall = a_ground()
        universe.handle(add_torch("op1", "ada"))
        universe.handle(pick("p1"))
        self.assertTrue(universe.handle(add_torch("op3", "bob")).ok)
        self.assertIsNotNone(hall.find_item("torch"))

    def test_a_picked_item_stays_gone_after_a_restart_and_the_answer_is_replayed(self) -> None:
        repository = InMemoryUniverseRepository()

        def start() -> tuple[Universe, Room]:
            hall = Room("hall", "Hall", "Cold and tiled.")
            return Universe(World({"hall": hall}, "hall"), None, repository), hall

        universe, _ = start()
        universe.place_player("ada", "hall")
        universe.handle(add_torch("op1", "ada"))
        universe.handle(pick("p1", player="ada"))
        again, hall = start()
        self.assertIsNone(hall.find_item("torch"))
        replay = again.handle(pick("p1", player="ada"))
        self.assertEqual(["torch"], [i.item_id for i in replay.items])
        self.assertIsNone(hall.find_item("torch"))

if __name__ == "__main__":
    unittest.main()