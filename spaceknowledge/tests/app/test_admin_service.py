"""Tests for AdminService: the server side of every admin action."""

import unittest

from spaceknowledge.app.admin_service import AdminService
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.tests.dmz.admin_helpers import Rig, a_rig, admin_token, latest_code

LOGGER = "spaceknowledge.app.admin_service"


class TestAdminService(unittest.TestCase):
    def setUp(self) -> None:
        self.rig: Rig = a_rig(self)

    def test_the_emailed_code_gives_an_admin_token_that_lists_the_players(self) -> None:
        self.rig.front.register("bob", "correct horse")
        self.rig.front.register("ada", "correct horse")
        token = admin_token(self.rig)
        self.assertEqual(["ada", "bob"], self.rig.admin.players(token))

    def test_a_wrong_code_is_refused_with_three_parts_and_no_token(self) -> None:
        self.rig.admin.request_code("root")
        refusal = self.rig.admin.login("root", "00000000x")
        self.assertIsInstance(refusal, Refusal)
        self.assertTrue(refusal.what and refusal.why and refusal.next_step)

    def test_without_a_valid_admin_token_nothing_is_shown(self) -> None:
        for call in (self.rig.admin.players, self.rig.admin.stats):
            with self.subTest(call=call.__name__):
                self.assertIsInstance(call("not-a-token"), Refusal)

    def test_a_customer_token_is_not_an_admin_token(self) -> None:
        self.rig.front.register("ada", "correct horse")
        customer = self.rig.front.login("ada", "correct horse")
        assert isinstance(customer, str)
        self.assertIsInstance(self.rig.admin.players(customer), Refusal)

    def test_logging_out_ends_the_admin_session(self) -> None:
        token = admin_token(self.rig)
        self.assertTrue(self.rig.admin.logout(token))
        self.assertIsInstance(self.rig.admin.players(token), Refusal)

    def test_the_stats_name_the_broker_and_count_the_players_and_the_queue(self) -> None:
        self.rig.front.register("ada", "correct horse")
        stats = self.rig.admin.stats(admin_token(self.rig))
        self.assertEqual("broker-1", stats["broker"])
        self.assertEqual(1, stats["registered_players"])
        self.assertEqual(0, stats["queue_depth"])
        self.assertIn("latency_ms", stats)

    def test_every_admin_read_is_logged_with_the_admin_name_and_never_the_code(self) -> None:
        token = admin_token(self.rig)
        with self.assertLogs(LOGGER, level="INFO") as logs:
            self.rig.admin.players(token)
            self.rig.admin.stats(token)
        text = "\n".join(logs.output)
        self.assertIn("root", text)
        self.assertIn("players", text)
        self.assertIn("statistics", text)
        self.assertNotIn(latest_code(self.rig), text)

    def test_bad_arguments_are_refused(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            AdminService("gate", self.rig.front, self.rig.server, "b")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            AdminService(self.rig.admin._gate, self.rig.admin._accounts, self.rig.server, "")


if __name__ == "__main__":
    unittest.main()