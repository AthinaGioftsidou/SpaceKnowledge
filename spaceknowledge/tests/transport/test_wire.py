"""Tests for the wire format: one JSON object per line."""

import io
import unittest

from spaceknowledge.common.messages import ItemInfo, Request, Response
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.transport.wire import (
    MAX_LINE,
    WireError,
    read_message,
    request_from_wire,
    request_to_wire,
    response_from_wire,
    response_to_wire,
    text_field,
    write_message,
)


def parts(request: Request) -> tuple:
    return (request.op_id, request.action, request.player_id,
            request.item_id, request.amount, request.name)


class TestRequests(unittest.TestCase):
    def test_a_full_request_round_trips(self) -> None:
        request = Request("op1", "add_item", "ada", "torch-1", 2, "torch")
        self.assertEqual(parts(request), parts(request_from_wire(request_to_wire(request))))

    def test_a_minimal_request_round_trips_and_leaves_out_the_name(self) -> None:
        request = Request("op1", "mine", "ada", "iron")
        body = request_to_wire(request)
        self.assertNotIn("name", body)
        self.assertEqual(parts(request), parts(request_from_wire(body)))

    def test_bad_requests_are_refused_with_a_wire_error(self) -> None:
        good = {"op_id": "op1", "action": "mine", "player_id": "ada", "item_id": "iron"}
        bad: list[object] = [5, [], {}]
        bad += [{k: v for k, v in good.items() if k != key} for key in good]
        bad += [{**good, "op_id": 5}, {**good, "op_id": ""}, {**good, "amount": True},
                {**good, "amount": 0}, {**good, "amount": 1.5}, {**good, "amount": "3"},
                {**good, "name": ""}, {**good, "name": 5}, {**good, "admin": True}]
        for body in bad:
            with self.subTest(body=body):
                with self.assertRaises(WireError):
                    request_from_wire(body)  # type: ignore[arg-type]


class TestResponses(unittest.TestCase):
    def test_an_ok_response_with_items_round_trips(self) -> None:
        info = ItemInfo("torch-1", "torch", "a torch")
        back = response_from_wire(response_to_wire(Response("op1", items=(info,))))
        self.assertEqual(("op1", True, (info,)), (back.op_id, back.ok, back.items))

    def test_a_refusal_round_trips_with_all_three_parts(self) -> None:
        back = response_from_wire(response_to_wire(Response("op1", Refusal("a", "b", "c"))))
        self.assertFalse(back.ok)
        self.assertEqual(("a", "b", "c"),
                         (back.refusal.what, back.refusal.why, back.refusal.next_step))

    def test_bad_responses_are_refused_with_a_wire_error(self) -> None:
        good = {"op_id": "op1", "ok": True}
        refusal = {"what": "a", "why": "b", "next_step": "c"}
        item = {"id": "i", "name": "n", "description": "d"}
        bad: list[object] = [
            5, {}, {"op_id": "op1"}, {"op_id": "op1", "ok": "yes"}, {"op_id": "", "ok": True},
            {"op_id": "op1", "ok": False},
            {**good, "refusal": refusal},
            {"op_id": "op1", "ok": False, "refusal": {"what": "a", "why": "b"}},
            {"op_id": "op1", "ok": False, "refusal": {**refusal, "why": ""}},
            {"op_id": "op1", "ok": False, "refusal": refusal, "items": [item]},
            {**good, "items": "torch"}, {**good, "items": [5]},
            {**good, "items": [{"id": "i", "name": "n"}]}, {**good, "extra": 1},
        ]
        for body in bad:
            with self.subTest(body=body):
                with self.assertRaises(WireError):
                    response_from_wire(body)  # type: ignore[arg-type]


class TestLines(unittest.TestCase):
    def test_a_message_is_exactly_one_line_even_with_a_newline_inside_a_value(self) -> None:
        sent: list[bytes] = []
        write_message(sent.append, {"a": "x\ny"})
        self.assertEqual(1, len(sent))
        self.assertEqual(1, sent[0].count(b"\n"))

    def test_messages_round_trip_in_order(self) -> None:
        buffer = io.BytesIO()
        write_message(buffer.write, {"n": 1})
        write_message(buffer.write, {"n": 2})
        buffer.seek(0)
        self.assertEqual([{"n": 1}, {"n": 2}, None],
                         [read_message(buffer), read_message(buffer), read_message(buffer)])

    def test_bad_lines_are_refused(self) -> None:
        for data in (b"not json\n", b"[1]\n", b'"x"\n', b"\xff\xfe\n", b'{"a":1}',
                     b"x" * (MAX_LINE + 5) + b"\n"):
            with self.subTest(data=data[:20]):
                with self.assertRaises(WireError):
                    read_message(io.BytesIO(data))

    def test_text_fields_must_be_non_empty_text(self) -> None:
        self.assertEqual("x", text_field({"k": "x"}, "k", "thing"))
        for body in ({}, {"k": ""}, {"k": 5}):
            with self.subTest(body=body):
                with self.assertRaises(WireError):
                    text_field(body, "k", "thing")


if __name__ == "__main__":
    unittest.main()