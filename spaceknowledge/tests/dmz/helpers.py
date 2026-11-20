"""Shared helpers for the DMZ tests. Not a test module itself."""

import http.client
import json
import unittest
from typing import Any

from spaceknowledge.app.front import Front
from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.broker_server import BrokerServer
from spaceknowledge.common.messages import Request, Response
from spaceknowledge.dmz.http_adapter import DmzServer
from spaceknowledge.transport.channel import InMemoryChannel, UniverseChannel
from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.universe import Universe
from spaceknowledge.users.accounts import AccountRegistry
from spaceknowledge.users.session_book import SessionBook
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World

WAIT = 5
PASSWORD = "correct horse"


class LostChannel(UniverseChannel):
    """The world cannot be reached."""

    def send(self, request: Request) -> Response:
        raise ConnectionError("cannot reach the Universe at 127.0.0.1:7400")


def a_front(test: unittest.TestCase, front_class: type[Front] = Front,
            lost: bool = False) -> tuple[Front, Deposits]:
    """A Front over a one-destination world. With `lost`, the Broker's channel
    is dead and the player ada already exists, so a command reaches the dead
    channel."""
    earth = Destination("earth", "Earth", "Home.")
    deposits = Deposits({"earth": {"iron": 100}})
    universe = Universe(World({"earth": earth}, "earth"), deposits)
    broker = Broker(LostChannel() if lost else InMemoryChannel(universe))
    if lost:
        broker.add_player("ada")
    server = BrokerServer(broker)
    server.start()
    test.addCleanup(server.stop)
    front = front_class(AccountRegistry(iterations=1), SessionBook(), server,
                        None if lost else "earth")
    return front, deposits


def a_dmz(test: unittest.TestCase, front: Front, request_timeout: float = 10.0) -> DmzServer:
    server = DmzServer(front, request_timeout=request_timeout)
    test.addCleanup(server.stop)  # runs before the Broker thread stops
    server.start()
    return server


def call(server: DmzServer, method: str, path: str, body: Any = None,
         token: str | None = None, content_type: str | None = "application/json",
         raw: bytes | None = None) -> tuple[int, dict[str, Any], Any]:
    """One HTTP request. Returns the status, the parsed JSON body and the headers."""
    host, port = server.address
    headers: dict[str, str] = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    payload = raw
    if payload is None and body is not None:
        payload = json.dumps(body).encode("utf-8")
    if payload is not None and content_type is not None:
        headers["Content-Type"] = content_type
    connection = http.client.HTTPConnection(host, port, timeout=WAIT)
    try:
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        data = response.read()
        return response.status, json.loads(data.decode("utf-8")), response.headers
    finally:
        connection.close()


def header_only_call(server: DmzServer, path: str,
                     headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    """A POST that claims a body in its headers and never sends one, so the
    server must decide from the headers alone."""
    host, port = server.address
    connection = http.client.HTTPConnection(host, port, timeout=WAIT)
    try:
        connection.putrequest("POST", path)
        for name, value in headers.items():
            connection.putheader(name, value)
        connection.endheaders()
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


def sign_up(server: DmzServer, name: str = "ada", password: str = PASSWORD) -> str:
    """Register and log in over HTTP. Returns the session token."""
    status, _, _ = call(server, "POST", "/register", {"username": name, "password": password})
    assert status == 201, status
    status, body, _ = call(server, "POST", "/login", {"username": name, "password": password})
    assert status == 200, status
    return body["token"]