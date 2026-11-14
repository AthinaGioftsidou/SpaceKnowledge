"""Tests for the server key, the mutual handshake and AuthenticatedChannel."""

import shutil
import tempfile
import unittest
from pathlib import Path

from observatory.common.messages import Request, Response
from observatory.common.refusal import Refusal
from observatory.transport.channel import UniverseChannel
from observatory.transport.server_auth import (
    AuthenticatedChannel,
    CorruptKeyError,
    ServerAuthError,
    ServerIdentity,
    handshake,
    load_or_create_key,
)

KEY = b"k" * 32
OTHER = b"o" * 32


class CountingChannel(UniverseChannel):
    def __init__(self) -> None:
        self.sent: list[Request] = []

    def send(self, request: Request) -> Response:
        self.sent.append(request)
        return Response(request.op_id)


class TestIdentity(unittest.TestCase):
    def test_a_proof_checks_out_for_the_right_signer_and_nonces_only(self) -> None:
        broker, universe = ServerIdentity("broker", KEY), ServerIdentity("universe", KEY)
        proof = universe.prove("n-universe", "n-broker")
        self.assertTrue(broker.verify("universe", "n-broker", "n-universe", proof))
        self.assertFalse(broker.verify("broker", "n-broker", "n-universe", proof))
        self.assertFalse(broker.verify("universe", "other", "n-universe", proof))
        self.assertFalse(broker.verify("universe", "n-broker", "n-universe", "x" * 64))
        self.assertFalse(broker.verify("universe", "n-broker", "n-universe", "é"))

    def test_nonces_are_fresh_every_time(self) -> None:
        identity = ServerIdentity("broker", KEY)
        self.assertNotEqual(identity.new_nonce(), identity.new_nonce())

    def test_bad_arguments_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            ServerIdentity("", KEY)
        with self.assertRaises(ValueError):
            ServerIdentity("broker", b"short")
        with self.assertRaisesRegex(TypeError, "must be"):
            ServerIdentity("broker", "not bytes")  # type: ignore[arg-type]


class TestHandshake(unittest.TestCase):
    def test_servers_with_the_same_key_authenticate_each_other(self) -> None:
        self.assertIsNone(handshake(ServerIdentity("broker", KEY), ServerIdentity("universe", KEY)))

    def test_servers_with_different_keys_are_refused_with_all_three_parts(self) -> None:
        refusal = handshake(ServerIdentity("broker", KEY), ServerIdentity("universe", OTHER))
        self.assertIsInstance(refusal, Refusal)
        self.assertIn("Next:", refusal.describe())

    def test_a_server_cannot_pose_as_its_own_peer(self) -> None:
        self.assertIsInstance(
            handshake(ServerIdentity("broker", KEY), ServerIdentity("broker", KEY)), Refusal
        )

    def test_bad_arguments_are_refused(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            handshake("broker", ServerIdentity("universe", KEY))  # type: ignore[arg-type]


class TestAuthenticatedChannel(unittest.TestCase):
    def test_after_the_handshake_requests_pass_through(self) -> None:
        inner = CountingChannel()
        channel = AuthenticatedChannel(
            inner, ServerIdentity("broker", KEY), ServerIdentity("universe", KEY)
        )
        self.assertTrue(channel.send(Request("op1", "mine", "ada", "iron", 1)).ok)
        self.assertEqual(1, len(inner.sent))

    def test_a_wrong_key_means_no_channel_and_nothing_is_sent(self) -> None:
        inner = CountingChannel()
        with self.assertRaises(ServerAuthError):
            AuthenticatedChannel(
                inner, ServerIdentity("broker", KEY), ServerIdentity("universe", OTHER)
            )
        self.assertEqual([], inner.sent)

    def test_an_auth_failure_is_a_connection_error(self) -> None:
        self.assertTrue(issubclass(ServerAuthError, ConnectionError))

    def test_bad_arguments_are_refused(self) -> None:
        good = ServerIdentity("broker", KEY)
        with self.assertRaisesRegex(TypeError, "must be"):
            AuthenticatedChannel("inner", good, ServerIdentity("universe", KEY))  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            AuthenticatedChannel(CountingChannel(), "me", good)  # type: ignore[arg-type]


class TestKeyFile(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = self.directory / "keys" / "server.key"

    def test_a_missing_file_is_created_with_a_random_key(self) -> None:
        key = load_or_create_key(self.path)
        self.assertEqual(32, len(key))
        self.assertTrue(self.path.exists())

    def test_the_same_key_is_read_back_next_time(self) -> None:
        self.assertEqual(load_or_create_key(self.path), load_or_create_key(self.path))

    def test_two_fresh_files_get_different_keys(self) -> None:
        other = self.directory / "other.key"
        self.assertNotEqual(load_or_create_key(self.path), load_or_create_key(other))

    def test_a_file_that_cannot_be_trusted_is_refused(self) -> None:
        self.path.parent.mkdir(parents=True)
        for text in ("", "abc", "z" * 64, "A" * 64, "a" * 63):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="ascii")
                with self.assertRaises(CorruptKeyError):
                    load_or_create_key(self.path)

    def test_a_string_is_refused_where_a_path_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            load_or_create_key("server.key")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()