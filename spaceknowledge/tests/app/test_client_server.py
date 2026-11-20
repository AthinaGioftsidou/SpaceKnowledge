"""Scenario tests: the Universe, two Brokers with DMZs, and HTTP clients."""

import shutil
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from spaceknowledge.app.broker_program import BrokerNode, start_broker_node
from spaceknowledge.app.paths import SERVER_KEY_FILE
from spaceknowledge.app.universe_program import start_universe
from spaceknowledge.client.game_client import GameClient, SessionEnded
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.tests.transport.helpers import WAIT, in_thread

SPACE_FILE = Path(__file__).resolve().parents[3] / "data" / "space.json"
PASSWORD = "correct horse"
THREADS = {"dmz", "broker", "universe-listener"}


def thread_names() -> set[str]:
    return {thread.name for thread in threading.enumerate()}


class TestClientsOverHttp(unittest.TestCase):
    
    def test_a_player_flies_and_each_place_has_its_own_stock_and_ground(self) -> None:
        one, two = self.client(self.node("broker-1")), self.client(self.node("broker-2"))
        ada, bob = self.signed_in(one, "ada"), self.signed_in(two, "bob")
        self.assertIn("no nickel to mine", one.command(ada, "mine nickel 1"))
        reply = one.command(ada, "fly to mars")
        self.assertTrue(reply.startswith("You fly to Mars."))
        self.assertIn("Nickel can be mined here.", reply)
        self.assertEqual("You are at Mars.", one.command(ada, "where"))
        self.assertEqual("You are at Earth.", two.command(bob, "where"))
        self.assertEqual("You mine 5 nickel.", one.command(ada, "mine nickel 5"))
        self.assertIn("no nickel to mine", two.command(bob, "mine nickel 1"))
        self.assertEqual("You drop the torch.", one.command(ada, "drop torch"))
        self.assertEqual("Nothing lies on the ground here.", two.command(bob, "look"))
        two.command(bob, "fly mars")
        self.assertEqual("On the ground here: torch", two.command(bob, "look"))

    def test_a_flight_with_no_route_is_refused_with_the_routes_listed(self) -> None:
        client = self.client(self.node("broker-1"))
        token = self.signed_in(client, "ada")
        text = client.command(token, "fly sun")
        self.assertIn("no route to sun", text)
        self.assertIn("fly to one of: mars, moon", text)
        self.assertEqual("You are at Earth.", client.command(token, "where"))

    def test_a_players_place_survives_restarting_every_program(self) -> None:
        node = self.node("broker-1")
        client = self.client(node)
        client.command(self.signed_in(client, "ada"), "fly mars")
        node.close()
        self.process.close()

        self.process = start_universe(
            SPACE_FILE, self.universe_dir, peers=("broker-1", "broker-2"))
        client = self.client(self.node("broker-1"))
        token = client.login("ada", PASSWORD)  # logging in joins at Earth, but a placed player stays
        assert isinstance(token, str), token
        self.assertEqual("You are at Mars.", client.command(token, "where"))

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.universe_dir = self.root / "universe"
        self.process = start_universe(
            SPACE_FILE, self.universe_dir, peers=("broker-1", "broker-2"))
        self.addCleanup(lambda: self.process.close())  # the current one, even after a restart

    def node(self, name: str, dmz_port: int = 0) -> BrokerNode:
        host, port = self.process.address
        node = start_broker_node(
            self.root / name, self.universe_dir / SERVER_KEY_FILE, host, port, "earth", name,
            dmz_port=dmz_port, iterations=1, timeout=2.0)
        self.addCleanup(node.close)
        return node

    @staticmethod
    def client(node: BrokerNode) -> GameClient:
        host, port = node.address
        return GameClient(host, port, timeout=10.0)

    def signed_in(self, client: GameClient, name: str) -> str:
        self.assertIsNone(client.register(name, PASSWORD))
        token = client.login(name, PASSWORD)
        assert isinstance(token, str), token
        return token

    def test_a_player_registers_logs_in_and_plays_over_http(self) -> None:
        client = self.client(self.node("broker-1"))
        token = self.signed_in(client, "ada")
        self.assertEqual("You mine 3 iron.", client.command(token, "mine iron 3"))
        self.assertEqual("You are carrying: torch\nResources: iron 3",
                         client.command(token, "inventory"))
        self.assertTrue(client.logout(token))
        with self.assertRaises(SessionEnded):
            client.command(token, "inventory")

    def test_clients_of_two_brokers_share_one_world(self) -> None:
        one, two = self.client(self.node("broker-1")), self.client(self.node("broker-2"))
        ada, bob = self.signed_in(one, "ada"), self.signed_in(two, "bob")
        self.assertEqual("You drop the torch.", one.command(ada, "drop torch"))
        self.assertEqual("On the ground here: torch", two.command(bob, "look"))
        self.assertEqual("You pick up the torch.", two.command(bob, "pick torch"))
        self.assertEqual("You mine 5 iron.", one.command(ada, "mine iron 5"))
        self.assertEqual("You mine 5 iron.", two.command(bob, "mine iron 5"))
        self.assertEqual("You mine 490 iron.", one.command(ada, "mine iron 490"))
        self.assertIn("no iron to mine", two.command(bob, "mine iron 1"))

    def test_a_client_sees_no_trace_of_the_internal_server_even_when_it_is_down(self) -> None:
        client = self.client(self.node("broker-1"))
        token = self.signed_in(client, "ada")
        port = str(self.process.address[1])
        self.process.close()
        reply = client.command(token, "mine iron 1")
        self.assertIn("game world did not answer", reply)
        self.assertIsNone(client.register("bob", PASSWORD))
        refusal = client.login("bob", PASSWORD)
        self.assertIsInstance(refusal, Refusal)
        for text in (reply, refusal.describe()):
            self.assertNotIn("universe", text.lower())
            self.assertNotIn(port, text)

    def test_everything_survives_restarting_every_program(self) -> None:
        node = self.node("broker-1")
        client = self.client(node)
        client.command(self.signed_in(client, "ada"), "mine iron 3")
        node.close()
        self.process.close()

        self.process = start_universe(
            SPACE_FILE, self.universe_dir, peers=("broker-1", "broker-2"))
        client = self.client(self.node("broker-1"))
        token = client.login("ada", PASSWORD)
        assert isinstance(token, str), token
        self.assertEqual("You are carrying: torch\nResources: iron 3",
                         client.command(token, "inventory"))
        self.assertEqual("You mine 497 iron.", client.command(token, "mine iron 497"))

    def test_a_stopped_broker_is_a_connection_error_for_its_client(self) -> None:
        node = self.node("broker-1")
        client = self.client(node)
        node.close()
        with self.assertRaises(ConnectionError):
            client.login("ada", PASSWORD)

    def test_many_clients_on_both_brokers_at_once_lose_nothing(self) -> None:
        clients = [self.client(self.node("broker-1")), self.client(self.node("broker-2"))]
        replies: list[str] = []

        def player(number: int) -> None:
            client = clients[number % 2]
            token = self.signed_in(client, f"player{number}")
            for _ in range(5):
                replies.append(client.command(token, "mine iron 1"))

        workers = [in_thread(lambda n=n: player(n)) for n in range(6)]
        for worker in workers:
            worker.join(WAIT * 3)
        self.assertEqual(["You mine 1 iron."] * 30, replies)
        token = self.signed_in(clients[0], "closer")
        self.assertEqual("You mine 470 iron.", clients[0].command(token, "mine iron 470"))
        self.assertIn("no iron to mine", clients[0].command(token, "mine iron 1"))

    def test_closing_everything_leaves_no_thread_behind(self) -> None:
        one, two = self.node("broker-1"), self.node("broker-2")
        self.signed_in(self.client(one), "ada")
        self.signed_in(self.client(two), "bob")
        one.close()
        two.close()
        self.process.close()
        self.assertFalse(THREADS & thread_names())

    def test_a_dmz_port_that_is_taken_stops_the_broker_again(self) -> None:
        taken = socket.socket()
        self.addCleanup(taken.close)
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        with self.assertRaises(OSError):
            self.node("broker-1", dmz_port=taken.getsockname()[1])
        self.assertNotIn("broker", thread_names())

    def test_bad_arguments_are_refused(self) -> None:
        host, port = self.process.address
        key_file = self.universe_dir / SERVER_KEY_FILE
        with self.assertRaisesRegex(TypeError, "must be"):
            start_broker_node("state", key_file, host, port, "earth", "broker-1")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            start_broker_node(self.root / "x", key_file, host, port, "earth", "Bad Name")


if __name__ == "__main__":
    unittest.main()