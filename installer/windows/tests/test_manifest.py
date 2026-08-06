"""Tests for installer/windows/manifest.py.

All tests run in temporary directories; they never touch the real LAMF
installation or harness configuration.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from installer.windows.manifest import (
    DEFAULT_MANIFEST_NAME,
    generate_manifest,
    verify_manifest,
    _main,
)


class ManifestGenerationTests(unittest.TestCase):
    """Tests for manifest generation."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="lamf-manifest-"))

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel_path: str, content: str) -> Path:
        path = self.tmp / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_generate_creates_default_manifest(self) -> None:
        self._write("a.txt", "alpha")
        self._write("b/c.txt", "charlie")
        manifest = generate_manifest(self.tmp)

        self.assertEqual(manifest, self.tmp / DEFAULT_MANIFEST_NAME)
        text = manifest.read_text(encoding="utf-8")
        self.assertIn("a.txt", text)
        self.assertIn("b/c.txt", text)
        self.assertNotIn(DEFAULT_MANIFEST_NAME, text)

    def test_manifest_excludes_itself(self) -> None:
        self._write("file.txt", "x")
        manifest = generate_manifest(self.tmp)
        lines = manifest.read_text(encoding="utf-8").splitlines()
        for line in lines:
            self.assertNotIn(DEFAULT_MANIFEST_NAME, line)
        self.assertEqual(len(lines), 1)

    def test_deterministic_order(self) -> None:
        self._write("zebra.txt", "z")
        self._write("apple.txt", "a")
        self._write("nested/beta.txt", "b")
        first = generate_manifest(self.tmp).read_text(encoding="utf-8")
        second = generate_manifest(self.tmp).read_text(encoding="utf-8")
        self.assertEqual(first, second)
        paths = [line.split(None, 2)[1] for line in first.splitlines()]
        self.assertEqual(paths, sorted(paths))

    def test_custom_output_path(self) -> None:
        self._write("file.txt", "x")
        out = self.tmp / "subdir" / "checksums.txt"
        result = generate_manifest(self.tmp, out)
        self.assertEqual(result, out)
        self.assertTrue(out.is_file())


class ManifestVerificationTests(unittest.TestCase):
    """Tests for manifest verification."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="lamf-verify-"))

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel_path: str, content: str) -> Path:
        path = self.tmp / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_verify_passes_for_unchanged_tree(self) -> None:
        self._write("one.txt", "one")
        self._write("two/three.txt", "three")
        generate_manifest(self.tmp)
        result = verify_manifest(self.tmp)
        self.assertTrue(result["ok"])
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["mismatched"], [])
        self.assertEqual(result["errors"], [])

    def test_tamper_detection(self) -> None:
        target = self._write("one.txt", "one")
        generate_manifest(self.tmp)
        target.write_text("tampered", encoding="utf-8")
        result = verify_manifest(self.tmp)
        self.assertFalse(result["ok"])
        self.assertEqual(result["mismatched"], ["one.txt"])

    def test_missing_file(self) -> None:
        target = self._write("one.txt", "one")
        generate_manifest(self.tmp)
        target.unlink()
        result = verify_manifest(self.tmp)
        self.assertFalse(result["ok"])
        self.assertEqual(result["missing"], ["one.txt"])

    def test_extra_file(self) -> None:
        self._write("one.txt", "one")
        generate_manifest(self.tmp)
        self._write("two.txt", "two")
        result = verify_manifest(self.tmp)
        self.assertTrue(result["ok"])
        self.assertEqual(result["extra"], ["two.txt"])

    def test_missing_manifest(self) -> None:
        result = verify_manifest(self.tmp)
        self.assertFalse(result["ok"])
        self.assertTrue(any("not found" in e for e in result["errors"]))

    def test_malformed_manifest_line(self) -> None:
        manifest = self.tmp / DEFAULT_MANIFEST_NAME
        manifest.write_text("not-a-valid-line\n", encoding="utf-8")
        result = verify_manifest(self.tmp)
        self.assertFalse(result["ok"])
        self.assertTrue(any("malformed" in e for e in result["errors"]))


class ManifestCliTests(unittest.TestCase):
    """Tests for the manifest command-line interface."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="lamf-manifest-cli-"))

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cli_generate_and_verify(self) -> None:
        (self.tmp / "file.txt").write_text("hello", encoding="utf-8")
        code_gen = _main(["--generate", str(self.tmp)])
        self.assertEqual(code_gen, 0)
        self.assertTrue((self.tmp / DEFAULT_MANIFEST_NAME).is_file())

        code_ver = _main(["--verify", str(self.tmp)])
        self.assertEqual(code_ver, 0)

    def test_cli_verify_fails_on_tamper(self) -> None:
        target = self.tmp / "file.txt"
        target.write_text("hello", encoding="utf-8")
        _main(["--generate", str(self.tmp)])
        target.write_text("goodbye", encoding="utf-8")
        code = _main(["--verify", str(self.tmp)])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
