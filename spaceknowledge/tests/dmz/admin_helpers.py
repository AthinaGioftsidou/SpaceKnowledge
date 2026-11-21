"""A whole Broker node with admin support, for the admin tests. Not a test module."""

import unittest
from dataclasses import dataclass

from spaceknowledge.app.admin_service import AdminService
from spaceknowledge.app.front import Front
from spaceknowledge.broker.broker import Broker
from spaceknowledge.broker.broker_server import BrokerServer
from spaceknowledge.dmz.http_adapter import DmzServer
from spaceknowledge.transport.channel import InMemoryChannel
from spaceknowledge.universe.deposits import Deposits
from spaceknowledge.universe.universe import Universe
from spaceknowledge.users.accounts import AccountRegistry
from spaceknowledge.users.admin_gate import AdminGate
from spaceknowledge.users.one_time import InMemoryMailbox, OneTimePasswords
from spaceknowledge.users.session_book import SessionBook
from spaceknowledge.world.destination import Destination
from spaceknowledge.world.world import World


@dataclass
class Rig:
    front: Front
    admin: AdminService
    mailbox: InMemoryMailbox
    dmz: DmzServer
    server: BrokerServer


def a_rig(test: unittest.TestCase) -> Rig:
    earth = Destination("earth", "Earth", "Home.")
    universe = Universe(World({"earth": earth}, "earth"), Deposits({"earth": {"iron": 100}}))
    server = BrokerServer(Broker(InMemoryChannel(universe)))
    server.start()
    test.addCleanup(server.stop)
    accounts = AccountRegistry(iterations=1)
    front = Front(accounts, SessionBook(), server, "earth")
    mailbox = InMemoryMailbox()
    admin = AdminService(
        AdminGate(OneTimePasswords(["root"], mailbox)), accounts, server, "broker-1")
    dmz = DmzServer(front, admin=admin)
    test.addCleanup(dmz.stop)  # runs before the Broker thread stops
    dmz.start()
    return Rig(front, admin, mailbox, dmz, server)


def latest_code(rig: Rig) -> str:
    return rig.mailbox.messages[-1][1]


def admin_token(rig: Rig) -> str:
    """Request a code, read it from the mailbox, and log in as root."""
    rig.admin.request_code("root")
    token = rig.admin.login("root", latest_code(rig))
    assert isinstance(token, str), token
    return token