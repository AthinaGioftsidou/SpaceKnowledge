"""Tests for the Universe on a socket: UniverseListener and SocketChannel.

These use real loopback sockets on a port the operating system picks (never a
fixed port), and wait on events and timeouts, never on long sleeps."""

import socket
import threading
import time
import unittest

from spaceknowledge.common.messages import Request, Response
from spaceknowledge.tests.transport.helpers import WAIT, in_thread
from spaceknowledge.transport.channel import UniverseChannel
from spaceknowledge.transport.server_auth import ServerAuthError, ServerIdentity
from spaceknowledge.transport.socket_channel import SocketChannel
from spaceknowledge.transport.universe_listener import UniverseListener
from spaceknowledge.transport.wire import MAX_LINE, read_message, request_to_wire, write_message
from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.universe import Universe
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World

KEY = b"k" * 32
OTHER = b"o" * 32
LOGGER = "spaceknowledge.transport.universe_listener"


class OverlapUniverse(Universe):
    """Counts how many requests are inside `handle` at the same moment."""

    def __init__(self, world: World, deposits: Deposits) -> None:
        super().__init__(world, deposits)
        self.active = 0
        self.peak = 0

    def handle(self, request: Request) -> Response:
        self.active += 1
        self.peak = max(self.peak, self.active)
        time.sleep(0.001)  # long enough for an unprotected overlap to show
        try:
            return super().handle(request)
        finally:
            self.active -= 1


class BlockingUniverse(Universe):
    """Stops inside `handle` until the test lets it go."""

    def __init__(self, world: World, deposits: Deposits) -> None:
        super().__init__(world, deposits)
        self.release = threading.Event()

    def handle(self, request: Request) -> Response:
        self.release.wait(WAIT)
        return super().handle(request)


class FlakyUniverse(Universe):
    """Fails once, with an error nobody planned for."""

    def __init__(self, world: World, deposits: Deposits) -> None:
        super().__init__(world, deposits)
        self.fail_next = True

    def handle(self, request: Request) -> Response:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("boom")
        return super().handle(request)


def a_universe(kind=Universe, iron: int = 100):  # type: ignore[no-untyped-def]
    earth = Destination("earth", "Earth", "Home.")
    deposits = Deposits({"earth": {"iron": iron}})
    universe = kind(World({"earth": earth}, "earth"), deposits)
    universe.place_player("ada", "earth")
    universe.place_player("bob", "earth")
    return universe, deposits


def mine(op_id: str, player: str = "ada", amount: int = 1) -> Request:
    return Request(op_id, "mine", player, "iron", amount)


def a_listener(test: unittest.TestCase, universe: Universe, key: bytes = KEY,
               peers: tuple[str, ...] = ("broker",)) -> UniverseListener:
    listener = UniverseListener(universe, ServerIdentity("universe", key), peers=peers)
    listener.start()
    test.addCleanup(listener.stop)
    return listener


def a_channel(test: unittest.TestCase, listener: UniverseListener, key: bytes = KEY,
              name: str = "broker", timeout: float = 5.0) -> SocketChannel:
    host, port = listener.address
    channel = SocketChannel(host, port, ServerIdentity(name, key), timeout)
    test.addCleanup(channel.close)  # runs before the listener's stop
    return channel


def closed_by_server(stream) -> bool:  # type: ignore[no-untyped-def]
    """True if the server ended the connection (cleanly or with a reset)."""
    try:
        return read_message(stream) is None
    except OSError:
        return True


class TestAnswering(unittest.TestCase):
    def test_it_is_a_universe_channel(self) -> None:
        universe, _ = a_universe()
        self.assertIsInstance(a_channel(self, a_listener(self, universe)), UniverseChannel)

    def test_a_request_is_answered_and_the_world_changes(self) -> None:
        universe, deposits = a_universe()
        channel = a_channel(self, a_listener(self, universe))
        response = channel.send(mine("op1", amount=3))
        self.assertTrue(response.ok)
        self.assertEqual("op1", response.op_id)
        self.assertEqual(97, deposits.available("earth", "iron"))

    def test_a_refusal_crosses_the_socket_with_its_three_parts(self) -> None:
        universe, deposits = a_universe()
        channel = a_channel(self, a_listener(self, universe))
        response = channel.send(mine("op1", amount=1000))
        self.assertFalse(response.ok)
        self.assertIn("Next:", response.refusal.describe())
        self.assertEqual(100, deposits.available("earth", "iron"))

    def test_item_data_crosses_the_socket(self) -> None:
        universe, _ = a_universe()
        channel = a_channel(self, a_listener(self, universe))
        channel.send(Request("op1", "add_item", "ada", "torch-1", name="torch"))
        items = channel.send(Request("op2", "look", "bob", "here")).items
        self.assertEqual([("torch-1", "torch")], [(i.item_id, i.name) for i in items])

    def test_a_repeated_op_id_changes_the_world_only_once(self) -> None:
        universe, deposits = a_universe()
        channel = a_channel(self, a_listener(self, universe))
        channel.send(mine("op1"))
        channel.send(mine("op1"))
        self.assertEqual(99, deposits.available("earth", "iron"))


class TestAuthentication(unittest.TestCase):
    def test_a_wrong_key_is_refused_and_nothing_reaches_the_universe(self) -> None:
        universe, deposits = a_universe()
        channel = a_channel(self, a_listener(self, universe), key=OTHER)
        with self.assertRaises(ServerAuthError):
            channel.send(mine("op1"))
        self.assertEqual(100, deposits.available("earth", "iron"))
        self.assertEqual(0, universe.answer_count())

    def test_a_name_that_is_not_an_allowed_peer_is_refused(self) -> None:
        universe, deposits = a_universe()
        channel = a_channel(self, a_listener(self, universe), name="intruder")
        with self.assertRaises(ServerAuthError):
            channel.send(mine("op1"))
        self.assertEqual(100, deposits.available("earth", "iron"))

    def test_several_allowed_peers_can_connect(self) -> None:
        universe, _ = a_universe()
        listener = a_listener(self, universe, peers=("broker-1", "broker-2"))
        for name, op in (("broker-1", "op1"), ("broker-2", "op2")):
            self.assertTrue(a_channel(self, listener, name=name).send(mine(op)).ok)

    def test_a_client_that_skips_the_handshake_is_closed_and_the_world_untouched(self) -> None:
        universe, deposits = a_universe()
        listener = a_listener(self, universe)
        sock = socket.create_connection(listener.address, timeout=WAIT)
        self.addCleanup(sock.close)
        stream = sock.makefile("rb")
        self.addCleanup(stream.close)
        read_message(stream)  # the challenge
        write_message(sock.sendall, request_to_wire(mine("op1")))
        self.assertTrue(closed_by_server(stream))
        self.assertEqual(100, deposits.available("earth", "iron"))

    def test_garbage_and_oversize_lines_close_the_connection(self) -> None:
        universe, _ = a_universe()
        listener = a_listener(self, universe)
        for data in (b"not json\n", b"x" * (MAX_LINE + 10) + b"\n"):
            with self.subTest(size=len(data)):
                sock = socket.create_connection(listener.address, timeout=WAIT)
                self.addCleanup(sock.close)
                stream = sock.makefile("rb")
                self.addCleanup(stream.close)
                read_message(stream)
                sock.sendall(data)
                self.assertTrue(closed_by_server(stream))


class TestConcurrency(unittest.TestCase):
    def test_many_brokers_at_once_all_succeed_and_nothing_is_lost(self) -> None:
        universe, deposits = a_universe(iron=100)
        listener = a_listener(self, universe)
        channels = [a_channel(self, listener) for _ in range(4)]
        results: list[bool] = []

        def broker(number: int) -> None:
            for step in range(10):
                results.append(channels[number].send(mine(f"b{number}-{step}")).ok)

        workers = [in_thread(lambda n=n: broker(n)) for n in range(4)]
        for worker in workers:
            worker.join(WAIT)
        self.assertEqual([True] * 40, results)
        self.assertEqual(60, deposits.available("earth", "iron"))

    def test_only_one_request_changes_the_world_at_a_time(self) -> None:
        universe, _ = a_universe(OverlapUniverse)
        listener = a_listener(self, universe)
        channels = [a_channel(self, listener) for _ in range(4)]

        def broker(number: int) -> None:
            for step in range(10):
                channels[number].send(mine(f"b{number}-{step}"))

        workers = [in_thread(lambda n=n: broker(n)) for n in range(4)]
        for worker in workers:
            worker.join(WAIT)
        self.assertEqual(1, universe.peak)


class TestLifecycle(unittest.TestCase):
    def test_a_stopped_listener_refuses_new_connections(self) -> None:
        universe, _ = a_universe()
        listener = a_listener(self, universe)
        channel = a_channel(self, listener)
        listener.stop()
        with self.assertRaises(ConnectionError):
            channel.send(mine("op1"))

    def test_stopping_twice_is_harmless(self) -> None:
        universe, _ = a_universe()
        listener = a_listener(self, universe)
        listener.stop()
        listener.stop()

    def test_stopping_ends_open_connections(self) -> None:
        universe, _ = a_universe()
        listener = a_listener(self, universe)
        channel = a_channel(self, listener)
        self.assertTrue(channel.send(mine("op1")).ok)
        listener.stop()
        with self.assertRaises(ConnectionError):
            channel.send(mine("op2"))

    def test_the_channel_quietly_reconnects_when_the_listener_dropped_it(self) -> None:
        universe, deposits = a_universe()
        listener = a_listener(self, universe)
        channel = a_channel(self, listener)
        channel.send(mine("op1"))
        listener.disconnect_all()
        self.assertTrue(channel.send(mine("op2")).ok)
        self.assertEqual(98, deposits.available("earth", "iron"))

    def test_a_closed_channel_connects_again_on_the_next_send(self) -> None:
        universe, _ = a_universe()
        channel = a_channel(self, a_listener(self, universe))
        channel.send(mine("op1"))
        channel.close()
        self.assertTrue(channel.send(mine("op2")).ok)

    def test_a_reply_that_never_comes_times_out(self) -> None:
        universe, _ = a_universe(BlockingUniverse)
        listener = a_listener(self, universe)
        self.addCleanup(universe.release.set)  # runs before the listener stops
        channel = a_channel(self, listener, timeout=0.3)
        with self.assertRaises(TimeoutError):
            channel.send(mine("op1"))

    def test_an_unexpected_error_is_logged_and_the_resent_request_succeeds(self) -> None:
        universe, deposits = a_universe(FlakyUniverse)
        channel = a_channel(self, a_listener(self, universe))
        with self.assertLogs(LOGGER, level="ERROR") as logs:
            with self.assertRaises(ConnectionError):
                channel.send(mine("op1"))
        self.assertIn("op1", "\n".join(logs.output))
        self.assertEqual(100, deposits.available("earth", "iron"))
        # What crash recovery does: send the same op_id again.
        self.assertTrue(channel.send(mine("op1")).ok)
        self.assertEqual(99, deposits.available("earth", "iron"))


class TestArguments(unittest.TestCase):
    def test_bad_arguments_are_refused(self) -> None:
        universe, _ = a_universe()
        identity = ServerIdentity("universe", KEY)
        with self.assertRaisesRegex(TypeError, "must be"):
            UniverseListener("universe", identity)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            UniverseListener(universe, "identity")  # type: ignore[arg-type]
        for kwargs in ({"peers": ()}, {"peers": ("universe",)}, {"peers": ("",)},
                       {"handshake_timeout": 0}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    UniverseListener(universe, identity, **kwargs)  # type: ignore[arg-type]
        me = ServerIdentity("broker", KEY)
        with self.assertRaisesRegex(TypeError, "must be"):
            SocketChannel("127.0.0.1", 5000, "me")  # type: ignore[arg-type]
        for host, port, timeout in (("", 5000, 5.0), ("h", 0, 5.0), ("h", 70000, 5.0),
                                    ("h", 5000, 0)):
            with self.subTest(host=host, port=port, timeout=timeout):
                with self.assertRaises(ValueError):
                    SocketChannel(host, port, me, timeout)
        with self.assertRaisesRegex(TypeError, "must be"):
            SocketChannel("127.0.0.1", 5000, me).send("request")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()