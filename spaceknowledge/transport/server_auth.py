"""Server to server authentication: a shared key that is NOT a client
credential, and a mutual handshake built on it."""

import hmac
import os
import secrets
from pathlib import Path

from spaceknowledge.common.messages import Request, Response
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.transport.channel import UniverseChannel

MIN_KEY_BYTES = 16
_KEY_BYTES = 32
_HEX = frozenset("0123456789abcdef")


class CorruptKeyError(ValueError):
    """A key file that cannot be trusted, so it was not used."""


class ServerAuthError(ConnectionError):
    """The other server could not prove it holds the shared key."""


def load_or_create_key(path: Path) -> bytes:
    """Read the server key, or create it (readable by this user only).

    Both servers read the same file. It is never stored with the accounts and
    never given to a player.
    """
    if not isinstance(path, Path):
        raise TypeError(f"path must be a Path, not {type(path).__name__}")
    if path.exists():
        try:
            text = path.read_text(encoding="ascii").strip()
        except UnicodeDecodeError:
            raise CorruptKeyError(f"{path.name} is not a key file") from None
        if len(text) != _KEY_BYTES * 2 or not set(text) <= _HEX:
            raise CorruptKeyError(f"{path.name} does not hold a {_KEY_BYTES}-byte hex key")
        return bytes.fromhex(text)
    key = secrets.token_bytes(_KEY_BYTES)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="ascii") as handle:
        handle.write(key.hex())
    return key


class ServerIdentity:
    """A server's name and the shared key. Proves it knows the key without
    ever sending the key."""

    def __init__(self, name: str, key: bytes) -> None:
        if not name:
            raise ValueError("name must not be empty")
        if not isinstance(key, bytes):
            raise TypeError(f"key must be bytes, not {type(key).__name__}")
        if len(key) < MIN_KEY_BYTES:
            raise ValueError(f"key must be at least {MIN_KEY_BYTES} bytes")
        self._name = name
        self._key = key

    @property
    def name(self) -> str:
        return self._name

    @staticmethod
    def new_nonce() -> str:
        """A fresh random challenge, so an old proof cannot be replayed."""
        return secrets.token_hex(16)

    def prove(self, my_nonce: str, peer_nonce: str) -> str:
        """My answer to the peer's challenge, naming me as the signer."""
        return self._mac(self._name, peer_nonce, my_nonce)

    def verify(self, peer_name: str, my_nonce: str, peer_nonce: str, proof: str) -> bool:
        """Is `proof` what `peer_name` would answer to my challenge?"""
        expected = self._mac(peer_name, my_nonce, peer_nonce)
        if not isinstance(proof, str):
            return False
        return hmac.compare_digest(expected.encode("utf-8"), proof.encode("utf-8"))

    def _mac(self, signer: str, challenge: str, answer_nonce: str) -> str:
        message = f"{signer}|{challenge}|{answer_nonce}".encode("utf-8")
        return hmac.new(self._key, message, "sha256").hexdigest()


def handshake(first: ServerIdentity, second: ServerIdentity) -> Refusal | None:
    """Each server proves itself to the other. None if both succeed.

    Run in one process here. With sockets the same four values would travel
    over the wire, and nothing in this function would change.
    """
    for server in (first, second):
        if not isinstance(server, ServerIdentity):
            raise TypeError(f"server must be a ServerIdentity, not {type(server).__name__}")
    if first.name == second.name:
        return Refusal(
            "authenticate the servers",
            f"both servers are called {first.name}",
            "give each server its own name",
        )
    first_nonce, second_nonce = first.new_nonce(), second.new_nonce()
    second_proves = second.prove(second_nonce, first_nonce)
    first_proves = first.prove(first_nonce, second_nonce)
    both = (
        first.verify(second.name, first_nonce, second_nonce, second_proves)
        and second.verify(first.name, second_nonce, first_nonce, first_proves)
    )
    if both:
        return None
    return Refusal(
        "authenticate the servers",
        f"the {first.name} and the {second.name} do not share the same server key",
        "check that both servers read the same key file",
    )


class AuthenticatedChannel(UniverseChannel):
    """A channel that exists only if the two servers authenticated each other.

    Wraps any other channel, so the Broker still sees only UniverseChannel.
    """

    def __init__(self, inner: UniverseChannel, local: ServerIdentity, peer: ServerIdentity) -> None:
        if not isinstance(inner, UniverseChannel):
            raise TypeError(f"inner must be a UniverseChannel, not {type(inner).__name__}")
        if not isinstance(local, ServerIdentity):
            raise TypeError(f"local must be a ServerIdentity, not {type(local).__name__}")
        refusal = handshake(local, peer)
        if refusal is not None:
            raise ServerAuthError(refusal.describe())
        self._inner = inner

    def send(self, request: Request) -> Response:
        return self._inner.send(request)