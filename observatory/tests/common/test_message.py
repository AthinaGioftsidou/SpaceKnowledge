"""Tests for Request and Response, the messages between Broker and Universe."""

import unittest

from observatory.common.messages import ItemInfo, Request, Response
from observatory.common.refusal import Refusal


class TestRequest(unittest.TestCase):
    def test_it_keeps_its_parts(self) -> None:
        request = Request("op1", "add_item", "ada", "torch")
        self.assertEqual("op1", request.op_id)
        self.assertEqual("add_item", request.action)
        self.assertEqual("ada", request.player_id)
        self.assertEqual("torch", request.item_id)

    def test_an_empty_part_is_refused(self) -> None:
        parts = [("", "a", "b", "c"), ("a", "", "b", "c"), ("a", "b", "", "c"), ("a", "b", "c", "")]
        for part in parts:
            with self.subTest(part=part):
                with self.assertRaises(ValueError):
                    Request(*part)


class TestResponse(unittest.TestCase):
    def test_a_response_without_a_refusal_is_ok(self) -> None:
        response = Response("op1")
        self.assertTrue(response.ok)
        self.assertIsNone(response.refusal)

    def test_a_response_with_a_refusal_is_not_ok(self) -> None:
        refusal = Refusal("drop torch", "no such item", "type inventory")
        response = Response("op1", refusal)
        self.assertFalse(response.ok)
        self.assertIs(refusal, response.refusal)

    def test_an_empty_op_id_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            Response("")

    def test_a_string_is_refused_where_a_refusal_is_expected(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            Response("op1", "not a refusal")  # type: ignore[arg-type]

class TestRequestAmount(unittest.TestCase):
    def test_the_amount_defaults_to_one(self) -> None:
        self.assertEqual(1, Request("op1", "add_item", "ada", "torch").amount)

    def test_an_amount_is_kept(self) -> None:
        self.assertEqual(5, Request("op1", "mine", "ada", "iron", 5).amount)

    def test_an_amount_below_one_is_refused(self) -> None:
        for amount in (0, -3):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    Request("op1", "mine", "ada", "iron", amount)

    def test_an_amount_that_is_not_a_whole_number_is_refused(self) -> None:
        for amount in (2.5, "5", True):
            with self.subTest(amount=amount):
                with self.assertRaisesRegex(TypeError, "must be"):
                    Request("op1", "mine", "ada", "iron", amount)  # type: ignore[arg-type]


class TestItemInfoAndItems(unittest.TestCase):
    def test_an_item_info_keeps_its_parts(self) -> None:
        info = ItemInfo("torch", "torch", "a rubber torch")
        self.assertEqual(("torch", "torch", "a rubber torch"),
                         (info.item_id, info.name, info.description))

    def test_an_empty_part_is_refused(self) -> None:
        for parts in (("", "n", "d"), ("i", "", "d"), ("i", "n", "")):
            with self.subTest(parts=parts):
                with self.assertRaises(ValueError):
                    ItemInfo(*parts)

    def test_a_response_can_carry_items(self) -> None:
        info = ItemInfo("torch", "torch", "a rubber torch")
        response = Response("op1", items=(info,))
        self.assertTrue(response.ok)
        self.assertEqual((info,), response.items)
        self.assertEqual((), Response("op1").items)

    def test_a_refusal_and_items_together_are_refused(self) -> None:
        info = ItemInfo("torch", "torch", "a rubber torch")
        with self.assertRaises(ValueError):
            Response("op1", Refusal("a", "b", "c"), (info,))

    def test_items_must_be_a_tuple_of_item_infos(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be"):
            Response("op1", items=["torch"])  # type: ignore[arg-type]

class TestRequestName(unittest.TestCase):
    def test_the_name_is_optional_and_the_display_name_falls_back_to_the_id(self) -> None:
        plain = Request("op1", "add_item", "ada", "torch-1")
        self.assertIsNone(plain.name)
        self.assertEqual("torch-1", plain.display_name)

    def test_a_name_is_kept(self) -> None:
        named = Request("op1", "add_item", "ada", "torch-1", name="torch")
        self.assertEqual(("torch", "torch"), (named.name, named.display_name))

    def test_an_empty_name_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            Request("op1", "add_item", "ada", "torch-1", name="")

if __name__ == "__main__":
    unittest.main()