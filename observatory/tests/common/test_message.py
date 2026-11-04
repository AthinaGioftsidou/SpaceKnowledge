"""Tests for Request and Response, the messages between Broker and Universe."""

import unittest

from observatory.common.messages import Request, Response
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


if __name__ == "__main__":
    unittest.main()