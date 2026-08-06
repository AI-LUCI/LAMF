"""Tests for installer/windows/build_config.py.

All tests run in temporary directories and use synthetic files only.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from installer.windows.build_config import (
    BUILD_REQUIREMENTS,
    CFFI_VERSION,
    CFFI_WHEEL_SHA256,
    INNO_SETUP_SHA256,
    INNO_SETUP_VERSION,
    OPTIMIZATION_PACK_COMMIT,
    PYNACL_VERSION,
    PYNACL_WHEEL_SHA256,
    PYCPARSER_VERSION,
    PYCPARSER_WHEEL_SHA256,
    PYYAML_VERSION,
    PYYAML_WHEEL_SHA256,
    PYTHON_EMBED_SHA256,
    PYTHON_EMBED_VERSION,
    BuildConfig,
    default_build_config,
    verify_sha256,
)


class BuildConfigTests(unittest.TestCase):
    """Tests for pinned build configuration."""

    def test_default_build_config_matches_constants(self) -> None:
        cfg = default_build_config()
        self.assertEqual(cfg.python_version, PYTHON_EMBED_VERSION)
        self.assertEqual(cfg.python_embed_sha256, PYTHON_EMBED_SHA256)
        self.assertEqual(cfg.pyyaml_version, PYYAML_VERSION)
        self.assertEqual(cfg.pyyaml_wheel_sha256, PYYAML_WHEEL_SHA256)
        self.assertEqual(cfg.pynacl_version, PYNACL_VERSION)
        self.assertEqual(cfg.pynacl_wheel_sha256, PYNACL_WHEEL_SHA256)
        self.assertEqual(cfg.cffi_version, CFFI_VERSION)
        self.assertEqual(cfg.cffi_wheel_sha256, CFFI_WHEEL_SHA256)
        self.assertEqual(cfg.pycparser_version, PYCPARSER_VERSION)
        self.assertEqual(cfg.pycparser_wheel_sha256, PYCPARSER_WHEEL_SHA256)
        self.assertEqual(cfg.inno_setup_version, INNO_SETUP_VERSION)
        self.assertEqual(cfg.inno_setup_sha256, INNO_SETUP_SHA256)
        self.assertEqual(cfg.optimization_pack_commit, OPTIMIZATION_PACK_COMMIT)

    def test_requirement_ids_present(self) -> None:
        for req_id in ("R-WIN-01", "R-WIN-02", "R-WIN-03", "R-WIN-04", "R-WIN-05", "R-WIN-06"):
            self.assertIn(req_id, BUILD_REQUIREMENTS)
            self.assertIsInstance(BUILD_REQUIREMENTS[req_id], str)

    def test_verify_sha256_matches_known_content(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.txt"
            content = b"LAMF Windows installer build input"
            path.write_bytes(content)
            expected = hashlib.sha256(content).hexdigest()
            self.assertTrue(verify_sha256(path, expected))

    def test_verify_sha256_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.txt"
            path.write_text("hello", encoding="utf-8")
            expected = hashlib.sha256(b"hello").hexdigest().upper()
            self.assertTrue(verify_sha256(path, expected))

    def test_verify_sha256_detects_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.txt"
            path.write_text("hello", encoding="utf-8")
            wrong = "0" * 64
            self.assertFalse(verify_sha256(path, wrong))


if __name__ == "__main__":
    unittest.main()
