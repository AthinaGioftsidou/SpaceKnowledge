"""MISSIONS: shared goals. Players gather a resource together and answer a
question about it, and a route that was shut opens for everybody."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

COLLECTING = "collecting"
QUESTION = "question"
COMPLETE = "complete"

# A door that a mission opens has a key named after the mission, so no item in
# the game can ever open it by accident.
MISSION_KEY_PREFIX = "mission:"

# A longer reply is a paragraph, not an answer: it would match by luck.
MAX_ANSWER_WORDS = 8

_SPEC_FIELDS = {"id", "title", "goal", "briefing", "question", "answers", "hint",
                "success", "opens"}


class MissionError(ValueError):
    """A mission, or saved mission progress, that cannot be trusted."""


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _filled(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True)
class Mission:
    """One shared goal. Read-only, and written in data, not in code."""

    mission_id: str
    title: str
    resource: str          # what must be mined...
    amount: int            # ...how much of it...
    where: str             # ...and at which destination
    briefing: str
    question: str
    answers: tuple[str, ...]
    hint: str
    success: str
    opens_from: str        # the destination whose gate this opens...
    opens_direction: str   # ...in this direction

    def __post_init__(self) -> None:
        for label in ("mission_id", "title", "resource", "where", "briefing", "question",
                      "hint", "success", "opens_from", "opens_direction"):
            if not _filled(getattr(self, label)):
                raise MissionError(f"a mission needs {label} as non-empty text")
        if isinstance(self.amount, bool) or not isinstance(self.amount, int) or self.amount < 1:
            raise MissionError("a mission needs amount as a whole number of at least 1")
        if (not isinstance(self.answers, tuple) or not self.answers
                or not all(isinstance(a, str) and _words(a) for a in self.answers)):
            raise MissionError("a mission needs answers as a non-empty tuple of words")

    def key(self) -> str:
        return MISSION_KEY_PREFIX + self.mission_id

    def accepts(self, answer: str) -> bool:
        """Does the player's text contain one of the accepted answers, as whole
        words in order? Case and punctuation do not matter."""
        given = _words(answer)
        if not given or len(given) > MAX_ANSWER_WORDS:
            return False
        for accepted in self.answers:
            phrase = _words(accepted)
            for start in range(len(given) - len(phrase) + 1):
                if given[start:start + len(phrase)] == phrase:
                    return True
        return False


@dataclass
class _Progress:
    collected: int = 0
    complete: bool = False


class MissionBook:
    """The missions, and how far everybody together has got.

    Not thread-safe on its own: only the Universe uses it, under the Universe's
    one lock.
    """

    def __init__(self, missions: Iterable[Mission] = ()) -> None:
        self._missions: dict[str, Mission] = {}
        for mission in missions:
            if not isinstance(mission, Mission):
                raise TypeError(f"mission must be a Mission, not {type(mission).__name__}")
            if mission.mission_id in self._missions:
                raise MissionError(f"the mission {mission.mission_id} is listed twice")
            self._missions[mission.mission_id] = mission
        self._progress = {mission_id: _Progress() for mission_id in self._missions}

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "MissionBook":
        """Read the optional "missions" list of a world file."""
        specs = raw.get("missions", [])
        if not isinstance(specs, list):
            raise MissionError("missions must be a list")
        return cls(_mission_from_spec(spec) for spec in specs)

    def all(self) -> list[Mission]:
        return list(self._missions.values())

    def status(self, mission_id: str) -> str:
        mission, progress = self._missions[mission_id], self._progress[mission_id]
        if progress.complete:
            return COMPLETE
        if progress.collected >= mission.amount:
            return QUESTION
        return COLLECTING

    def collected(self, mission_id: str) -> int:
        return self._progress[mission_id].collected

    def current(self) -> Mission | None:
        """The first unfinished mission, or the last one when all are done."""
        mission = self._first_open()
        if mission is not None:
            return mission
        return list(self._missions.values())[-1] if self._missions else None

    def text(self, mission: Mission) -> str:
        """What a player is told, which depends on where the mission stands."""
        status = self.status(mission.mission_id)
        if status == COLLECTING:
            have = self._progress[mission.mission_id].collected
            return (f"Collected {have} of {mission.amount} {mission.resource}.\n"
                    f"{mission.briefing}")
        if status == QUESTION:
            return f"{mission.question}\nType answer and your answer."
        return mission.success

    def record_mining(self, destination_id: str, resource: str, amount: int) -> None:
        """Count iron mined (or whatever the goal is) towards the open mission."""
        mission = self._first_open()
        if mission is None:
            return
        progress = self._progress[mission.mission_id]
        if progress.collected >= mission.amount:
            return  # enough already: now it waits for the answer
        if destination_id == mission.where and resource == mission.resource:
            progress.collected = min(mission.amount, progress.collected + amount)

    def answer(self, text: str) -> tuple[Mission, bool] | None:
        """None if no question is waiting. Otherwise the mission and whether the
        answer was right; a right answer completes the mission."""
        mission = self._first_open()
        if mission is None or self.status(mission.mission_id) != QUESTION:
            return None
        if not mission.accepts(text):
            return mission, False
        self._progress[mission.mission_id].complete = True
        return mission, True

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """A copy, for saving."""
        return {mission_id: {"collected": p.collected, "complete": p.complete}
                for mission_id, p in self._progress.items()}

    def check(self, saved: dict[str, dict[str, Any]]) -> None:
        """Refuse saved progress that does not fit these missions."""
        for mission_id, record in saved.items():
            mission = self._missions.get(mission_id)
            if mission is None:
                raise MissionError(
                    f"the saved state has progress for the mission {mission_id}, which does not exist")
            collected, complete = record.get("collected"), record.get("complete")
            if (isinstance(collected, bool) or not isinstance(collected, int)
                    or not 0 <= collected <= mission.amount):
                raise MissionError(f"the saved progress of {mission_id} has a bad amount")
            if not isinstance(complete, bool):
                raise MissionError(f"the saved progress of {mission_id} has a bad complete flag")

    def restore(self, saved: dict[str, dict[str, Any]]) -> None:
        """Replace progress with `saved`. If it is bad, nothing changes."""
        self.check(saved)
        for mission_id, record in saved.items():
            self._progress[mission_id] = _Progress(record["collected"], record["complete"])

    def _first_open(self) -> Mission | None:
        for mission_id, mission in self._missions.items():
            if not self._progress[mission_id].complete:
                return mission
        return None


def _object(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MissionError(f"{what} must be an object")
    return value


def _mission_from_spec(spec: Any) -> Mission:
    spec = _object(spec, "a mission")
    unknown = set(spec) - _SPEC_FIELDS
    if unknown:
        raise MissionError(f"a mission has an unexpected field {sorted(unknown)[0]}")
    goal = _object(spec.get("goal"), "a mission's goal")
    opens = _object(spec.get("opens"), "a mission's opens")
    answers = spec.get("answers")
    if not isinstance(answers, list):
        raise MissionError("a mission needs answers as a list")
    return Mission(
        spec.get("id"), spec.get("title"), goal.get("resource"), goal.get("amount"),
        goal.get("destination"), spec.get("briefing"), spec.get("question"), tuple(answers),
        spec.get("hint"), spec.get("success"), opens.get("destination"), opens.get("direction"),
    )