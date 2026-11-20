"""Tests that the shipped space world loads and is wired as intended."""

import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()