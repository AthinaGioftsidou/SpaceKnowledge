"""Writing a JSON file so that it is never half written."""

import json
import os
from pathlib import Path
from typing import Any


def write_json_atomically(path: Path, document: Any) -> None:
    """Write `document` to a temporary file, then swap it over `path`.

    At every moment `path` holds either the complete old file or the complete
    new one. On failure the old file is kept and nothing is left behind.
    """
    text = json.dumps(document, indent=2)  # before any file exists, so a bad document leaves nothing
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise