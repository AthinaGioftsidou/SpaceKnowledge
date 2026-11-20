"""The Universe on a socket: many Brokers connect, and one request at a time
changes the world."""

import logging
import socket
import socketserver
import threading
from collections.abc import Callable
from typing import BinaryIO

from spaceknowledge.transport.server_auth import ServerIdentity
from spaceknowledge.transport.wire import (
    WireError,
    read_message,
    request_from_wire,
    response_to_wire,
    text_field,
    write_message,
)
from spaceknowledge.universe.universe import Universe

# Where these lines go is decided once, by the program that opens the log.
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

Send = Callable[[bytes], object]


class _Handler(socketserver.StreamRequestHandler):
    """One connection. Runs on its own thread, made by the server."""

    server: "_Server"

    def handle(self) -> None:
        self.server.listener.serve_connection(self.request, self.rfile, self.wfile.write)


class _Server(socketserver.ThreadingTCPServer):
    # Connection threads are daemons: they end when their socket is closed, and
    # `UniverseListener.stop` closes every socket.
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], listener: "UniverseListener") -> None:
        self.listener = listener
        super().__init__(address, _Handler)


class UniverseListener:
    """Accepts Broker connections and answers their requests.

    THREADS. One thread accepts connections. Each connection has its own
    thread, which reads and writes the network concurrently. Only
    `universe.handle` runs under the lock, so the world is changed by one
    request at a time while the network work overlaps.

    TRUST. Every connection must pass a mutual handshake with the shared server
    key before a single request is read. Only listens on loopback by default.
    """

    def __init__(
        self,
        universe: Universe,
        identity: ServerIdentity,
        host: str = "127.0.0.1",
        port: int = 0,
        peers: tuple[str, ...] = ("broker",),
        handshake_timeout: float = 5.0,
    ) -> None:
        if not isinstance(universe, Universe):
            raise TypeError(f"universe must be a Universe, not {type(universe).__name__}")
        if not isinstance(identity, ServerIdentity):
            raise TypeError(f"identity must be a ServerIdentity, not {type(identity).__name__}")
        if not peers or any(not name for name in peers) or identity.name in peers:
            raise ValueError("peers must be non-empty names other than this server's own")
        if handshake_timeout <= 0:
            raise ValueError("handshake_timeout must be more than 0 seconds")
        self._universe = universe
        self._identity = identity
        self._peers = frozenset(peers)
        self._handshake_timeout = handshake_timeout
        self._lock = threading.Lock()  # serialises world changes only
        self._connections: set[socket.socket] = set()
        self._connections_lock = threading.Lock()
        self._stopped = False
        self._thread: threading.Thread | None = None
        self._server = _Server((host, port), self)  # binds now: port 0 is chosen here

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    def start(self) -> None:
        if self._thread is not None or self._stopped:
            raise RuntimeError("the Universe listener can only be started once")
        self._thread = threading.Thread(
            target=lambda: self._server.serve_forever(poll_interval=0.05),
            name="universe-listener",
        )
        self._thread.start()
        log.info("listening on %s:%d", *self.address)

    def stop(self, timeout: float = 5.0) -> None:
        """Stop accepting, end every open connection, and wait for the accept
        thread. Harmless to call twice."""
        with self._connections_lock:
            already = self._stopped
            self._stopped = True
        if already:
            return
        if self._thread is not None:
            self._server.shutdown()
        self._server.server_close()
        self.disconnect_all()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                raise RuntimeError(f"the listener thread did not stop within {timeout} seconds")
        log.info("stopped")

    def disconnect_all(self) -> None:
        """End every open connection. The listener keeps accepting new ones."""
        with self._connections_lock:
            sockets = list(self._connections)
        for sock in sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)  # wakes a thread blocked on read
            except OSError:
                pass

    def serve_connection(self, sock: socket.socket, rfile: BinaryIO, send: Send) -> None:
        """Runs on the connection's own thread."""
        if not self._register(sock):
            return
        try:
            sock.settimeout(self._handshake_timeout)  # a silent client cannot hold a thread
            peer = self._authenticate(rfile, send)
            if peer is None:
                return
            sock.settimeout(None)
            self._serve_requests(peer, rfile, send)
        except (OSError, WireError) as problem:
            log.warning("a connection ended: %s", problem)
        except Exception:
            # The top of a connection thread, so the one place a broad catch
            # belongs: log it, and end only this connection.
            log.exception("a connection failed")
        finally:
            with self._connections_lock:
                self._connections.discard(sock)

    def _register(self, sock: socket.socket) -> bool:
        with self._connections_lock:
            if self._stopped:
                return False
            self._connections.add(sock)
            return True

    def _authenticate(self, rfile: BinaryIO, send: Send) -> str | None:
        """Mutual handshake. The peer's name, or None if it failed."""
        nonce = self._identity.new_nonce()
        write_message(send, {"nonce": nonce})
        hello = read_message(rfile)
        if hello is None:
            return None
        try:
            name = text_field(hello, "name", "the hello")
            peer_nonce = text_field(hello, "nonce", "the hello")
            proof = text_field(hello, "proof", "the hello")
        except WireError:
            log.warning("a connection was rejected: it sent no valid hello")
            return None
        if name not in self._peers or not self._identity.verify(name, nonce, peer_nonce, proof):
            log.warning("a connection claiming to be %r was rejected", name[:40])
            return None
        write_message(send, {"name": self._identity.name,
                             "proof": self._identity.prove(nonce, peer_nonce)})
        log.info("%s connected", name)
        return name

    def _serve_requests(self, peer: str, rfile: BinaryIO, send: Send) -> None:
        while True:
            message = read_message(rfile)
            if message is None:
                log.info("%s disconnected", peer)
                return
            request = request_from_wire(message)
            try:
                with self._lock:
                    response = self._universe.handle(request)
            except Exception:
                # Ends this connection. The Broker sees a lost connection, keeps
                # the operation pending, and recovers it with the same op_id.
                log.exception("%s: request %s (%s %s by %s) failed", peer, request.op_id,
                              request.action, request.item_id, request.player_id)
                return
            log.info("%s: %s %s by %s [%s]: %s", peer, request.action, request.item_id,
                     request.player_id, request.op_id, "ok" if response.ok else "refused")
            write_message(send, response_to_wire(response))