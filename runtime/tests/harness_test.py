"""Cross-harness contract test: one launcher, one data directory, valid configs."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

RUNTIME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME))

from lamf.harness import HARNESS_IDS, HARNESSES, apply_grok, apply_hermes, render, server_spec, validate_all  # noqa: E402
from lamf import mcp_server, optimizations  # noqa: E402


def main() -> int:
    data = RUNTIME.parent / "data"
    errors = validate_all(RUNTIME, data)
    assert not errors, errors
    for hid in HARNESS_IDS:
        text = render(hid, RUNTIME, data)
        assert "lamf_mcp.py" in text
        assert "LAMF_DATA_DIR" in text
        assert "LAMF_HARNESS" in text and hid in text
        if HARNESSES[hid].format == "json":
            json.loads(text)
        print(f"PASS {hid}: shared MCP launcher + shared authority")
    with tempfile.TemporaryDirectory() as td:
        optimization_data = Path(td) / "data"
        optimizations.initialize(optimization_data)
        instructions = mcp_server.server_instructions(
            SimpleNamespace(data_dir=str(optimization_data)))
        if optimizations.discover():
            assert "stale context" in instructions
            assert "independently switchable" in instructions
            print("PASS optimization delivery: optional modules reach MCP instructions")
        else:
            assert "independently switchable" not in instructions
            print("PASS optimization delivery: core emits no optional instructions")
    import yaml
    with tempfile.TemporaryDirectory() as td:
        config = Path(td) / "config.yaml"
        config.write_text("model: test-model\nmcp_servers:\n  existing:\n    command: keep-me\n", encoding="utf-8")
        apply_hermes(config, RUNTIME, data)
        first = yaml.safe_load(config.read_text(encoding="utf-8"))
        apply_hermes(config, RUNTIME, data)
        second = yaml.safe_load(config.read_text(encoding="utf-8"))
        assert first == second
        assert second["model"] == "test-model"
        assert second["mcp_servers"]["existing"]["command"] == "keep-me"
        assert second["mcp_servers"]["lamf"]["args"][0].endswith("lamf_mcp.py")
        assert list(Path(td).glob("config.yaml.bak.*"))
        print("PASS hermes apply: idempotent merge + backup + unrelated settings preserved")
    with tempfile.TemporaryDirectory() as td:
        config = Path(td) / "config.toml"
        config.write_text('model = "grok-test"\n', encoding="utf-8")
        apply_grok(config, RUNTIME, data)
        first = config.read_text(encoding="utf-8")
        apply_grok(config, RUNTIME, data)
        second = config.read_text(encoding="utf-8")
        assert first == second
        assert 'model = "grok-test"' in second
        assert second.count("# BEGIN LAMF MANAGED") == 1
        assert "[mcp_servers.lamf]" in second and "lamf_mcp.py" in second
        assert list(Path(td).glob("config.toml.bak.*"))
        print("PASS grok apply: idempotent managed block + backup + unrelated settings preserved")
    print(f"PASS matrix: {len(HARNESS_IDS)} harnesses, one LAMF installation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
