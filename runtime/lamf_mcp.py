"""Universal LAMF stdio MCP entry point for every compatible agent harness."""

from __future__ import annotations

import os
import sys
from pathlib import Path

RUNTIME_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = RUNTIME_DIR.parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from lamf.cli import main  # noqa: E402


if __name__ == "__main__":
    data_dir = Path(os.environ.get("LAMF_DATA_DIR", PACKAGE_ROOT / "data"))
    raise SystemExit(main(["mcp", "--data-dir", str(data_dir)]))
