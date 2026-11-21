"""Tests for the admin routes of the DMZ, over real HTTP."""

import unittest
from typing import Any

from spaceknowledge.tests.dmz.admin_helpers import Rig, a_rig, latest_code
from spaceknowledge.tests.dmz.helpers import PASSWORD, a_dmz, a_front, call, sign_up


def assert_refusal(test: unittest.TestCase, body: dict[str, Any]) -> None:
    test.assertFalse(body["ok"])
    for key in ("what", "why", "next_step"):
        test.assertTrue(body["refusal"][key], key)


class TestAdminRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.rig: Rig = a_rig(self)

    def post(self, path: str, body: Any = None, token: str | None = None) -> tuple[int, dict[str, Any]]:
        status, parsed, _ = call(self.rig.dmz, "POST", path, {} if body is None else body, token=token)
        return status, parsed

    def sign_in_admin(self) -> str:
        self.post("/admin/code", {"admin": "root"})
        status, body = self.post("/admin/login", {"admin": "root", "code": latest_code(self.rig)})
        self.assertEqual(200, status)
        return body["token"]

    def test_asking_for_a_code_gives_the_same_answer_for_every_name(self) -> None:
        known = self.post("/admin/code", {"admin": "root"})
        written = len(self.rig.mailbox.messages)
        unknown = self.post("/admin/code", {"admin": "mallory"})
        self.assertEqual((202, {"ok": True}), known)
        self.assertEqual(known, unknown)
        self.assertEqual(written, len(self.rig.mailbox.messages))

    def test_the_code_logs_in_once_and_gives_a_long_token(self) -> None:
        token = self.sign_in_admin()
        self.assertGreaterEqual(len(token), 32)
        status, body = self.post("/admin/login", {"admin": "root", "code": latest_code(self.rig)})
        self.assertEqual(401, status)
        assert_refusal(self, body)

    def test_a_wrong_code_and_an_unknown_admin_get_the_same_401(self) -> None:
        self.post("/admin/code", {"admin": "root"})
        wrong = self.post("/admin/login", {"admin": "root", "code": "00000000"})
        unknown = self.post("/admin/login", {"admin": "mallory", "code": "00000000"})
        self.assertEqual(401, wrong[0])
        self.assertEqual(wrong, unknown)

    def test_bad_fields_are_a_400(self) -> None:
        for path, body in (("/admin/login", {"admin": "root"}),
                           ("/admin/login", {"admin": "root", "code": 12345678}),
                           ("/admin/login", {"admin": "root", "code": "1", "extra": 1}),
                           ("/admin/code", {}), ("/admin/code", {"admin": 5}),
                           ("/admin/code", {"admin": "root", "role": "x"})):
            with self.subTest(path=path, body=body):
                status, parsed = self.post(path, body)
                self.assertEqual(400, status)
                assert_refusal(self, parsed)

    def test_the_players_and_the_stats_are_listed_for_an_admin(self) -> None:
        sign_up(self.rig.dmz, "ada")
        sign_up(self.rig.dmz, "bob")
        token = self.sign_in_admin()
        self.assertEqual(["ada", "bob"], self.post("/admin/players", {}, token)[1]["players"])
        stats = self.post("/admin/stats", {}, token)[1]["stats"]
        self.assertEqual("broker-1", stats["broker"])
        self.assertEqual(2, stats["registered_players"])

    def test_the_stats_count_what_the_broker_has_done_and_never_name_the_internal_server(self) -> None:
        player = sign_up(self.rig.dmz, "ada")                      # the login joins: 1 line
        call(self.rig.dmz, "POST", "/command", {"line": "inventory"}, token=player)   # 1 more
        token = self.sign_in_admin()
        stats = self.post("/admin/stats", {}, token)[1]["stats"]
        self.assertEqual((2, 0, 0), (stats["requests_served"], stats["pending_operations"],
                                     stats["queue_depth"]))
        self.assertGreaterEqual(stats["latency_ms"]["count"], 2)
        self.assertNotIn("universe", str(stats).lower())

    def test_no_token_or_a_bad_token_is_a_401(self) -> None:
        for path in ("/admin/players", "/admin/stats", "/admin/logout"):
            for token in (None, "not-a-token"):
                with self.subTest(path=path, token=token):
                    status, body = self.post(path, {}, token)
                    self.assertEqual(401, status)
                    assert_refusal(self, body)

    def test_a_customer_token_cannot_use_an_admin_route(self) -> None:
        customer = sign_up(self.rig.dmz, "ada")
        for path in ("/admin/players", "/admin/stats"):
            with self.subTest(path=path):
                self.assertEqual(401, self.post(path, {}, customer)[0])

    def test_an_admin_token_cannot_play_the_game(self) -> None:
        token = self.sign_in_admin()
        status, _, _ = call(self.rig.dmz, "POST", "/command", {"line": "inventory"}, token=token)
        self.assertEqual(401, status)

    def test_logging_out_ends_the_admin_session(self) -> None:
        token = self.sign_in_admin()
        status, body = self.post("/admin/logout", {}, token)
        self.assertEqual((200, True), (status, body["was_logged_in"]))
        self.assertEqual(401, self.post("/admin/players", {}, token)[0])

    def test_a_dmz_built_without_admin_support_has_no_admin_routes(self) -> None:
        front, _ = a_front(self)
        server = a_dmz(self, front)
        status, body, _ = call(server, "POST", "/admin/login", {"admin": "root", "code": "1"})
        self.assertEqual(404, status)
        assert_refusal(self, body)

    def test_bad_arguments_are_refused(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            from spaceknowledge.dmz.http_adapter import DmzServer
            DmzServer(self.rig.front, admin="admin")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()