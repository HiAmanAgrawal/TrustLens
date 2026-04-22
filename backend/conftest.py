"""Make the sibling ``services/`` package importable from inside tests.

The same path tweak lives in ``app/__init__.py`` for the runtime side, but
pytest can collect test files (e.g. ``test_matcher_compare.py``) that import
``services`` directly without ever touching ``app``. This file runs before
collection, so the path is set early enough for those imports to succeed.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
