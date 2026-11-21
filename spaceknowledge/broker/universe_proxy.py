"""PROXY. The Broker's stand-in for the Universe's questions about items."""

from collections.abc import Callable

from spaceknowledge.broker.item_proxy import ItemProxy
from spaceknowledge.common.messages import ItemInfo, Request
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.transport.channel import UniverseChannel

# Sends a request with crash protection, and settles it: (request, proxy) -> why not.
Sender = Callable[[Request, ItemProxy | None], Refusal | None]


class UniverseProxy:
    """Asks the Universe what lies here and hands back ItemProxies, and sends
    a proxy's pick. It knows nothing about the world itself."""

    def __init__(
        self, channel: UniverseChannel, next_op_id: Callable[[], str], send: Sender
    ) -> None:
        if not isinstance(channel, UniverseChannel):
            raise TypeError(f"channel must be a UniverseChannel, not {type(channel).__name__}")
        if not callable(next_op_id):
            raise TypeError("next_op_id must be callable")
        if not callable(send):
            raise TypeError("send must be callable")
        self._channel = channel
        self._next_op_id = next_op_id
        self._send = send

    def look(self, player_id: str) -> list[ItemProxy] | Refusal:
        """A proxy for every item lying where the player is. The request's
        item id is the placeholder "here": the Universe knows the location."""
        response = self._channel.send(Request(self._next_op_id(), "look", player_id, "here"))
        if not response.ok:
            return response.refusal  # type: ignore[return-value]
        return [ItemProxy(info, self.pick) for info in response.items]

    def where(self, player_id: str) -> tuple[str, str] | Refusal:
        """The id and name of the destination the player is in."""
        response = self._channel.send(Request(self._next_op_id(), "where", player_id, "here"))
        if not response.ok:
            return response.refusal  # type: ignore[return-value]
        if len(response.items) != 1:
            return Refusal("find out where you are", "the game gave an unexpected answer",
                           "try again in a moment")
        place = response.items[0]
        return place.item_id, place.name

    def mission(self, player_id: str) -> ItemInfo | Refusal:
        """The current mission as plain data: its status, title and text."""
        response = self._channel.send(Request(self._next_op_id(), "mission", player_id, "here"))
        if not response.ok:
            return response.refusal  # type: ignore[return-value]
        if len(response.items) != 1:
            return Refusal("read the mission", "the game gave an unexpected answer",
                           "try again in a moment")
        return response.items[0]

    def pick(self, proxy: ItemProxy, player_id: str) -> Refusal | None:
        """Put the proxy in flight, then send the pick through the Broker's
        crash-safe path. A proxy already in flight is refused, and nothing is sent."""
        refusal = proxy.begin_pick()
        if refusal is not None:
            return refusal
        return self._send(Request(self._next_op_id(), "pick", player_id, proxy.item_id), proxy)