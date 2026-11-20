"""Tests for the HTTP boundary: what is accepted, and what leaves."""

import unittest

from spaceknowledge.common.refusal import Refusal
from spaceknowledge.dmz.http_protocol import (
    MAX_TOKEN,
    HttpProblem,
    bearer_token,
    only_fields,
    parse_json_body,
    refusal_body,
    scrub,
    text_field,
)


class TestScrub(unittest.TestCase):
    def test_the_internal_server_is_never_named(self) -> None:
        self.assertEqual("the game world did not answer", scrub("the Universe did not answer"))
        self.assertEqual("a game world b", scrub("a UNIVERSE b"))

    def test_other_text_is_left_alone(self) -> None:
        self.assertEqual("You mine 3 iron.", scrub("You mine 3 iron."))


class TestRefusalBody(unittest.TestCase):
    def test_it_has_all_three_parts_and_is_scrubbed(self) -> None:
        body = refusal_body(Refusal("a", "the Universe is down", "wait"))
        self.assertEqual(
            {"ok": False,
             "refusal": {"what": "a", "why": "the game world is down", "next_step": "wait"}},
            body)


class TestBearerToken(unittest.TestCase):
    def test_a_good_header_gives_the_token(self) -> None:
        self.assertEqual("abc", bearer_token("Bearer abc"))
        self.assertEqual("abc", bearer_token("bearer abc"))

    def test_anything_else_is_a_401(self) -> None:
        for header in (None, "", "Bearer", "Bearer ", "Basic abc", "Bearer " + "x" * (MAX_TOKEN + 1)):
            with self.subTest(header=header):
                with self.assertRaises(HttpProblem) as caught:
                    bearer_token(header)
                self.assertEqual(401, caught.exception.status)


class TestBody(unittest.TestCase):
    def test_a_json_object_is_parsed(self) -> None:
        self.assertEqual({"a": 1}, parse_json_body(b'{"a": 1}', "application/json; charset=utf-8"))

    def test_the_wrong_content_type_is_a_415(self) -> None:
        with self.assertRaises(HttpProblem) as caught:
            parse_json_body(b"{}", "text/plain")
        self.assertEqual(415, caught.exception.status)

    def test_bad_bodies_are_a_400(self) -> None:
        for raw in (b"", b"not json", b"[1]", b'"x"', b"\xff\xfe", b"5"):
            with self.subTest(raw=raw):
                with self.assertRaises(HttpProblem) as caught:
                    parse_json_body(raw, "application/json")
                self.assertEqual(400, caught.exception.status)


class TestFields(unittest.TestCase):
    def test_a_text_field_is_returned(self) -> None:
        self.assertEqual("ada", text_field({"u": "ada"}, "u", 10))

    def test_bad_text_fields_are_a_400(self) -> None:
        for body in ({}, {"u": 5}, {"u": None}, {"u": "x" * 11}, {"u": "a\x00b"}, {"u": "a\nb"}):
            with self.subTest(body=body):
                with self.assertRaises(HttpProblem) as caught:
                    text_field(body, "u", 10)
                self.assertEqual(400, caught.exception.status)

    def test_a_password_may_contain_any_character(self) -> None:
        self.assertEqual("a\tb", text_field({"p": "a\tb"}, "p", 10, allow_control=True))

    def test_an_unexpected_field_is_refused(self) -> None:
        only_fields({"a": 1}, {"a", "b"})
        with self.assertRaises(HttpProblem) as caught:
            only_fields({"a": 1, "admin": True}, {"a"})
        self.assertEqual(400, caught.exception.status)


if __name__ == "__main__":
    unittest.main()