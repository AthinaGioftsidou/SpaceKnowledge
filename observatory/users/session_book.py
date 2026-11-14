"""SessionBook: login tokens and the players they stand for."""

import secrets
import threading


class SessionBook:
    """A token is random and unguessable, and means one player. Kept in memory
    only, so a restart logs everybody out. Safe to call from several threads."""

    def __init__(self) -> None:
        self._players: dict[str, str] = {}
        self._lock = threading.Lock()

    def open(self, player_id: str) -> str:
        if not player_id:
            raise ValueError("player_id must not be empty")
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._players[token] = player_id
        return token

    def player_for(self, token: str) -> str | None:
        if not isinstance(token, str):
            raise TypeError(f"token must be a str, not {type(token).__name__}")
        with self._lock:
            return self._players.get(token)

    def close(self, token: str) -> bool:
        """True if there was such a session."""
        with self._lock:
            return self._players.pop(token, None) is not None