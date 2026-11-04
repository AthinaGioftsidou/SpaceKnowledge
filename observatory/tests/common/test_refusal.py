"""Tests for Refusal, the answer to a request the server will not carry out."""

import unittest

from observatory.common.refusal import Refusal


class TestRefusal(unittest.TestCase):
    def test_it_keeps_its_three_parts(self) -> None:
        refusal = Refusal("drop torch", "you are not carrying a torch", "type inventory")
        self.assertEqual("drop torch", refusal.what)
        self.assertEqual("you are not carrying a torch", refusal.why)
        self.assertEqual("type inventory", refusal.next_step)

    def test_the_text_says_what_why_and_what_next(self) -> None:
        refusal = Refusal("drop torch", "you are not carrying a torch", "type inventory")
        text = refusal.describe()
        self.assertIn("drop torch", text)
        self.assertIn("you are not carrying a torch", text)
        self.assertIn("type inventory", text)

    def test_an_empty_part_is_refused(self) -> None:
        for what, why, next_step in (("", "why", "next"), ("what", "", "next"), ("what", "why", "")):
            with self.subTest(what=what, why=why, next_step=next_step):
                with self.assertRaises(ValueError):
                    Refusal(what, why, next_step)


if __name__ == "__main__":
    unittest.main()