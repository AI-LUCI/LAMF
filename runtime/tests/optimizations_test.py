"""Isolation and switching tests for LAMF agent optimizations."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME))

from lamf import optimizations  # noqa: E402

EXTERNAL_MODULES = Path(os.environ.get(
    "LAMF_OPTIMIZATION_PACK_SOURCE",
    "E:/LAMF-Optimizations-GitHub/optimizations/modules",
))


def _copy_module_pack(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _fake_optimizations_file(root: Path) -> Path:
    fake_file = root / "runtime" / "lamf" / "optimizations.py"
    fake_file.parent.mkdir(parents=True)
    fake_file.write_text("# stub", encoding="utf-8")
    return fake_file


class _PatchedFile:
    def __init__(self, fake_file: Path) -> None:
        self.fake_file = fake_file
        self.old_file: str = ""

    def __enter__(self) -> "_PatchedFile":
        self.old_file = optimizations.__file__
        optimizations.__file__ = str(self.fake_file)
        return self

    def __exit__(self, *args: object) -> None:
        optimizations.__file__ = self.old_file


def test_module_root_payload_layout() -> None:
    with tempfile.TemporaryDirectory() as td:
        fake_root = Path(td)
        installed_modules = fake_root / "optimizations" / "optimizations" / "modules"
        installed_modules.mkdir(parents=True)
        fake_file = _fake_optimizations_file(fake_root)
        with _PatchedFile(fake_file):
            assert optimizations.module_root() == installed_modules


def test_module_root_compatibility_layout() -> None:
    with tempfile.TemporaryDirectory() as td:
        fake_root = Path(td)
        compat_modules = fake_root / "optimizations" / "modules"
        compat_modules.mkdir(parents=True)
        fake_file = _fake_optimizations_file(fake_root)
        with _PatchedFile(fake_file):
            assert optimizations.module_root() == compat_modules


def test_module_root_source_fallback_layout() -> None:
    with tempfile.TemporaryDirectory() as td:
        fake_root = Path(td)
        source_modules = fake_root / "05_INTEGRATIONS" / "optimizations" / "modules"
        source_modules.mkdir(parents=True)
        fake_file = _fake_optimizations_file(fake_root)
        with _PatchedFile(fake_file):
            assert optimizations.module_root() == source_modules


def test_source_mode_uses_resolved_root() -> None:
    """set_module and compiled_instructions can use module_root() without an explicit root."""
    if not EXTERNAL_MODULES.exists():
        raise RuntimeError(f"external modules root not found: {EXTERNAL_MODULES}")

    with tempfile.TemporaryDirectory() as td:
        fake_root = Path(td)
        source_modules = fake_root / "05_INTEGRATIONS" / "optimizations" / "modules"
        _copy_module_pack(EXTERNAL_MODULES, source_modules)
        fake_file = _fake_optimizations_file(fake_root)

        with _PatchedFile(fake_file):
            resolved_root = optimizations.module_root()
            assert resolved_root == source_modules

            data = Path(td) / "data"
            optimizations.initialize(data)
            initial = optimizations.status(data)
            assert initial["enabled"]
            expected_ids = {
                "minimal-solution", "selective-workflows", "stale-context-guards",
                "surgical-changes", "verified-execution",
            }
            assert {item["id"] for item in initial["modules"]} == expected_ids
            assert all(item["enabled"] and item["valid"] for item in initial["modules"])

            optimizations.set_module(data, "minimal-solution", False)
            text = optimizations.compiled_instructions(data)
            assert "smallest safe solution" not in text
            assert "directly required" in text

            optimizations.set_global(data, False)
            assert optimizations.compiled_instructions(data) == ""
            optimizations.set_global(data, True)
            assert "directly required" in optimizations.compiled_instructions(data)

            optimizations.config_path(data).write_text("{broken", encoding="utf-8")
            broken = optimizations.status(data)
            assert broken["config_error"] and not broken["enabled"]
            assert optimizations.compiled_instructions(data) == ""


def test_isolated_module_switching() -> None:
    if not EXTERNAL_MODULES.exists():
        raise RuntimeError(f"external modules root not found: {EXTERNAL_MODULES}")

    with tempfile.TemporaryDirectory() as td:
        fake_root = Path(td)
        source_modules = fake_root / "05_INTEGRATIONS" / "optimizations" / "modules"
        _copy_module_pack(EXTERNAL_MODULES, source_modules)
        fake_file = _fake_optimizations_file(fake_root)

        with _PatchedFile(fake_file):
            data = Path(td) / "data"
            optimizations.initialize(data)
            expected_ids = {
                "minimal-solution", "selective-workflows", "stale-context-guards",
                "surgical-changes", "verified-execution",
            }
            for module_id in sorted(expected_ids):
                isolated_data = Path(td) / f"isolated-{module_id}"
                optimizations.initialize(isolated_data)
                optimizations.set_module(isolated_data, module_id, False)
                states = {
                    item["id"]: item["enabled"]
                    for item in optimizations.status(isolated_data)["modules"]
                }
                assert states[module_id] is False
                assert all(value for key, value in states.items() if key != module_id)


def test_module_validation() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "modules"
        good = root / "good"
        bad = root / "bad"
        good.mkdir(parents=True)
        bad.mkdir(parents=True)
        (good / "module.json").write_text(json.dumps({
            "id": "good", "version": "1", "default_enabled": True,
            "instruction_file": "instruction.md"}), encoding="utf-8")
        (good / "instruction.md").write_text("healthy", encoding="utf-8")
        (bad / "module.json").write_text("{}", encoding="utf-8")
        found = {item["id"]: item for item in optimizations.discover(root)}
        assert found["good"]["error"] is None
        assert found["bad"]["error"]


def main() -> int:
    test_module_root_payload_layout()
    test_module_root_compatibility_layout()
    test_module_root_source_fallback_layout()
    test_source_mode_uses_resolved_root()
    test_isolated_module_switching()
    test_module_validation()
    print("PASS: every module switch is isolated and invalid state fails open")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
