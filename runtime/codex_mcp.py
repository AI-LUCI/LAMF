"""Compatibility alias for the universal harness-neutral MCP launcher."""

from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("lamf_mcp.py")), run_name="__main__")
