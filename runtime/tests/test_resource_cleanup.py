"""Regression tests for resource cleanup on Windows (WinError 32)."""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME_DIR = HERE.parent
sys.path.insert(0, str(RUNTIME_DIR))
sys.path.insert(0, str(HERE))

from final_test_support import new_instance  # noqa: E402
from lamf.cli import _open_ctx  # noqa: E402


def test_open_ctx_and_sqlite_connections_closed_before_removal():
    """Opening _open_ctx and a direct sqlite connection must not keep lamf.db locked."""
    root, data_dir = new_instance("lamf-cleanup-regression-")
    try:
        # Mimic final_event_recovery: direct sqlite probe plus _open_ctx store.
        conn = sqlite3.connect(data_dir / "lamf.db")
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()

        ctx = _open_ctx(data_dir)
        try:
            ctx.store.conn.execute("SELECT 1").fetchone()
        finally:
            ctx.store.close()

        # On Windows this rmtree fails if any handle to lamf.db is still open.
        shutil.rmtree(root, ignore_errors=False)
    except Exception:
        # Make sure the temporary directory is still removed on failure so the
        # test does not leak fixtures, but re-raise the original error.
        shutil.rmtree(root, ignore_errors=True)
        raise
    assert not root.exists()
