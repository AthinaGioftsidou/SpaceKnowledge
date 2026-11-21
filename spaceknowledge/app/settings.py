"""Settings: where the Universe listens, which Brokers may connect, which ports
their DMZs use, and who the administrators are."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from spaceknowledge.users.credentials import check_username

DEFAULT_PORT = 7400
DEFAULT_DMZ_BASE_PORT = 8400

# Names become folder names and peer names, so they are strictly limited.
_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,29}")


class SettingsError(ValueError):
    """A settings file or value that cannot be trusted."""


def is_valid_name(name: object) -> bool:
    """A Broker's name: lower case letters, digits, - and _, at most 30
    characters. "universe" is reserved for the Universe itself."""
    return isinstance(name, str) and name != "universe" and _NAME.fullmatch(name) is not None


@dataclass(frozen=True)
class Settings:
    """Read-only. The defaults let everything start with no settings file.

    Each Broker's DMZ listens on `dmz_base_port` plus the Broker's position in
    `brokers`, so the first Broker gets the base port, the next one the port
    after it, and so on. `admins` are the names that may ask for a one-time
    admin code."""

    universe_host: str = "127.0.0.1"
    universe_port: int = DEFAULT_PORT
    brokers: tuple[str, ...] = ("broker-1", "broker-2")
    start: str = "earth"
    dmz_base_port: int = DEFAULT_DMZ_BASE_PORT
    admins: tuple[str, ...] = ("root",)

    def __post_init__(self) -> None:
        if not isinstance(self.universe_host, str) or not self.universe_host:
            raise SettingsError("universe_host must be non-empty text")
        port = self.universe_port
        if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
            raise SettingsError("universe_port must be a whole number from 1 to 65535")
        if not isinstance(self.brokers, tuple) or not self.brokers:
            raise SettingsError("brokers must be a non-empty list of names")
        for name in self.brokers:
            if not is_valid_name(name):
                raise SettingsError(f"{name!r} is not a valid Broker name")
        if len(set(self.brokers)) != len(self.brokers):
            raise SettingsError("a Broker name is listed twice")
        if not isinstance(self.start, str) or not self.start:
            raise SettingsError("start must be non-empty text")
        base = self.dmz_base_port
        if isinstance(base, bool) or not isinstance(base, int) or not 0 < base < 65536:
            raise SettingsError("dmz_base_port must be a whole number from 1 to 65535")
        last = base + len(self.brokers) - 1
        if last >= 65536:
            raise SettingsError("dmz_base_port leaves no room for every Broker's port")
        if base <= port <= last:
            raise SettingsError("the DMZ ports must not include the Universe's port")
        if not isinstance(self.admins, tuple) or not self.admins:
            raise SettingsError("admins must be a non-empty list of names")
        for admin in self.admins:
            if (not isinstance(admin, str) or admin != admin.strip().lower()
                    or check_username(admin) is not None):
                raise SettingsError(f"{admin!r} is not a valid administrator name")
        if len(set(self.admins)) != len(self.admins):
            raise SettingsError("an administrator name is listed twice")

    def dmz_port(self, name: str) -> int:
        """The port this Broker's DMZ listens on."""
        if name not in self.brokers:
            raise SettingsError(f"{name} is not one of the brokers")
        return self.dmz_base_port + self.brokers.index(name)


_FIELDS = {"universe_host", "universe_port", "brokers", "start", "dmz_base_port", "admins"}
_LISTS = ("brokers", "admins")


def load_settings(path: Path) -> Settings:
    """The settings in `path`, or the defaults if there is no such file."""
    if not isinstance(path, Path):
        raise TypeError(f"path must be a Path, not {type(path).__name__}")
    if not path.exists():
        return Settings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as problem:
        raise SettingsError(f"{path.name} is not valid JSON ({problem})") from None
    if not isinstance(raw, dict):
        raise SettingsError(f"{path.name} must hold a JSON object")
    unknown = set(raw) - _FIELDS
    if unknown:
        raise SettingsError(f"{path.name} has an unknown setting {sorted(unknown)[0]}")
    values = dict(raw)
    for key in _LISTS:
        if key in values:
            if not isinstance(values[key], list):
                raise SettingsError(f"{key} must be a list of names")
            values[key] = tuple(values[key])
    return Settings(**values)