"""Tests for UniverseProxy: the Broker's stand-in for the Universe."""

import itertools
import unittest

from spaceknowledge.broker.item_proxy import ItemProxy
from spaceknowledge.broker.universe_proxy import UniverseProxy
from spaceknowledge.common.messages import ItemInfo, Request, Response
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.transport.channel import UniverseChannel


class StubChannel(UniverseChannel):
    """Answers every request with a fixed response, and remembers the requests."""

    def __init__(self, response: Response) -> None:
        self._response = response
        self.requests: list[Request] = []

    def send(self, request: Request) -> Response:
        self.requests.append(request)
        return self._response


def a_proxy(response: Response):  # type: ignore[no-untyped-def]
    counter = itertools.count(1)
    sent: list[tuple[Request, ItemProxy | None]] = []

    def send(request: Request, proxy: ItemProxy | None) -> Refusal | None:
        sent.append((request, proxy))
        return None

    channel = StubChannel(response)
    return UniverseProxy(channel, lambda: f"op{next(counter)}", send), channel, sent


TORCH = ItemInfo("torch", "torch", "a rubber torch")


class TestLook(unittest.TestCase):
    def test_a_look_is_sent_and_the_answer_becomes_item_proxies(self) -> None:
        universe, channel, _ = a_proxy(Response("x", items=(TORCH,)))
        proxies = universe.look("ada")
        self.assertEqual(("look", "ada"), (channel.requests[0].action, channel.requests[0].player_id))
        self.assertEqual(["torch"], [proxy.name for proxy in proxies])
        self.assertIsInstance(proxies[0], ItemProxy)
        self.assertEqual(("owned", "universe"), (proxies[0].state(), proxies[0].holder()))

    def test_an_empty_destination_gives_no_proxies(self) -> None:
        universe, _, _ = a_proxy(Response("x"))
        self.assertEqual([], universe.look("ada"))

    def test_a_refused_look_gives_the_refusal(self) -> None:
        refusal = Refusal("look here", "unknown player", "log in")
        universe, _, _ = a_proxy(Response("x", refusal))
        self.assertIs(refusal, universe.look("ada"))


class TestPick(unittest.TestCase):
    def test_a_proxy_pick_puts_it_in_flight_and_sends_a_pick_request(self) -> None:
        universe, _, sent = a_proxy(Response("x", items=(TORCH,)))
        proxy = universe.look("ada")[0]
        self.assertIsNone(proxy.pick("ada"))
        request, sent_proxy = sent[0]
        self.assertEqual(("pick", "ada", "torch"),
                         (request.action, request.player_id, request.item_id))
        self.assertIs(proxy, sent_proxy)
        self.assertEqual("flight", proxy.state())

    def test_a_proxy_already_in_flight_is_refused_and_nothing_is_sent(self) -> None:
        universe, _, sent = a_proxy(Response("x", items=(TORCH,)))
        proxy = universe.look("ada")[0]
        proxy.begin_pick()
        self.assertIsInstance(universe.pick(proxy, "ada"), Refusal)
        self.assertEqual([], sent)


class TestArguments(unittest.TestCase):
    def test_bad_arguments_are_refused(self) -> None:
        channel = StubChannel(Response("x"))
        with self.assertRaisesRegex(TypeError, "must be"):
            UniverseProxy("channel", lambda: "op", lambda r, p: None)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            UniverseProxy(channel, "op", lambda r, p: None)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            UniverseProxy(channel, lambda: "op", "send")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()