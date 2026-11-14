"""Tests for ItemProxy: the Broker's stand-in for an item in the Universe."""

import unittest

from observatory.broker.item_proxy import ItemProxy
from observatory.common.messages import ItemInfo
from observatory.common.refusal import Refusal
from observatory.world.item import Item

INFO = ItemInfo("torch", "torch", "a rubber torch")


def a_proxy(picker=None) -> ItemProxy:  # type: ignore[no-untyped-def]
    return ItemProxy(INFO, picker if picker is not None else (lambda proxy, player: None))


class TestLooksLikeAnItem(unittest.TestCase):
    def test_it_is_an_item_with_the_same_face(self) -> None:
        proxy = a_proxy()
        self.assertIsInstance(proxy, Item)
        self.assertEqual(("torch", "torch", "a rubber torch"),
                         (proxy.item_id, proxy.name, proxy.describe()))


class TestStates(unittest.TestCase):
    def test_it_starts_on_the_ground_held_by_the_universe(self) -> None:
        proxy = a_proxy()
        self.assertEqual(("owned", "universe"), (proxy.state(), proxy.holder()))

    def test_a_pick_goes_through_flight_to_done_held_by_the_broker(self) -> None:
        proxy = a_proxy()
        self.assertIsNone(proxy.begin_pick())
        self.assertEqual(("flight", "universe"), (proxy.state(), proxy.holder()))
        self.assertIsNone(proxy.finish_pick())
        self.assertEqual(("done", "broker"), (proxy.state(), proxy.holder()))

    def test_a_refusal_puts_it_back_on_the_ground(self) -> None:
        proxy = a_proxy()
        proxy.begin_pick()
        self.assertIsNone(proxy.cancel_pick())
        self.assertEqual(("owned", "universe"), (proxy.state(), proxy.holder()))

    def test_a_second_pick_while_in_flight_is_refused(self) -> None:
        proxy = a_proxy()
        proxy.begin_pick()
        self.assertIsInstance(proxy.begin_pick(), Refusal)
        self.assertEqual("flight", proxy.state())

    def test_finishing_a_pick_that_never_began_is_refused(self) -> None:
        proxy = a_proxy()
        self.assertIsInstance(proxy.finish_pick(), Refusal)
        self.assertEqual("owned", proxy.state())


class TestPick(unittest.TestCase):
    def test_pick_hands_itself_and_the_player_to_the_picker(self) -> None:
        calls: list[tuple[ItemProxy, str]] = []

        def picker(proxy: ItemProxy, player: str) -> Refusal | None:
            calls.append((proxy, player))
            return None

        proxy = a_proxy(picker)
        self.assertIsNone(proxy.pick("ada"))
        self.assertEqual([(proxy, "ada")], calls)


class TestArguments(unittest.TestCase):
    def test_bad_arguments_are_refused(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            ItemProxy("torch", lambda proxy, player: None)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "must be"):
            ItemProxy(INFO, "picker")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()