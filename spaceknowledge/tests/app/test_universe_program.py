"""Tests for start_universe: the Universe as its own server."""

import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from spaceknowledge.app.keys import read_existing_key
from spaceknowledge.app.paths import SERVER_KEY_FILE
from spaceknowledge.app.universe_program import UniverseProcess, start_universe
from spaceknowledge.common.messages import Request
from spaceknowledge.transport.server_auth import ServerAuthError, ServerIdentity
from spaceknowledge.transport.socket_channel import SocketChannel

SPACE_FILE = Path(__file__).resolve().parents[3] / "data" / "space.json"
LISTENER = "universe-listener"


def thread_names() -> set[str]:
    return {thread.name for thread in threading.enumerate()}


def join(op_id: str = "j1", player: str = "ada") -> Request:
    return Request(op_id, "join", player, "earth")


def mine(op_id: str, amount: int) -> Request:
    return Request(op_id, "mine", "ada", "iron", amount)


class TestStartUniverse(unittest.TestCase):
    def setUp(self) -> None:
        self.state = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state)

    def start(self, peers: tuple[str, ...] = ("broker-1",)) -> UniverseProcess:
        process = start_universe(SPACE_FILE, self.state, peers=peers)
        self.addCleanup(process.close)
        return process

    def channel(self, process: UniverseProcess, key: bytes | None = None) -> SocketChannel:
        host, port = process.address
        key = key or read_existing_key(self.state / SERVER_KEY_FILE)
        channel = SocketChannel(host, port, ServerIdentity("broker-1", key), 5.0)
        self.addCleanup(channel.close)  # runs before the process closes
        return channel

    def test_it_listens_on_a_port_the_system_chose_and_answers(self) -> None:
        process = self.start()
        self.assertGreater(process.address[1], 0)
        self.assertTrue(self.channel(process).send(join()).ok)
        self.assertEqual("earth", process.universe.location_of("ada"))

    def test_the_server_key_is_created_in_the_state_folder(self) -> None:
        self.start()
        self.assertTrue((self.state / SERVER_KEY_FILE).exists())

    def test_closing_stops_the_listener_and_closing_twice_is_harmless(self) -> None:
        process = self.start()
        self.assertIn(LISTENER, thread_names())
        process.close()
        process.close()
        self.assertNotIn(LISTENER, thread_names())

    def test_a_wrong_key_is_refused_and_nothing_is_answered(self) -> None:
        process = self.start()
        with self.assertRaises(ServerAuthError):
            self.channel(process, key=b"o" * 32).send(join())
        self.assertEqual(0, process.universe.answer_count())

    def test_the_universe_state_survives_a_restart_of_the_program(self) -> None:
        first = self.start()
        channel = self.channel(first)
        channel.send(join())
        self.assertTrue(channel.send(mine("m1", 3)).ok)
        first.close()

        second = self.start()  # a new process: new port, same state folder
        channel = self.channel(second)
        self.assertTrue(channel.send(mine("m1", 3)).ok)      # replayed, not mined again
        self.assertTrue(channel.send(mine("m2", 497)).ok)    # 500 - 3 = 497 are left
        self.assertFalse(channel.send(mine("m3", 1)).ok)     # and now there is none

    def test_bad_arguments_are_refused(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            start_universe("space.json", self.state)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            start_universe(SPACE_FILE, "state")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            start_universe(SPACE_FILE, self.state, peers=())
        self.assertNotIn(LISTENER, thread_names())


if __name__ == "__main__":
    unittest.main()