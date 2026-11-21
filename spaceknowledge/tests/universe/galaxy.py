"""A small galaxy for the travel and mission tests: Earth, the Moon and Mars."""

from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.missions import MissionBook
from spaceknowledge.universe.universe import Universe
from spaceknowledge.universe.universe_repository import UniverseRepository
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.door import Door
from spaceknowledge.world.world import World


def a_galaxy(
    door_to_mars: Door | None = None,
    repository: UniverseRepository | None = None,
    deposits: Deposits | None = None,
    place: bool = True,
    missions: MissionBook | None = None,
) -> Universe:
    """Earth has routes to the Moon and Mars (the Mars route may have a door).
    With `place`, ada and bob start on Earth. A restarted Universe must not be
    placed again, or it would forget where its players were."""
    earth = Destination("earth", "Earth", "Home.")
    moon = Destination("moon", "The Moon", "Grey and airless.")
    mars = Destination("mars", "Mars", "Red.")
    earth.add_exit("moon", moon)
    earth.add_exit("mars", mars, door_to_mars)
    moon.add_exit("earth", earth)
    mars.add_exit("earth", earth)
    universe = Universe(
        World({"earth": earth, "moon": moon, "mars": mars}, "earth"),
        deposits, repository, missions=missions,
    )
    if place:
        for player in ("ada", "bob"):
            universe.place_player(player, "earth")
    return universe