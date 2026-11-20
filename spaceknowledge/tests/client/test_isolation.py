"""The trust boundary, checked on the source: the client imports nothing from
the server side and never names the internal server."""

import ast
import unittest
from pathlib import Path

import spaceknowledge.client

CLIENT_DIR = Path(spaceknowledge.client.__file__).parent
FORBIDDEN = ("universe", "transport", "broker", "world", "app", "dmz", "users")


def imported_modules(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


class TestTheClientKnowsOnlyTheDmz(unittest.TestCase):
    def files(self) -> list[Path]:
        files = sorted(CLIENT_DIR.glob("*.py"))
        self.assertGreaterEqual(len(files), 3)  # so this test can never be empty
        return files

    def test_no_client_file_imports_the_server_side(self) -> None:
        for path in self.files():
            for module in imported_modules(path):
                for name in FORBIDDEN:
                    with self.subTest(file=path.name, module=module):
                        self.assertFalse(module.startswith(f"spaceknowledge.{name}"), module)

    def test_no_client_file_names_the_internal_server(self) -> None:
        for path in self.files():
            with self.subTest(file=path.name):
                self.assertNotIn("universe", path.read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()