"""The pages the DMZ serves: a fixed whitelist of three files, loaded once."""

from dataclasses import dataclass
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent / "web"

# URL path -> (file name, content type). Nothing else on disk can be reached,
# because a request is looked up here and never turned into a file path.
PAGES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


@dataclass(frozen=True)
class Asset:
    """One page, already read into memory. Read-only."""

    content_type: str
    data: bytes


def load_assets(directory: Path) -> dict[str, Asset]:
    """Read every whitelisted file, or refuse if one is missing, so a broken
    install fails at start-up and not on the first visit."""
    if not isinstance(directory, Path):
        raise TypeError(f"directory must be a Path, not {type(directory).__name__}")
    assets: dict[str, Asset] = {}
    for url, (filename, content_type) in PAGES.items():
        try:
            assets[url] = Asset(content_type, (directory / filename).read_bytes())
        except OSError:
            raise ValueError(f"the page file {filename} is missing in {directory}") from None
    return assets