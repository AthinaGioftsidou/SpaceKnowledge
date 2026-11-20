"""Tests for the pages the DMZ serves, and the headers it serves them with."""

import http.client
import shutil
import tempfile
import unittest
from pathlib import Path

from spaceknowledge.dmz.http_adapter import DmzServer
from spaceknowledge.dmz.web_assets import Asset, load_assets
from spaceknowledge.tests.dmz.helpers import WAIT, a_dmz, a_front, call, sign_up

LOGGER = "spaceknowledge.dmz.http_adapter"


def fetch(server: DmzServer, path: str, method: str = "GET"):  # type: ignore[no-untyped-def]
    host, port = server.address
    connection = http.client.HTTPConnection(host, port, timeout=WAIT)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response.status, response.headers, response.read()
    finally:
        connection.close()


class TestPages(unittest.TestCase):
    def setUp(self) -> None:
        front, _ = a_front(self)
        self.server = a_dmz(self, front)

    def test_the_three_files_are_served_with_the_right_types(self) -> None:
        for path, kind, marker in (("/", "text/html", b"<title>Space Knowledge</title>"),
                                   ("/app.js", "text/javascript", b"use strict"),
                                   ("/style.css", "text/css", b"planet-earth")):
            with self.subTest(path=path):
                status, headers, body = fetch(self.server, path)
                self.assertEqual(200, status)
                self.assertTrue(headers["Content-Type"].startswith(kind))
                self.assertIn(marker, body)

    def test_nothing_else_on_disk_can_be_reached(self) -> None:
        for path in ("/index.html", "/../state/players.json", "/%2e%2e/x", "/app.js/",
                     "/web/app.js", "/app.js%00", "/favicon.ico", "/style.css.map",
                     "/spaceknowledge/dmz/http_adapter.py"):
            with self.subTest(path=path):
                status, headers, body = fetch(self.server, path)
                self.assertEqual(404, status)
                self.assertTrue(headers["Content-Type"].startswith("application/json"))

    def test_a_query_string_is_ignored_and_a_post_is_not_a_page(self) -> None:
        self.assertEqual(200, fetch(self.server, "/app.js?v=2")[0])
        self.assertEqual(404, call(self.server, "POST", "/", {})[0])

    def test_the_page_is_locked_down(self) -> None:
        _, headers, _ = fetch(self.server, "/")
        policy = headers["Content-Security-Policy"]
        for part in ("default-src 'none'", "script-src 'self'", "style-src 'self'",
                     "connect-src 'self'", "frame-ancestors 'none'", "base-uri 'none'"):
            self.assertIn(part, policy)
        self.assertNotIn("unsafe", policy)
        self.assertEqual("nosniff", headers["X-Content-Type-Options"])
        self.assertEqual("no-store", headers["Cache-Control"])
        self.assertEqual("DENY", headers["X-Frame-Options"])
        self.assertTrue(headers["X-Request-Id"])

    def test_a_page_request_is_logged_like_any_other(self) -> None:
        with self.assertLogs(LOGGER, level="INFO") as logs:
            fetch(self.server, "/")
        self.assertIn("-> 200", "\n".join(logs.output))

    def test_where_works_over_http(self) -> None:
        token = sign_up(self.server)
        status, body, _ = call(self.server, "POST", "/command", {"line": "where"}, token=token)
        self.assertEqual((200, "You are at Earth."), (status, body["reply"]))


class TestAssets(unittest.TestCase):
    def test_a_folder_with_a_missing_file_is_refused(self) -> None:
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory)
        with self.assertRaises(ValueError):
            load_assets(directory)

    def test_custom_assets_can_replace_the_pages(self) -> None:
        front, _ = a_front(self)
        server = DmzServer(front, assets={"/": Asset("text/html; charset=utf-8", b"<p>hi</p>")})
        self.addCleanup(server.stop)
        server.start()
        self.assertEqual((200, b"<p>hi</p>"), (fetch(server, "/")[0], fetch(server, "/")[2]))
        self.assertEqual(404, fetch(server, "/app.js")[0])

    def test_bad_arguments_are_refused(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            load_assets("web")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()