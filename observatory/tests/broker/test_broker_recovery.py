"""Tests that the Broker finishes unfinished operations after a crash."""

import unittest

from observatory.broker.broker import Broker
from observatory.broker.inventory_entry import InventoryEntry
from observatory.broker.inventory_repository import (
    CorruptStoreError,
    InMemoryInventoryRepository,
)
from observatory.common.messages import Request, Response
from observatory.transport.channel import InMemoryChannel, UniverseChannel
from observatory.universe.deposits import Deposits
from observatory.universe.universe import Universe
from observatory.world.room import Room
from observatory.world.world import World


class CrashingChannel(UniverseChannel):
    """Simulates a crash on the way to or from the Universe.

    "before": the request is lost, the Universe never sees it.
    "after": the Universe acts, then the answer is lost.
    "never": everything works.
    """

    def __init__(self, inner: UniverseChannel, when: str = "never") -> None:
        self._inner = inner
        self.when = when
        self.sent = 0

    def send(self, request: Request) -> Response:
        if self.when == "before":
            raise ConnectionError("lost before the Universe")
        self.sent += 1
        response = self._inner.send(request)
        if self.when == "after":
            raise ConnectionError("lost after the Universe")
        return response


class FailingRepository(InMemoryInventoryRepository):
    """A repository whose disk can be made to fail."""

    def __init__(self) -> None:
        super().__init__()
        self.fail = False

    def save(self, records, resources=None, pending=None) -> None:  # type: ignore[no-untyped-def]
        if self.fail:
            raise OSError("disk full")
        super().save(records, resources, pending)


def a_universe() -> tuple[Universe, Deposits, Room]:
    earth = Room("earth", "Earth", "Home.")
    deposits = Deposits({"earth": {"iron": 10}})
    universe = Universe(World({"earth": earth}, "earth"), deposits)
    universe.place_player("ada", "earth")
    return universe, deposits, earth


class TestRecovery(unittest.TestCase):
    def setUp(self) -> None:
        self.universe, self.deposits, self.earth = a_universe()
        self.repository = InMemoryInventoryRepository()
        self.channel = CrashingChannel(InMemoryChannel(self.universe))
        self.broker = Broker(self.channel, self.repository)
        self.broker.add_player("ada")
        self.broker.give("ada", InventoryEntry("torch", "torch"))

    def restart(self) -> Broker:
        """A new process: only the repository and the Universe remember."""
        return Broker(InMemoryChannel(self.universe), self.repository)

    def test_nothing_is_pending_after_a_normal_drop(self) -> None:
        self.assertIsNone(self.broker.drop("ada", "torch"))
        self.assertEqual(0, self.broker.pending_count())
        self.assertEqual(0, self.restart().pending_count())

    def test_a_drop_whose_answer_was_lost_is_finished_after_a_restart(self) -> None:
        self.channel.when = "after"
        with self.assertRaises(ConnectionError):
            self.broker.drop("ada", "torch")
        self.assertIsNotNone(self.earth.find_item("torch"))
        again = self.restart()
        self.assertEqual(1, again.pending_count())
        self.assertEqual(1, again.recover())
        self.assertEqual(0, again.inventory_of("ada").count())
        self.assertEqual(0, again.pending_count())
        self.assertEqual(1, self.earth.item_count())

    def test_a_drop_whose_request_was_lost_is_finished_after_a_restart(self) -> None:
        self.channel.when = "before"
        with self.assertRaises(ConnectionError):
            self.broker.drop("ada", "torch")
        self.assertEqual(0, self.earth.item_count())
        again = self.restart()
        again.recover()
        self.assertIsNotNone(self.earth.find_item("torch"))
        self.assertEqual(0, again.inventory_of("ada").count())

    def test_a_pending_item_cannot_be_used_after_a_restart(self) -> None:
        self.channel.when = "before"
        with self.assertRaises(ConnectionError):
            self.broker.drop("ada", "torch")
        again = self.restart()
        self.assertIsNotNone(again.inventory_of("ada").check_usable("torch"))

    def test_a_mine_whose_answer_was_lost_is_finished_and_mined_only_once(self) -> None:
        self.channel.when = "after"
        with self.assertRaises(ConnectionError):
            self.broker.mine("ada", "iron", 3)
        self.assertEqual(7, self.deposits.available("earth", "iron"))
        again = self.restart()
        self.assertTrue(again.resources_of("ada").is_empty())
        again.recover()
        self.assertEqual(3, again.resources_of("ada").amount_of("iron"))
        self.assertEqual(7, self.deposits.available("earth", "iron"))

    def test_a_mine_whose_request_was_lost_is_mined_once_on_recovery(self) -> None:
        self.channel.when = "before"
        with self.assertRaises(ConnectionError):
            self.broker.mine("ada", "iron", 3)
        again = self.restart()
        again.recover()
        self.assertEqual(3, again.resources_of("ada").amount_of("iron"))
        self.assertEqual(7, self.deposits.available("earth", "iron"))

    def test_a_recovered_mine_that_the_universe_now_refuses_gives_nothing(self) -> None:
        self.channel.when = "before"
        with self.assertRaises(ConnectionError):
            self.broker.mine("ada", "iron", 3)
        self.deposits.remove("earth", "iron", 9)
        again = self.restart()
        self.assertEqual(1, again.recover())
        self.assertTrue(again.resources_of("ada").is_empty())
        self.assertEqual(0, again.pending_count())

    def test_recovering_twice_changes_nothing_the_second_time(self) -> None:
        self.channel.when = "after"
        with self.assertRaises(ConnectionError):
            self.broker.mine("ada", "iron", 3)
        again = self.restart()
        again.recover()
        self.assertEqual(0, again.recover())
        self.assertEqual(3, again.resources_of("ada").amount_of("iron"))
        self.assertEqual(7, self.deposits.available("earth", "iron"))

    def test_recovery_also_works_in_the_same_process(self) -> None:
        self.channel.when = "before"
        with self.assertRaises(ConnectionError):
            self.broker.drop("ada", "torch")
        self.channel.when = "never"
        self.assertEqual(1, self.broker.recover())
        self.assertIsNotNone(self.earth.find_item("torch"))
        self.assertEqual(0, self.broker.inventory_of("ada").count())

    def test_a_recovery_that_fails_keeps_the_operation_pending(self) -> None:
        self.channel.when = "before"
        with self.assertRaises(ConnectionError):
            self.broker.drop("ada", "torch")
        with self.assertRaises(ConnectionError):
            self.broker.recover()
        self.assertEqual(1, self.broker.pending_count())
        self.channel.when = "never"
        self.assertEqual(1, self.broker.recover())
        self.assertEqual(0, self.broker.pending_count())


class TestTheIntentionIsSavedBeforeSending(unittest.TestCase):
    def setUp(self) -> None:
        universe, _, _ = a_universe()
        self.repository = FailingRepository()
        self.channel = CrashingChannel(InMemoryChannel(universe))
        self.broker = Broker(self.channel, self.repository)
        self.broker.add_player("ada")
        self.broker.give("ada", InventoryEntry("torch", "torch"))
        self.repository.fail = True

    def test_a_drop_that_cannot_be_saved_is_not_sent_and_the_item_stays_usable(self) -> None:
        with self.assertRaises(OSError):
            self.broker.drop("ada", "torch")
        self.assertEqual(0, self.channel.sent)
        self.assertEqual(0, self.broker.pending_count())
        self.assertIsNone(self.broker.inventory_of("ada").check_usable("torch"))

    def test_a_mine_that_cannot_be_saved_is_not_sent(self) -> None:
        with self.assertRaises(OSError):
            self.broker.mine("ada", "iron", 1)
        self.assertEqual(0, self.channel.sent)
        self.assertEqual(0, self.broker.pending_count())


class TestBadPendingOperations(unittest.TestCase):
    def broker_with(self, *pending: Request) -> Broker:
        universe, _, _ = a_universe()
        repository = InMemoryInventoryRepository()
        repository.save({"ada": [("torch", "torch")]}, None, list(pending))
        return Broker(InMemoryChannel(universe), repository)

    def test_a_valid_pending_mine_is_accepted(self) -> None:
        broker = self.broker_with(Request("op1", "mine", "ada", "iron", 3))
        self.assertEqual(1, broker.pending_count())

    def test_an_unknown_action_is_refused(self) -> None:
        with self.assertRaises(CorruptStoreError):
            self.broker_with(Request("op1", "teleport", "ada", "torch"))

    def test_a_drop_of_something_not_carried_is_refused(self) -> None:
        with self.assertRaises(CorruptStoreError):
            self.broker_with(Request("op1", "add_item", "ada", "lantern"))

    def test_two_pending_drops_of_the_same_item_are_refused(self) -> None:
        with self.assertRaises(CorruptStoreError):
            self.broker_with(
                Request("op1", "add_item", "ada", "torch"),
                Request("op2", "add_item", "ada", "torch"),
            )


if __name__ == "__main__":
    unittest.main()