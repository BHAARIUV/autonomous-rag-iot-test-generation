"""
Thin launcher so the app can be started from the repository root with:

    python run.py

The application code lives under `backend/app/`. This launcher adds `backend/`
to `sys.path` (so the `app` package resolves) and delegates to app.main.run().
Keeping this file tiny means the real logic lives in app/ where it's testable
and importable, while this stays the one obvious "start here" entry point.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_BACKEND = _ROOT / "backend"

if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.main import run  # noqa: E402

if __name__ == "__main__":
    run()
