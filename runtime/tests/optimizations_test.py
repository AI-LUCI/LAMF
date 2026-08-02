"""Core optimization-loader tests with no optional pack installed."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME))

from lamf import optimizations  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        data = Path(td) / "data"
        optimizations.initialize(data)
        initial = optimizations.status(data)
        assert initial["enabled"]
        assert initial["modules"] == []
        assert optimizations.compiled_instructions(data) == ""

        try:
            optimizations.set_module(data, "not-installed", False)
        except ValueError as exc:
            assert "unknown optimization" in str(exc)
        else:
            raise AssertionError("missing modules must not appear configurable")

        optimizations.set_global(data, False)
        assert optimizations.compiled_instructions(data) == ""
        optimizations.set_global(data, True)
        assert optimizations.compiled_instructions(data) == ""

        optimizations.config_path(data).write_text("{broken", encoding="utf-8")
        broken = optimizations.status(data)
        assert broken["config_error"] and not broken["enabled"]
        assert optimizations.compiled_instructions(data) == ""

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
    print("PASS: core works without the optional pack and invalid state fails open")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
