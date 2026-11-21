"""Tests that the shipped space world loads and is wired as intended."""

import unittest
from pathlib import Path
import json
from spaceknowledge.common.messages import Request
from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.missions import MissionBook
from spaceknowledge.universe.universe import Universe

from spaceknowledge.world.loader import StandardWorldLoader

SPACE_FILE = Path(__file__).resolve().parents[3] / "data" / "space.json"


class TestTheSpaceWorld(unittest.TestCase):
    def setUp(self) -> None:
        self.world = StandardWorldLoader().load(SPACE_FILE)

    def test_it_has_three_destinations(self) -> None:
        self.assertEqual(3, self.world.destination_count())

    def test_the_game_starts_on_earth(self) -> None:
        self.assertEqual("earth", self.world.start_destination.destination_id)

    def test_earth_leads_to_the_moon_and_mars(self) -> None:
        earth = self.world.destination("earth")
        self.assertIs(self.world.destination("moon"), earth.exit_to("moon"))
        self.assertIs(self.world.destination("mars"), earth.exit_to("mars"))

    def test_you_can_fly_home_from_mars(self) -> None:
        self.assertIs(self.world.destination("earth"), self.world.destination("mars").exit_to("earth"))


    def test_the_shipped_galaxy_has_a_locked_mars_and_a_mission_that_opens_it(self) -> None:
        raw = json.loads(SPACE_FILE.read_text(encoding="utf-8"))
        earth = self.world.destination("earth")
        self.assertFalse(earth.door_to("mars").is_passable())
        self.assertIsNone(earth.door_to("moon"))

        universe = Universe(self.world, Deposits.from_raw(raw), None, missions=MissionBook.from_raw(raw))
        universe.place_player("ada", "earth")
        universe.handle(Request("m1", "mine", "ada", "iron", 20))
        self.assertEqual("question", universe.handle(Request("q1", "mission", "ada", "here")).items[0].item_id)
        self.assertTrue(universe.handle(Request("a1", "answer", "ada", "iron")).ok)
        self.assertTrue(universe.handle(Request("f1", "fly", "ada", "mars")).ok)

if __name__ == "__main__":
    unittest.main()