"""The Broker's side of the socket: a UniverseChannel that talks to a listener."""

import socket
import threading
from typing import BinaryIO

from spaceknowledge.common.messages import Request, Response
from spaceknowledge.transport.channel import UniverseChannel
from spaceknowledge.transport.server_auth import ServerAuthError, ServerIdentity
from spaceknowledge.transport.wire import (
    WireError,
    read_message,
    request_to_wire,
    response_from_wire,
    text_field,
    write_message,
)


class _Dropped(Exception):
    """The connection died or spoke nonsense. Internal: it is never raised
    out of `send`, which turns it into a ConnectionError."""


class SocketChannel(UniverseChannel):
    """Same contract as ThreadedChannel, so the Broker does not change.

    Connects on the first send, proves it holds the shared key (and checks the
    Universe does too), and keeps the connection. If a connection that worked
    before turns out to be dead, it reconnects ONCE and resends: safe, because
    the Universe answers a repeated op_id from memory.
    """

    def __init__(
        self,
        host: str,
        port: int,
        identity: ServerIdentity,
        timeout: float = 5.0,
        server_name: str = "universe",
    ) -> None:
        if not host:
            raise ValueError("host must not be empty")
        if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
            raise ValueError("port must be a whole number from 1 to 65535")
        if not isinstance(identity, ServerIdentity):
            raise TypeError(f"identity must be a ServerIdentity, not {type(identity).__name__}")
        if timeout <= 0:
            raise ValueError("timeout must be more than 0 seconds")
        self._host = host
        self._port = port
        self._identity = identity
        self._timeout = timeout
        self._server_name = server_name
        self._sock: socket.socket | None = None
        self._rfile: BinaryIO | None = None
        self._lock = threading.Lock()  # one conversation on the connection at a time

    def send(self, request: Request) -> Response:
        if not isinstance(request, Request):
            raise TypeError(f"request must be a Request, not {type(request).__name__}")
        with self._lock:
            reused = self._sock is not None
            try:
                return self._exchange(request)
            except _Dropped as first:
                self._close_connection()
                if not reused:
                    raise ConnectionError(str(first)) from None
            try:
                return self._exchange(request)
            except _Dropped as second:
                self._close_connection()
                raise ConnectionError(str(second)) from None

    def close(self) -> None:
        """Close the connection. The next send connects again."""
        with self._lock:
            self._close_connection()

    def _exchange(self, request: Request) -> Response:
        if self._sock is None or self._rfile is None:
            self._connect()
        assert self._sock is not None and self._rfile is not None
        try:
            write_message(self._sock.sendall, request_to_wire(request))
            reply = read_message(self._rfile)
        except TimeoutError:
            self._close_connection()  # a late reply would confuse the next request
            raise
        except (OSError, WireError) as problem:
            raise _Dropped(f"the connection to the Universe failed ({problem})") from None
        if reply is None:
            raise _Dropped("the Universe closed the connection")
        try:
            response = response_from_wire(reply)
        except WireError as problem:
            raise _Dropped(f"the Universe sent a bad reply ({problem})") from None
        if response.op_id != request.op_id:
            raise _Dropped("the Universe answered a different request")
        return response

    def _connect(self) -> None:
        try:
            sock = socket.create_connection((self._host, self._port), timeout=self._timeout)
        except OSError as problem:
            raise ConnectionError(
                f"cannot reach the Universe at {self._host}:{self._port} ({problem})"
            ) from None
        rfile = sock.makefile("rb")
        try:
            self._handshake(sock, rfile)
        except (ServerAuthError, TimeoutError):
            self._discard(sock, rfile)
            raise
        except WireError as problem:
            self._discard(sock, rfile)
            raise ServerAuthError(f"the handshake with the Universe failed ({problem})") from None
        except OSError as problem:
            self._discard(sock, rfile)
            raise ConnectionError(f"the handshake with the Universe failed ({problem})") from None
        self._sock, self._rfile = sock, rfile

    def _handshake(self, sock: socket.socket, rfile: BinaryIO) -> None:
        challenge = read_message(rfile)
        if challenge is None:
            raise ServerAuthError("the Universe closed the connection before the handshake")
        server_nonce = text_field(challenge, "nonce", "the challenge")
        my_nonce = self._identity.new_nonce()
        write_message(sock.sendall, {
            "name": self._identity.name,
            "nonce": my_nonce,
            "proof": self._identity.prove(my_nonce, server_nonce),
        })
        answer = read_message(rfile)
        if answer is None:
            raise ServerAuthError("the Universe did not accept this server's proof")
        name = text_field(answer, "name", "the answer")
        proof = text_field(answer, "proof", "the answer")
        if name != self._server_name or not self._identity.verify(
            name, my_nonce, server_nonce, proof
        ):
            raise ServerAuthError("the Universe could not prove it holds the shared key")

    def _close_connection(self) -> None:
        sock, rfile = self._sock, self._rfile
        self._sock = self._rfile = None
        if sock is not None and rfile is not None:
            self._discard(sock, rfile)

    @staticmethod
    def _discard(sock: socket.socket, rfile: BinaryIO) -> None:
        for resource in (rfile, sock):
            try:
                resource.close()
            except OSError:
                pass