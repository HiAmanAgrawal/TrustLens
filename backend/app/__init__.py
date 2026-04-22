"""TrustLens backend package.

Importing this package must remain side-effect-free for FastAPI itself: no
HTTP app is constructed here. The app is built explicitly via
``app.main.create_app()`` so tests can build their own instance with a
different config.

The one side effect we DO accept: prepending the repo root to ``sys.path`` so
the sibling ``services/`` package is importable when the backend is run from
the ``backend/`` directory (``uvicorn app.main:app`` or ``pytest``). Doing it
here keeps every other module — and every test — free of path hacks.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
