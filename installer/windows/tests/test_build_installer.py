"""Tests for installer/windows/build_installer.py CLI and path handling."""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_installer  # noqa: E402


def test_cli_help_includes_optimization_pack_source():
    """--help must document the optimization pack source option."""
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = StringIO()
    sys.stderr = StringIO()
    try:
        try:
            build_installer.main(["--help"])
        except SystemExit as exc:
            assert exc.code == 0
    finally:
        stdout = sys.stdout.getvalue()
        stderr = sys.stderr.getvalue()
        sys.stdout = old_stdout
        sys.stderr = old_stderr
    combined = stdout + stderr
    assert "--optimization-pack-source" in combined
    assert "LAMF_OPTIMIZATION_PACK_SOURCE" in combined


def test_build_installer_signature_accepts_optimization_pack_source():
    """build_installer() must accept an optimization_pack_source keyword."""
    varnames = build_installer.build_installer.__code__.co_varnames
    assert "optimization_pack_source" in varnames
