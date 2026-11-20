"""Test discovery imports this package before any test module, so the Python
version is checked here, once, before an older interpreter fails on the
annotations in every module with a NameError.

To try an older Python anyway, set STOP_ON_OLD_PYTHON to False.
"""

import sys

STOP_ON_OLD_PYTHON = True

if STOP_ON_OLD_PYTHON and sys.version_info < (3, 14):
    raise SystemExit(
        f"These tests need Python 3.14; this is Python {sys.version.split()[0]}. "
        "In VS Code: Ctrl+Shift+P, Python: Select Interpreter."
    )
