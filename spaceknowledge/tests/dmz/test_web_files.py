"""Checks on the page's source files: no way to run injected script, no mention
of the internal server, and a background for every destination in the world."""

import json
import re
import unittest
from pathlib import Path

from spaceknowledge.dmz.web_assets import WEB_DIR

SPACE_FILE = Path(__file__).resolve().parents[3] / "data" / "space.json"


def slug(name: str) -> str:
    """The same rule as `slug` in app.js."""
    text = re.sub(r"^the\s+", "", name.lower().strip())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def read(name: str) -> str:
    return (WEB_DIR / name).read_text(encoding="utf-8")


class TestTheScript(unittest.TestCase):
    def test_nothing_the_game_says_can_run_as_script_or_markup(self) -> None:
        source = read("app.js")
        for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write",
                       "eval(", "new Function", "localStorage"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, source)

    def test_the_session_lives_in_the_tab_only(self) -> None:
        self.assertIn("sessionStorage", read("app.js"))


class TestThePage(unittest.TestCase):
    def test_there_is_no_inline_script_style_or_handler(self) -> None:
        page = read("index.html")
        self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)", page))
        self.assertIsNone(re.search(r"\son\w+\s*=", page))
        self.assertIsNone(re.search(r"\sstyle\s*=", page))
        self.assertNotIn("<style", page)

    def test_it_loads_only_our_own_files(self) -> None:
        links = set(re.findall(r'(?:src|href)="([^"]+)"', read("index.html")))
        self.assertLessEqual(links, {"/app.js", "/style.css", "data:,"})


class TestEveryDestinationHasABackground(unittest.TestCase):
    def test_the_stylesheet_has_a_class_for_each_destination_and_a_default(self) -> None:
        css = read("style.css")
        names = [d["name"] for d in json.loads(SPACE_FILE.read_text(encoding="utf-8"))["destinations"]]
        self.assertGreaterEqual(len(names), 3)
        for name in names:
            with self.subTest(name=name):
                self.assertIn(f".planet-{slug(name)}", css)
        self.assertIn(".planet-space", css)


class TestNothingInternalIsNamed(unittest.TestCase):
    def test_no_web_file_mentions_the_internal_server(self) -> None:
        for name in ("index.html", "app.js", "style.css"):
            with self.subTest(name=name):
                self.assertNotIn("universe", read(name).lower())


if __name__ == "__main__":
    unittest.main()