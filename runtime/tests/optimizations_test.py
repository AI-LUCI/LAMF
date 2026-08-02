"""Isolation and switching tests for LAMF agent optimizations."""

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
        assert len(initial["modules"]) == 4
        assert all(item["enabled"] and item["valid"] for item in initial["modules"])

        optimizations.set_module(data, "minimal-solution", False)
        partial = optimizations.status(data)
        states = {item["id"]: item["enabled"] for item in partial["modules"]}
        assert not states["minimal-solution"]
        assert all(value for key, value in states.items() if key != "minimal-solution")
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
    print("PASS: global and per-module switches are isolated and fail open")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
