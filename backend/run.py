"""Run ParseIQ API: python -m backend.run  (from ParseIQ root)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    import uvicorn

    uvicorn.run(
        "backend.app:app",
        host="127.0.0.1",
        port=8000,
        # The dev launcher supervises this process. Uvicorn's separate
        # autoreload worker is unnecessary and can orphan workers on Windows.
        reload=False,
        app_dir=str(ROOT),
    )


if __name__ == "__main__":
    main()
