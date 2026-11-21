"""Tests for the world loader and the Factory Method it hangs on."""

import unittest
from pathlib import Path
from typing import Any

from spaceknowledge.world.container import Container
from spaceknowledge.world.item import Item, PlainItem
from spaceknowledge.world.loader import StandardWorldLoader, WorldLoader

WORLD_FILE = Path(__file__).resolve().parents[1] / "fixtures" / "station.json"


def minimal_spec() -> dict[str, Any]:
    """The smallest world that is legal. Kept tiny so a test that changes it
    says what it means, instead of hiding one edit inside eight destinations."""
    return {
        "start": "a",
        "destinations": [
            {"id": "a", "name": "A", "description": "First.", "exits": {"north": "b"}},
            {"id": "b", "name": "B", "description": "Second.", "exits": {"south": "a"}},
        ],
    }


class CountingLoader(WorldLoader):
    """A different Concrete Creator, which is the whole point of the pattern.
    `build` is inherited untouched and produces different products."""

    def __init__(self) -> None:
        self.made = 0

    def make_item(self, spec: dict[str, Any]) -> Item:
        self.made += 1
        return PlainItem(spec["id"], spec["name"], "counted")


class TestBuildingFromData(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = StandardWorldLoader()

    def test_a_minimal_world_builds(self) -> None:
        world = self.loader.build(minimal_spec())
        self.assertEqual(2, world.destination_count())

    def test_the_start_destination_is_the_one_named_in_the_data(self) -> None:
        world = self.loader.build(minimal_spec())
        self.assertEqual("A", world.start_destination.name)

    def test_exits_are_wired_between_destination_objects(self) -> None:
        world = self.loader.build(minimal_spec())
        self.assertIs(world.destination("b"), world.destination("a").exit_to("north"))

    def test_an_exit_to_an_unknown_destination_is_refused(self) -> None:
        spec = minimal_spec()
        spec["destinations"][0]["exits"]["west"] = "nowhere"
        with self.assertRaises(ValueError):
            self.loader.build(spec)

    def test_a_start_destination_that_does_not_exist_is_refused(self) -> None:
        spec = minimal_spec()
        spec["start"] = "nowhere"
        with self.assertRaises(ValueError):
            self.loader.build(spec)

    def test_a_duplicate_destination_id_is_refused(self) -> None:
        spec = minimal_spec()
        spec["destinations"].append(dict(spec["destinations"][0]))
        with self.assertRaises(ValueError):
            self.loader.build(spec)


class TestTheFactoryMethod(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = StandardWorldLoader()

    def test_a_plain_item_spec_becomes_a_plain_item(self) -> None:
        item = self.loader.make_item(
            {"kind": "plain", "id": "k", "name": "key", "description": "a key"}
        )
        self.assertIsInstance(item, PlainItem)

    def test_a_container_spec_becomes_a_container_with_contents(self) -> None:
        item = self.loader.make_item(
            {
                "kind": "container",
                "id": "chest",
                "name": "chest",
                "description": "a chest",
                "contains": [
                    {"kind": "plain", "id": "k", "name": "key", "description": "a key"}
                ],
            }
        )
        self.assertIsInstance(item, Container)
        self.assertIsNotNone(item.find("k"))

    def test_a_missing_kind_is_an_error_not_a_default(self) -> None:
        # Treating an absent kind as "plain" hides a typo for ever. ValueError,
        # not KeyError: missing and unknown must be catchable together.
        with self.assertRaises(ValueError):
            self.loader.make_item({"id": "k", "name": "key", "description": "a key"})

    def test_an_unknown_kind_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.loader.make_item({"kind": "wombat", "id": "k", "name": "k", "description": "d"})

    def test_overriding_the_factory_method_changes_the_products(self) -> None:
        # build() is inherited and unmodified. Only make_item differs.
        spec = minimal_spec()
        spec["destinations"][0]["items"] = [
            {"kind": "plain", "id": "k", "name": "key", "description": "a key"}
        ]
        counting = CountingLoader()
        world = counting.build(spec)
        self.assertEqual(1, counting.made)
        self.assertEqual("counted", world.destination("a").find_item("k").describe())


class TestTheShippedWorld(unittest.TestCase):
    def setUp(self) -> None:
        self.world = StandardWorldLoader().load(WORLD_FILE)

    def test_the_shipped_world_has_eight_destinations(self) -> None:
        self.assertEqual(8, self.world.destination_count())

    def test_the_fixture_world_starts_in_the_entrance_hall(self) -> None:
        self.assertEqual("entrance_hall", self.world.start_destination.destination_id)

    def test_every_exit_points_at_a_destination_that_exists(self) -> None:
        # build() already refuses a dangling exit, so this asserts the shipped
        # data is loadable rather than re-testing the loader.
        self.assertEqual(8, len(self.world.destination_ids()))

    def test_the_brass_key_is_inside_the_pigeonhole_not_loose(self) -> None:
        reception = self.world.destination("reception")
        self.assertIsNone(reception.find_item("brass_key"))
        pigeonhole = reception.find_item("pigeonhole")
        # find_item returns Item | None, and only a Container has .find().
        # Narrow before calling, or this is a type error that happens to work.
        self.assertIsInstance(pigeonhole, Container)
        assert isinstance(pigeonhole, Container)  # narrows for the type checker
        self.assertIsNotNone(pigeonhole.find("brass_key"))


class TestDoorsLoad(unittest.TestCase):
    """Week 4. Doors come from the file, and bad ones are refused at load."""

    def a_spec(self, **overrides: object) -> dict[str, Any]:
        spec: dict[str, Any] = {
            "start": "a",
            "destinations": [
                {
                    "id": "a",
                    "name": "A",
                    "description": "First.",
                    "exits": {"north": "b"},
                    "items": [
                        {
                            "kind": "plain",
                            "id": "brass_key",
                            "name": "brass key",
                            "description": "a key",
                        }
                    ],
                },
                {"id": "b", "name": "B", "description": "Second.",
                 "exits": {"south": "a"}},
            ],
            "doors": [
                {
                    "id": "hatch",
                    "name": "hatch",
                    "key": "brass_key",
                    "sides": [
                        {"destination": "a", "direction": "north"},
                        {"destination": "b", "direction": "south"},
                    ],
                }
            ],
        }
        spec.update(overrides)
        return spec

    def test_a_world_with_no_doors_still_loads(self) -> None:
        # Weeks 1 to 3 shipped files with no "doors" key at all. They must not
        # need editing, because a data format that breaks old data is a bad one.
        spec = self.a_spec()
        del spec["doors"]
        world = StandardWorldLoader().build(spec)
        self.assertIsNone(world.destination("a").door_to("north"))

    def test_both_sides_get_the_same_object(self) -> None:
        """The single most important assertion about doors in the module.

        Two Door objects would each hold their own state, so unlocking from one
        destination would leave the other still locked, and the bug would only show up
        for a player who walked back.
        """
        world = StandardWorldLoader().build(self.a_spec())
        self.assertIs(world.destination("a").door_to("north"),
                      world.destination("b").door_to("south"))

    def test_unlocking_from_one_side_unlocks_the_other(self) -> None:
        world = StandardWorldLoader().build(self.a_spec())
        world.destination("a").door_to("north").unlock("brass_key")
        self.assertTrue(world.destination("b").door_to("south").is_passable())

    def test_a_door_needing_a_key_that_does_not_exist_is_refused(self) -> None:
        spec = self.a_spec()
        spec["doors"][0]["key"] = "silver_key"
        with self.assertRaises(ValueError):
            StandardWorldLoader().build(spec)

    def test_a_key_nested_in_a_container_counts_as_existing(self) -> None:
        spec = self.a_spec()
        spec["destinations"][0]["items"] = [
            {
                "kind": "container",
                "id": "box",
                "name": "box",
                "description": "a box",
                "contains": [
                    {"kind": "plain", "id": "brass_key", "name": "brass key",
                     "description": "a key"}
                ],
            }
        ]
        self.assertIsNotNone(StandardWorldLoader().build(spec))

    def test_a_door_on_a_destination_that_does_not_exist_is_refused(self) -> None:
        spec = self.a_spec()
        spec["doors"][0]["sides"][0]["destination"] = "nowhere"
        with self.assertRaises(ValueError):
            StandardWorldLoader().build(spec)

    def test_a_door_on_a_direction_that_is_not_an_exit_is_refused(self) -> None:
        # A door across a wall is invisible and unreachable. Silently accepting
        # it would leave a typo in the data working exactly like a deletion.
        spec = self.a_spec()
        spec["doors"][0]["sides"][0]["direction"] = "up"
        with self.assertRaises(ValueError):
            StandardWorldLoader().build(spec)

    def test_a_door_that_a_mission_opens_needs_no_key_item(self) -> None:
        spec = self.a_spec()
        spec["doors"][0]["key"] = "mission:ship"
        world = StandardWorldLoader().build(spec)
        self.assertFalse(world.destination("a").door_to("north").is_passable())


class TestTheShippedWorldsDoor(unittest.TestCase):
    def test_the_dome_hatch_is_locked_and_the_key_is_findable(self) -> None:
        world = StandardWorldLoader().load(WORLD_FILE)
        hatch = world.destination("stairwell").door_to("up")
        self.assertEqual("locked", hatch.state_name())
        self.assertEqual("brass_key", hatch.key_id)


if __name__ == "__main__":
    unittest.main()
