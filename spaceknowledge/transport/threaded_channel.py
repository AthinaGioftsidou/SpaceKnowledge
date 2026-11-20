"""A channel that crosses from the Broker's thread to the Universe's thread."""

from spaceknowledge.common.messages import Request, Response
from spaceknowledge.transport.channel import UniverseChannel
from spaceknowledge.transport.universe_server import UniverseServer


class ThreadedChannel(UniverseChannel):
    """The same contract as InMemoryChannel, so the Broker does not change.
    `send` queues the request for the Universe thread and waits for the answer."""

    def __init__(self, server: UniverseServer, timeout: float = 5.0) -> None:
        if not isinstance(server, UniverseServer):
            raise TypeError(f"server must be a UniverseServer, not {type(server).__name__}")
        if timeout <= 0:
            raise ValueError("timeout must be more than 0 seconds")
        self._server = server
        self._timeout = timeout

    def send(self, request: Request) -> Response:
        if not isinstance(request, Request):
            raise TypeError(f"request must be a Request, not {type(request).__name__}")
        return self._server.call(request, self._timeout)