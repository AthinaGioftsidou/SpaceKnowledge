"""ADAPTER and DMZ server. HTTP in, Front calls out; Front answers in, JSON out.

Nothing here decides what the game does. It translates, checks the request
against the boundary in http_protocol, and hides everything internal. The
Broker and the Universe do not know they are being called over HTTP.
"""

import json
import logging
import secrets
import socketserver
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from spaceknowledge.app.front import Front
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.dmz.http_protocol import (
    MAX_BODY,
    MAX_LINE,
    MAX_NAME,
    MAX_PASSWORD_FIELD,
    HttpProblem,
    bearer_token,
    only_fields,
    parse_json_body,
    problem,
    refusal_body,
    scrub,
    text_field,
)

# Where these lines go is decided once, by the program that opens the log.
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

Reply = tuple[int, dict[str, Any]]


class _Handler(BaseHTTPRequestHandler):
    """One request. HTTP/1.0 on purpose: the connection closes after each
    answer, so an unread body can never be mistaken for the next request."""

    server: "_HttpServer"

    def version_string(self) -> str:
        return "SpaceKnowledge"

    def setup(self) -> None:
        self.timeout = self.server.request_timeout  # a silent client cannot hold a thread
        super().setup()

    def log_message(self, fmt: str, *args: object) -> None:
        """Silenced: every request is logged once, by `_dispatch`."""

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    @property
    def _front(self) -> Front:
        return self.server.front

    def _dispatch(self, method: str) -> None:
        request_id = secrets.token_hex(4)
        started = time.monotonic()
        path = self.path.split("?", 1)[0]
        try:
            status, body = self._route(method, path)
        except HttpProblem as refused:
            status, body = refused.status, refusal_body(refused.refusal)
        except OSError as lost:
            # The game (or its storage) could not be reached. Details go to the
            # log only: a client is never told addresses or server names.
            log.warning("[%s] the game could not be reached: %s", request_id, lost)
            status, body = 503, refusal_body(Refusal(
                "handle the request", "the game is not available right now",
                "try again in a moment"))
        except Exception:
            # The top of a request thread, so the one place a broad catch
            # belongs: log it with the request id and answer with a clean 500.
            log.exception("[%s] the request failed", request_id)
            status, body = 500, refusal_body(Refusal(
                "handle the request", "something went wrong inside the game",
                "try again, and tell the administrator if it keeps happening"))
        elapsed = (time.monotonic() - started) * 1000
        # Logged BEFORE answering, so the record exists once the client has its
        # answer. Never the body, the password or the token.
        log.info("%s %r -> %d [%s] %.1f ms", method, path[:60], status, request_id, elapsed)
        self._send(status, body, request_id)

    def _route(self, method: str, path: str) -> Reply:
        if method == "GET":
            if path == "/health":
                return 200, {"ok": True}
            raise self._not_found()
        raw = self._read_body()
        action = self._post_routes().get(path)
        if action is None:
            raise self._not_found()
        body = parse_json_body(raw, self.headers.get("Content-Type", ""))
        return action(body)

    def _post_routes(self) -> dict[str, Callable[[dict[str, Any]], Reply]]:
        """Path to handler: a table, so adding a route is one row."""
        return {
            "/register": self._register,
            "/login": self._login,
            "/logout": self._logout,
            "/command": self._command,
        }

    @staticmethod
    def _not_found() -> HttpProblem:
        return problem(404, "find that page", "there is nothing at that address",
                       "use /health, /register, /login, /logout or /command")

    def _read_body(self) -> bytes:
        text = self.headers.get("Content-Length", "0")
        if not (text.isascii() and text.isdigit() and len(text) <= 9):
            raise problem(400, "read the request", "Content-Length is not a whole number",
                          "send the length of the body in bytes")
        length = int(text)
        if length > MAX_BODY:
            # Decided from the header alone: refusing after reading a huge body
            # would be a delayed acceptance.
            raise problem(413, "read the request", f"the body is larger than {MAX_BODY} bytes",
                          "send a smaller request")
        try:
            return self.rfile.read(length)
        except TimeoutError:
            raise problem(408, "read the request", "the body did not arrive in time",
                          "send the whole request promptly") from None

    def _register(self, body: dict[str, Any]) -> Reply:
        only_fields(body, {"username", "password"})
        refusal = self._front.register(
            text_field(body, "username", MAX_NAME),
            text_field(body, "password", MAX_PASSWORD_FIELD, allow_control=True),
        )
        if refusal is not None:
            raise HttpProblem(400, refusal)
        return 201, {"ok": True}

    def _login(self, body: dict[str, Any]) -> Reply:
        only_fields(body, {"username", "password"})
        result = self._front.login(
            text_field(body, "username", MAX_NAME),
            text_field(body, "password", MAX_PASSWORD_FIELD, allow_control=True),
        )
        if isinstance(result, Refusal):
            raise HttpProblem(401, result)
        return 200, {"ok": True, "token": result}

    def _logout(self, body: dict[str, Any]) -> Reply:
        token = bearer_token(self.headers.get("Authorization"))
        only_fields(body, set())
        return 200, {"ok": True, "was_logged_in": self._front.logout(token)}

    def _command(self, body: dict[str, Any]) -> Reply:
        token = bearer_token(self.headers.get("Authorization"))
        only_fields(body, {"line"})
        result = self._front.command(token, text_field(body, "line", MAX_LINE))
        if isinstance(result, Refusal):
            raise HttpProblem(401, result)
        # A refusal by the GAME is a 200 with the reasons in the text: the
        # request was fine, the world just said no. Only a bad REQUEST is an
        # HTTP error, so clients can tell the two apart.
        return 200, {"ok": True, "reply": scrub(result)}

    def _send(self, status: int, body: dict[str, Any], request_id: str) -> None:
        data = json.dumps(body).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Request-Id", request_id)
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            log.info("[%s] the client went away before the answer", request_id)


class _HttpServer(ThreadingHTTPServer):
    # Request threads are daemons: they end with their connection.
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], front: Front, request_timeout: float) -> None:
        self.front = front
        self.request_timeout = request_timeout
        super().__init__(address, _Handler)

    def server_bind(self) -> None:
        # HTTPServer.server_bind looks up the host's full name, which can take
        # seconds on some machines. We only need the host and port.
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


class DmzServer:
    """The only thing clients can reach. It knows a Front and nothing behind it.

    THREADS: one accept thread, plus one short-lived thread per request. `Front`
    is safe to call from several threads, so requests overlap while the Broker
    thread behind it keeps its own order.
    """

    def __init__(
        self,
        front: Front,
        host: str = "127.0.0.1",
        port: int = 0,
        request_timeout: float = 10.0,
    ) -> None:
        if not isinstance(front, Front):
            raise TypeError(f"front must be a Front, not {type(front).__name__}")
        if not host:
            raise ValueError("host must not be empty")
        if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port < 65536:
            raise ValueError("port must be a whole number from 0 to 65535")
        if request_timeout <= 0:
            raise ValueError("request_timeout must be more than 0 seconds")
        self._lock = threading.Lock()
        self._stopped = False
        self._thread: threading.Thread | None = None
        self._server = _HttpServer((host, port), front, request_timeout)  # binds now

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    def start(self) -> None:
        if self._thread is not None or self._stopped:
            raise RuntimeError("the DMZ server can only be started once")
        self._thread = threading.Thread(
            target=lambda: self._server.serve_forever(poll_interval=0.05), name="dmz"
        )
        self._thread.start()
        log.info("listening on %s:%d", *self.address)

    def stop(self, timeout: float = 5.0) -> None:
        """Stop accepting and release the port. Harmless to call twice."""
        with self._lock:
            already = self._stopped
            self._stopped = True
        if already:
            return
        if self._thread is not None:
            self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                raise RuntimeError(f"the DMZ thread did not stop within {timeout} seconds")
        log.info("stopped")