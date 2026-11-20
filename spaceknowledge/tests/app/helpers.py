"""Shared helpers for the app tests. Not a test module itself."""


class Script:
    """Stands in for the keyboard: hands out lines, then reports end of input."""

    def __init__(self, *lines: str) -> None:
        self._lines = list(lines)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self._lines:
            raise EOFError
        return self._lines.pop(0)