"""Writing a JSON file so that it is never half written."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomically(path: Path, document: Any) -> None:
    """Write `document` to a UNIQUE temporary file, then swap it over `path`.

    At every moment `path` holds either the complete old file or the complete
    new one. On failure the old file is kept and our temporary file is removed.
    The temporary name is unique, so two writers never share one, and a
    leftover from a crashed writer is never mistaken for ours.
    """
    text = json.dumps(document, indent=2)  # first, so a bad document leaves nothing
    path.parent.mkdir(parents=True, exist_ok=True)
    # In the same folder, because a rename is only atomic inside one filesystem.
    # mkstemp creates the file readable by this user only.
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