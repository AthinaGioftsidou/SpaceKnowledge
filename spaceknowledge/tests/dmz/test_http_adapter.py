"""Tests for the DMZ: real HTTP, on a port the operating system picks."""

import socket
import unittest
from typing import Any

from spaceknowledge.app.front import Front
from spaceknowledge.dmz.http_adapter import DmzServer
from spaceknowledge.tests.dmz.helpers import (
    PASSWORD,
    WAIT,
    a_dmz,
    a_front,
    call,
    header_only_call,
    sign_up,
)
from spaceknowledge.tests.transport.helpers import in_thread

LOGGER = "spaceknowledge.dmz.http_adapter"


class LostFront(Front):
    """A Front whose login and commands fail the way a lost connection does."""

    def login(self, username: str, password: str):  # type: ignore[no-untyped-def]
        raise ConnectionError("cannot reach the Universe at 127.0.0.1:7400")

    def command(self, token: str, line: str, timeout: float = 5.0):  # type: ignore[no-untyped-def]
        raise ConnectionError("cannot reach the Universe at 127.0.0.1:7400")


def assert_refusal(test: unittest.TestCase, body: dict[str, Any]) -> None:
    test.assertFalse(body["ok"])
    for key in ("what", "why", "next_step"):
        test.assertTrue(body["refusal"][key], key)


class TestRouting(unittest.TestCase):
    def setUp(self) -> None:
        front, _ = a_front(self)
        self.server = a_dmz(self, front)

    def test_health_answers_without_logging_in(self) -> None:
        status, body, _ = call(self.server, "GET", "/health")
        self.assertEqual((200, {"ok": True}), (status, body))

    def test_unknown_paths_and_wrong_methods_are_a_404_with_three_parts(self) -> None:
        for method, path in (("GET", "/nowhere"), ("POST", "/nowhere"),
                             ("GET", "/login"), ("GET", "/command"), ("POST", "/health")):
            with self.subTest(method=method, path=path):
                status, body, _ = call(self.server, method, path, {} if method == "POST" else None)
                self.assertEqual(404, status)
                assert_refusal(self, body)


class TestRegisterAndLogin(unittest.TestCase):
    def setUp(self) -> None:
        front, _ = a_front(self)
        self.server = a_dmz(self, front)

    def post(self, path: str, body: Any) -> tuple[int, dict[str, Any]]:
        status, parsed, _ = call(self.server, "POST", path, body)
        return status, parsed

    def test_a_registered_player_logs_in_and_gets_a_long_token(self) -> None:
        self.assertEqual(201, self.post("/register", {"username": "ada", "password": PASSWORD})[0])
        status, body = self.post("/login", {"username": "ada", "password": PASSWORD})
        self.assertEqual(200, status)
        self.assertGreaterEqual(len(body["token"]), 32)

    def test_a_taken_name_and_a_bad_password_are_a_400_with_three_parts(self) -> None:
        self.post("/register", {"username": "ada", "password": PASSWORD})
        for body in ({"username": "ada", "password": PASSWORD},
                     {"username": "bob", "password": "short"},
                     {"username": "b", "password": PASSWORD}):
            with self.subTest(body=body):
                status, parsed = self.post("/register", body)
                self.assertEqual(400, status)
                assert_refusal(self, parsed)

    def test_a_wrong_password_is_a_401_with_no_token(self) -> None:
        self.post("/register", {"username": "ada", "password": PASSWORD})
        status, body = self.post("/login", {"username": "ada", "password": "wrong password"})
        self.assertEqual(401, status)
        self.assertNotIn("token", body)
        assert_refusal(self, body)

    def test_the_password_is_never_sent_back(self) -> None:
        status, body = self.post("/register", {"username": "ab", "password": PASSWORD})
        self.assertNotIn(PASSWORD, str(body))

    def test_too_many_wrong_passwords_pause_the_name_even_for_the_right_one(self) -> None:
        self.post("/register", {"username": "ada", "password": PASSWORD})
        for _ in range(5):
            self.assertEqual(401, self.post("/login", {"username": "ada", "password": "wrong password"})[0])
        status, body = self.post("/login", {"username": "ada", "password": PASSWORD})
        self.assertEqual(401, status)
        self.assertIn("paused", body["refusal"]["why"])

    def test_bad_fields_are_a_400(self) -> None:
        for body in ({"username": "ada"}, {"password": PASSWORD},
                     {"username": "ada", "password": 12345678},
                     {"username": ["ada"], "password": PASSWORD},
                     {"username": "ada", "password": PASSWORD, "admin": True}):
            with self.subTest(body=body):
                status, parsed = self.post("/login", body)
                self.assertEqual(400, status)
                assert_refusal(self, parsed)


class TestCommands(unittest.TestCase):
    def setUp(self) -> None:
        front, self.deposits = a_front(self)
        self.server = a_dmz(self, front)

    def command(self, token: str | None, line: str) -> tuple[int, dict[str, Any]]:
        status, body, _ = call(self.server, "POST", "/command", {"line": line}, token=token)
        return status, body

    def test_a_player_can_mine_and_see_the_inventory(self) -> None:
        token = sign_up(self.server)
        status, body = self.command(token, "mine iron 3")
        self.assertEqual((200, "You mine 3 iron."), (status, body["reply"]))
        status, body = self.command(token, "inventory")
        self.assertEqual(200, status)
        self.assertEqual("You are carrying: torch\nResources: iron 3", body["reply"])
        self.assertEqual(97, self.deposits.available("earth", "iron"))

    def test_a_refused_game_command_is_a_200_with_the_reasons_in_the_reply(self) -> None:
        token = sign_up(self.server)
        status, body = self.command(token, "juggle")
        self.assertEqual(200, status)
        self.assertIn("Why:", body["reply"])

    def test_no_token_or_a_bad_token_is_a_401_and_changes_nothing(self) -> None:
        for token in (None, "not-a-token"):
            with self.subTest(token=token):
                status, body = self.command(token, "mine iron 3")
                self.assertEqual(401, status)
                assert_refusal(self, body)
        self.assertEqual(100, self.deposits.available("earth", "iron"))

    def test_the_player_comes_from_the_token_not_the_body(self) -> None:
        token = sign_up(self.server)
        status, body, _ = call(self.server, "POST", "/command",
                               {"line": "inventory", "player": "bob"}, token=token)
        self.assertEqual(400, status)

    def test_two_players_have_separate_bags(self) -> None:
        ada, bob = sign_up(self.server, "ada"), sign_up(self.server, "bob")
        self.command(ada, "mine iron 2")
        self.assertEqual("You are carrying: torch", self.command(bob, "inventory")[1]["reply"])
        self.assertIn("iron 2", self.command(ada, "inventory")[1]["reply"])

    def test_logging_out_ends_the_session(self) -> None:
        token = sign_up(self.server)
        status, body, _ = call(self.server, "POST", "/logout", {}, token=token)
        self.assertEqual((200, True), (status, body["was_logged_in"]))
        self.assertEqual(401, self.command(token, "inventory")[0])
        self.assertFalse(call(self.server, "POST", "/logout", {}, token=token)[1]["was_logged_in"])

    def test_logging_out_needs_a_token(self) -> None:
        self.assertEqual(401, call(self.server, "POST", "/logout", {})[0])

    def test_a_line_that_is_too_long_or_has_control_characters_is_a_400(self) -> None:
        token = sign_up(self.server)
        for line in ("x" * 201, "mine\x00iron", "mine\niron"):
            with self.subTest(line=line[:10]):
                self.assertEqual(400, self.command(token, line)[0])


class TestBoundary(unittest.TestCase):
    def setUp(self) -> None:
        front, _ = a_front(self)
        self.server = a_dmz(self, front)

    def test_the_wrong_content_type_is_a_415(self) -> None:
        status, body, _ = call(self.server, "POST", "/login", raw=b"{}", content_type="text/plain")
        self.assertEqual(415, status)
        assert_refusal(self, body)

    def test_a_body_that_is_not_a_json_object_is_a_400(self) -> None:
        for raw in (b"not json", b"[1]", b"", b"\xff"):
            with self.subTest(raw=raw):
                status, body, _ = call(self.server, "POST", "/login", raw=raw)
                self.assertEqual(400, status)
                assert_refusal(self, body)

    def test_a_body_that_claims_to_be_huge_is_refused_before_it_is_read(self) -> None:
        status, body = header_only_call(
            self.server, "/login",
            {"Content-Type": "application/json", "Content-Length": "100000"})
        self.assertEqual(413, status)
        assert_refusal(self, body)

    def test_a_bad_content_length_is_a_400(self) -> None:
        for length in ("abc", "-5", "99999999999", "1.5"):
            with self.subTest(length=length):
                status, _ = header_only_call(
                    self.server, "/login",
                    {"Content-Type": "application/json", "Content-Length": length})
                self.assertEqual(400, status)

    def test_a_client_that_stops_sending_is_cut_off_with_a_408(self) -> None:
        front, _ = a_front(self)
        server = a_dmz(self, front, request_timeout=0.3)
        sock = socket.create_connection(server.address, timeout=WAIT)
        self.addCleanup(sock.close)
        sock.sendall(b"POST /login HTTP/1.0\r\nContent-Type: application/json\r\n"
                     b"Content-Length: 50\r\n\r\n{")
        first_line = sock.recv(4096).split(b"\r\n")[0]
        self.assertIn(b" 408 ", first_line)


class TestTrustBoundary(unittest.TestCase):
    def test_the_internal_server_is_never_named_even_when_the_game_cannot_reach_it(self) -> None:
        front, _ = a_front(self, lost=True)
        server = a_dmz(self, front)
        call(server, "POST", "/register", {"username": "ada", "password": PASSWORD})
        token = call(server, "POST", "/login", {"username": "ada", "password": PASSWORD})[1]["token"]
        status, body, _ = call(server, "POST", "/command", {"line": "mine iron 1"}, token=token)
        self.assertEqual(200, status)
        self.assertIn("game world did not answer", body["reply"])
        self.assertNotIn("universe", str(body).lower())

    def test_a_lost_connection_is_a_503_that_leaks_no_address_or_name(self) -> None:
        front, _ = a_front(self, front_class=LostFront)
        server = a_dmz(self, front)
        for path, body, token in (("/login", {"username": "ada", "password": PASSWORD}, None),
                                  ("/command", {"line": "look"}, "any-token")):
            with self.subTest(path=path):
                status, parsed, _ = call(server, "POST", path, body, token=token)
                self.assertEqual(503, status)
                assert_refusal(self, parsed)
                text = str(parsed).lower()
                self.assertNotIn("universe", text)
                self.assertNotIn("7400", text)
                self.assertNotIn("127.0.0.1", text)

    def test_the_server_does_not_announce_its_software_version(self) -> None:
        front, _ = a_front(self)
        server = a_dmz(self, front)
        _, _, headers = call(server, "GET", "/health")
        self.assertNotIn("Python", headers.get("Server", ""))
        self.assertEqual("nosniff", headers.get("X-Content-Type-Options"))


class TestOperations(unittest.TestCase):
    def test_every_request_gets_its_own_id_and_is_logged_without_secrets(self) -> None:
        front, _ = a_front(self)
        server = a_dmz(self, front)
        with self.assertLogs(LOGGER, level="INFO") as logs:
            token = sign_up(server)
            _, _, first = call(server, "POST", "/command", {"line": "inventory"}, token=token)
            _, _, second = call(server, "GET", "/health")
        text = "\n".join(logs.output)
        self.assertNotEqual(first["X-Request-Id"], second["X-Request-Id"])
        self.assertIn(first["X-Request-Id"], text)
        self.assertIn("/login", text)
        self.assertIn("-> 200", text)
        self.assertNotIn(PASSWORD, text)
        self.assertNotIn(token, text)


class TestConcurrency(unittest.TestCase):
    def test_many_clients_at_once_lose_nothing(self) -> None:
        front, deposits = a_front(self)
        server = a_dmz(self, front)
        statuses: list[int] = []

        def player(number: int) -> None:
            token = sign_up(server, f"player{number}")
            for _ in range(5):
                statuses.append(
                    call(server, "POST", "/command", {"line": "mine iron 1"}, token=token)[0])

        workers = [in_thread(lambda n=n: player(n)) for n in range(6)]
        for worker in workers:
            worker.join(WAIT * 3)
        self.assertEqual([200] * 30, statuses)
        self.assertEqual(70, deposits.available("earth", "iron"))


class TestLifecycle(unittest.TestCase):
    def test_it_listens_on_a_port_the_system_chose_and_stopping_closes_it(self) -> None:
        front, _ = a_front(self)
        server = DmzServer(front)
        self.addCleanup(server.stop)
        server.start()
        self.assertGreater(server.address[1], 0)
        self.assertEqual(200, call(server, "GET", "/health")[0])
        server.stop()
        server.stop()
        with self.assertRaises(OSError):
            call(server, "GET", "/health")

    def test_it_can_only_be_started_once(self) -> None:
        front, _ = a_front(self)
        server = a_dmz(self, front)
        with self.assertRaises(RuntimeError):
            server.start()
        server.stop()
        with self.assertRaises(RuntimeError):
            server.start()

    def test_bad_arguments_are_refused(self) -> None:
        front, _ = a_front(self)
        with self.assertRaisesRegex(TypeError, "must be"):
            DmzServer("front")  # type: ignore[arg-type]
        for kwargs in ({"request_timeout": 0}, {"host": ""}, {"port": -1}, {"port": 70000}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    DmzServer(front, **kwargs)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()