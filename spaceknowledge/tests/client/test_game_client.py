"""Tests for GameClient: a real DMZ over real HTTP, and a stub for bad replies."""

import socketserver
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from spaceknowledge.client.game_client import MAX_REPLY, GameClient, SessionEnded
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.tests.dmz.helpers import PASSWORD, WAIT, a_dmz, a_front


class _StubHandler(BaseHTTPRequestHandler):
    server: "StubServer"

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.server.hold is not None:
            self.server.hold.wait(WAIT)
        try:
            self.send_response(self.server.status)
            self.send_header("Content-Length", str(len(self.server.body)))
            self.end_headers()
            self.wfile.write(self.server.body)
        except OSError:
            pass  # the client gave up, which some tests do on purpose

    do_GET = do_POST

    def log_message(self, fmt: str, *args: object) -> None:
        pass


class StubServer(ThreadingHTTPServer):
    """Answers every request with a fixed status and body."""

    daemon_threads = True
    block_on_close = False

    def __init__(self, status: int, body: bytes, hold: threading.Event | None) -> None:
        self.status, self.body, self.hold = status, body, hold
        super().__init__(("127.0.0.1", 0), _StubHandler)

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)  # skip the slow host-name lookup


def a_stub(test: unittest.TestCase, body: bytes, status: int = 200,
           hold: threading.Event | None = None, timeout: float = WAIT) -> GameClient:
    server = StubServer(status, body, hold)
    threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05),
                     daemon=True).start()
    test.addCleanup(server.server_close)
    test.addCleanup(server.shutdown)
    if hold is not None:
        test.addCleanup(hold.set)  # runs first, so no handler is left waiting
    return GameClient("127.0.0.1", server.server_address[1], timeout)


class TestAgainstARealDmz(unittest.TestCase):
    def setUp(self) -> None:
        front, _ = a_front(self)
        self.server = a_dmz(self, front)
        host, port = self.server.address
        self.client = GameClient(host, port, timeout=WAIT)

    def sign_in(self, name: str = "ada") -> str:
        self.assertIsNone(self.client.register(name, PASSWORD))
        token = self.client.login(name, PASSWORD)
        assert isinstance(token, str), token
        return token

    def test_register_login_command_and_logout(self) -> None:
        token = self.sign_in()
        self.assertEqual("You mine 3 iron.", self.client.command(token, "mine iron 3"))
        self.assertEqual("You are carrying: torch\nResources: iron 3",
                         self.client.command(token, "inventory"))
        self.assertTrue(self.client.logout(token))
        self.assertFalse(self.client.logout(token))

    def test_refusals_arrive_as_refusal_objects_with_three_parts(self) -> None:
        self.sign_in()
        for result in (self.client.register("ada", PASSWORD),
                       self.client.register("bob", "short"),
                       self.client.login("ada", "wrong password")):
            with self.subTest(result=result):
                self.assertIsInstance(result, Refusal)
                self.assertTrue(result.what and result.why and result.next_step)

    def test_a_dead_token_raises_session_ended_with_the_reason(self) -> None:
        with self.assertRaises(SessionEnded) as caught:
            self.client.command("not-a-token", "look")
        self.assertIn("log in", caught.exception.refusal.next_step)

    def test_a_refusal_by_the_game_is_just_text(self) -> None:
        token = self.sign_in()
        self.assertIn("Why:", self.client.command(token, "juggle"))

    def test_a_line_the_server_refuses_as_a_bad_request_does_not_end_the_session(self) -> None:
        token = self.sign_in()
        self.assertIn("Refused", self.client.command(token, "x" * 300))
        self.assertIn("carrying", self.client.command(token, "inventory"))

    def test_a_server_that_is_gone_is_a_connection_error(self) -> None:
        self.server.stop()
        with self.assertRaises(ConnectionError):
            self.client.login("ada", PASSWORD)


class TestBadReplies(unittest.TestCase):
    def test_a_login_reply_that_cannot_be_trusted_is_a_connection_error(self) -> None:
        bad = [b"not json", b"[1]", b'{"nope": 1}', b'{"ok": "yes"}', b'{"ok": false}',
               b'{"ok": false, "refusal": {"what": "a"}}', b'{"ok": true}',
               b'{"ok": true, "token": ""}', b'{"ok": true, "token": 5}',
               b'{"ok": true, "token": "has space"}', b"x" * (MAX_REPLY + 10)]
        for body in bad:
            with self.subTest(body=body[:30]):
                with self.assertRaises(ConnectionError):
                    a_stub(self, body).login("ada", PASSWORD)

    def test_a_command_reply_that_cannot_be_trusted_is_a_connection_error(self) -> None:
        for body in (b'{"ok": true}', b'{"ok": true, "reply": 5}'):
            with self.subTest(body=body):
                with self.assertRaises(ConnectionError):
                    a_stub(self, body).command("tok", "look")

    def test_a_logout_reply_is_checked_too(self) -> None:
        self.assertTrue(a_stub(self, b'{"ok": true, "was_logged_in": true}').logout("tok"))
        with self.assertRaises(ConnectionError):
            a_stub(self, b'{"ok": true, "was_logged_in": "yes"}').logout("tok")

    def test_a_reply_that_never_comes_times_out_as_a_connection_error(self) -> None:
        client = a_stub(self, b'{"ok": true}', hold=threading.Event(), timeout=0.3)
        with self.assertRaises(ConnectionError):
            client.login("ada", PASSWORD)


class TestArguments(unittest.TestCase):
    def test_bad_arguments_are_refused(self) -> None:
        for host, port, timeout in (("", 80, 5.0), ("h", 0, 5.0), ("h", 70000, 5.0),
                                    ("h", True, 5.0), ("h", 80, 0)):
            with self.subTest(host=host, port=port, timeout=timeout):
                with self.assertRaises(ValueError):
                    GameClient(host, port, timeout)  # type: ignore[arg-type]
        client = GameClient("127.0.0.1", 9)
        for call in (lambda: client.register(5, "x"), lambda: client.login("a", 5),
                     lambda: client.command(5, "look"), lambda: client.command("tok", 5),
                     lambda: client.logout(5)):
            with self.assertRaisesRegex(TypeError, "must be"):
                call()  # type: ignore[arg-type]
        for token in ("", "has space", "x" * 200):
            with self.subTest(token=token[:10]):
                with self.assertRaises(ValueError):
                    client.command(token, "look")


if __name__ == "__main__":
    unittest.main()