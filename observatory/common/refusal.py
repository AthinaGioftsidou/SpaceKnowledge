"""A refusal: what was refused, why, and what the player can do next."""


class Refusal:
    """The answer to a request that was not carried out.

    Immutable on purpose: once a server has decided to refuse, nothing
    downstream should be able to change the reason.
    """

    def __init__(self, what: str, why: str, next_step: str) -> None:
        if not what:
            raise ValueError("what must not be empty")
        if not why:
            raise ValueError("why must not be empty")
        if not next_step:
            raise ValueError("next_step must not be empty")
        self._what = what
        self._why = why
        self._next_step = next_step

    @property
    def what(self) -> str:
        return self._what

    @property
    def why(self) -> str:
        return self._why

    @property
    def next_step(self) -> str:
        return self._next_step

    def describe(self) -> str:
        """The text the player sees."""
        return f"Refused: {self._what}. Why: {self._why}. Next: {self._next_step}."