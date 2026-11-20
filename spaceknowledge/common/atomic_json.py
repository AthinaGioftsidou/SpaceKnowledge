"""Writing a file so that it is never half written."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_text_atomically(path: Path, text: str) -> None:
    """Write `text` to a UNIQUE temporary file, then swap it over `path`.

    At every moment `path` holds either the complete old file or the complete
    new one. On failure the old file is kept and our temporary file is removed.
    The temporary name is unique, so two writers never share one. `mkstemp`
    creates the file readable by its owner only, and `os.replace` keeps that
    on POSIX systems.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # In the same folder, because a rename is only atomic inside one filesystem.
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def write_json_atomically(path: Path, document: Any) -> None:
    """Like `write_text_atomically`, for a JSON document. The document is
    converted first, so one that cannot be converted leaves nothing behind."""
    write_text_atomically(path, json.dumps(document, indent=2))