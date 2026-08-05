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
        expected_ids = {
            "minimal-solution", "selective-workflows", "stale-context-guards",
            "surgical-changes", "verified-execution",
        }
        assert {item["id"] for item in initial["modules"]} == expected_ids
        assert all(item["enabled"] and item["valid"] for item in initial["modules"])

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

        optimizations.set_module(data, "minimal-solution", False)
        text = optimizations.compiled_instructions(data)
        assert "smallest safe solution" not in text
        assert "directly required" in text
        assert "stale context" in text

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
    print("PASS: every module switch is isolated and invalid state fails open")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
