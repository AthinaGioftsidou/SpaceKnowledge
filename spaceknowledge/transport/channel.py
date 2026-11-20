"""The channel between the Broker and the Universe."""

from abc import ABC, abstractmethod

from spaceknowledge.common.messages import Request, Response
from spaceknowledge.universe.universe import Universe


class UniverseChannel(ABC):
    """What the Broker needs from the Universe: send a request, get an answer.

    The Broker knows only this contract. An in-memory version exists now, and
    a socket version can replace it later without changing the Broker.
    """

    @abstractmethod
    def send(self, request: Request) -> Response:
        """Deliver the request and return the Universe's answer."""


class InMemoryChannel(UniverseChannel):
    """Calls the Universe directly, in the same process."""

    def __init__(self, universe: Universe) -> None:
        if not isinstance(universe, Universe):
            raise TypeError(f"universe must be a Universe, not {type(universe).__name__}")
        self._universe = universe

    def send(self, request: Request) -> Response:
        if not isinstance(request, Request):
            raise TypeError(f"request must be a Request, not {type(request).__name__}")
        return self._universe.handle(request)