"""Tests for AdminClient: a real DMZ over real HTTP, and a stub for bad replies."""

import threading
import unittest

from spaceknowledge.client.admin_client import AdminClient
from spaceknowledge.client.http_client import SessionEnded
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.tests.client.test_game_client import StubServer
from spaceknowledge.tests.dmz.admin_helpers import a_rig, latest_code
from spaceknowledge.tests.dmz.helpers import WAIT, sign_up


def a_stub(test: unittest.TestCase, body: bytes, status: int = 200) -> AdminClient:
    server = StubServer(status, body, None)
    threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True).start()
    test.addCleanup(server.server_close)
    test.addCleanup(server.shutdown)
    return AdminClient("127.0.0.1", server.server_address[1], WAIT)


class TestAgainstARealDmz(unittest.TestCase):
    def setUp(self) -> None:
        self.rig = a_rig(self)
        host, port = self.rig.dmz.address
        self.client = AdminClient(host, port, timeout=WAIT)

    def sign_in(self) -> str:
        self.assertIsNone(self.client.request_code("root"))
        token = self.client.login("root", latest_code(self.rig))
        assert isinstance(token, str), token
        return token

    def test_the_whole_admin_session(self) -> None:
        sign_up(self.rig.dmz, "ada")
        token = self.sign_in()
        self.assertEqual(["ada"], self.client.players(token))
        self.assertEqual("broker-1", self.client.stats(token)["broker"])
        self.assertTrue(self.client.logout(token))
        self.assertFalse(self.client.logout(token))

    def test_a_wrong_code_is_a_refusal_object(self) -> None:
        self.client.request_code("root")
        result = self.client.login("root", "00000000")
        self.assertIsInstance(result, Refusal)
        self.assertTrue(result.what and result.why and result.next_step)

    def test_a_dead_token_raises_session_ended(self) -> None:
        for call in (self.client.players, self.client.stats):
            with self.subTest(call=call.__name__):
                with self.assertRaises(SessionEnded):
                    call("not-a-token")

    def test_a_customer_token_ends_the_admin_session_too(self) -> None:
        customer = sign_up(self.rig.dmz, "ada")
        with self.assertRaises(SessionEnded):
            self.client.players(customer)

    def test_a_server_that_is_gone_is_a_connection_error(self) -> None:
        self.rig.dmz.stop()
        with self.assertRaises(ConnectionError):
            self.client.request_code("root")


class TestBadReplies(unittest.TestCase):
    def test_a_players_reply_that_cannot_be_trusted_is_a_connection_error(self) -> None:
        for body in (b'{"ok": true}', b'{"ok": true, "players": "ada"}',
                     b'{"ok": true, "players": [1]}', b'{"ok": true, "players": [""]}',
                     b"not json"):
            with self.subTest(body=body):
                with self.assertRaises(ConnectionError):
                    a_stub(self, body).players("tok")

    def test_a_stats_reply_that_cannot_be_trusted_is_a_connection_error(self) -> None:
        deep = b'{"ok": true, "stats": {"a": {"b": {"c": {"d": 1}}}}}'
        for body in (b'{"ok": true}', b'{"ok": true, "stats": [1]}',
                     b'{"ok": true, "stats": {"a": [1]}}', deep):
            with self.subTest(body=body):
                with self.assertRaises(ConnectionError):
                    a_stub(self, body).stats("tok")

    def test_a_refusal_that_is_not_a_401_is_a_broken_reply_not_a_session_end(self) -> None:
        body = b'{"ok": false, "refusal": {"what": "a", "why": "b", "next_step": "c"}}'
        with self.assertRaises(ConnectionError):
            a_stub(self, body, status=400).players("tok")

    def test_a_logout_reply_is_checked(self) -> None:
        self.assertTrue(a_stub(self, b'{"ok": true, "was_logged_in": true}').logout("tok"))
        with self.assertRaises(ConnectionError):
            a_stub(self, b'{"ok": true, "was_logged_in": 1}').logout("tok")


class TestArguments(unittest.TestCase):
    def test_bad_arguments_are_refused(self) -> None:
        client = AdminClient("127.0.0.1", 9)
        for call in (lambda: client.request_code(5), lambda: client.login("a", 5),
                     lambda: client.players(5), lambda: client.stats(5), lambda: client.logout(5)):
            with self.assertRaisesRegex(TypeError, "must be"):
                call()  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            client.players("has space")


if __name__ == "__main__":
    unittest.main()