"""Cross-harness contract test: one launcher, one data directory, valid configs."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

RUNTIME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME))

from lamf.harness import (
    HARNESS_IDS, HARNESSES, apply_generic_json, apply_grok, apply_hermes,
    remove_generic_json, remove_grok, remove_hermes, render, server_spec,
    validate_all,
)  # noqa: E402
from lamf import api, mcp_server, optimizations  # noqa: E402
from final_test_support import new_instance  # noqa: E402


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
        assert "independently switchable" not in instructions
        print("PASS optimization boundary: core emits no separately distributed modules")
    root, private_data = new_instance("lamf-harness-privacy-")
    try:
        from lamf.store import Store
        from lamf.spine import Spine
        policy = {"profile": "controlled", "version": 1,
                  "context": {"capsule_max_tokens": 1200}}
        store = Store.open(str(private_data / "lamf.db"),
                           str(RUNTIME.parent / "04_STORAGE" / "SCHEMA.sql"))
        ctx = SimpleNamespace(store=store, spine=Spine(private_data / "spine", store.key),
                              policy=policy, data_dir=str(private_data))
        api.remember(ctx, {"title": "ordinary harness fact", "body": "shared safe detail",
                           "record_type": "fact", "scope": "test:privacy"})
        api.remember(ctx, {"title": "sensitive harness fact", "body": "private detail",
                           "record_type": "fact", "scope": "test:privacy",
                           "sensitivity": "sensitive"})
        default_hits = api.search(ctx, "harness fact", limit=10)["results"]
        elevated_hits = api.search(ctx, "harness fact", limit=10,
                                   filters={"sensitivity_max": "sensitive"})["results"]
        assert {r["sensitivity"] for r in default_hits} == {"ordinary"}
        assert {r["sensitivity"] for r in elevated_hits} == {"ordinary", "sensitive"}
        orientation = api.orientation(ctx)
        assert "private detail" not in json.dumps(orientation)
        print("PASS privacy baseline: automatic/default recall is ordinary-only")
        store.close()
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)
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
    with tempfile.TemporaryDirectory() as td:
        config = Path(td) / "mcp.json"
        apply_generic_json(config, RUNTIME, data, owned_key="lamf-memory", harness_id="gemini")
        first = json.loads(config.read_text(encoding="utf-8"))
        apply_generic_json(config, RUNTIME, data, owned_key="lamf-memory", harness_id="gemini")
        second = json.loads(config.read_text(encoding="utf-8"))
        assert first == second
        assert "mcpServers" in second
        assert "lamf-memory" in second["mcpServers"]
        assert second["mcpServers"]["lamf-memory"]["env"]["LAMF_HARNESS"] == "gemini"
        remove_generic_json(config, "lamf-memory")
        removed = json.loads(config.read_text(encoding="utf-8"))
        assert "lamf-memory" not in removed.get("mcpServers", {})
        assert list(Path(td).glob("mcp.json.bak.*"))
        print("PASS gemini apply/disconnect: JSON mcpServers round trip + backup")
    with tempfile.TemporaryDirectory() as td:
        config = Path(td) / "config.toml"
        config.write_text('model = "grok-test"\n', encoding="utf-8")
        apply_grok(config, RUNTIME, data)
        remove_grok(config)
        final = config.read_text(encoding="utf-8")
        assert "# BEGIN LAMF MANAGED" not in final
        assert 'model = "grok-test"' in final
        assert list(Path(td).glob("config.toml.bak.*"))
        print("PASS grok disconnect: managed block removed, unrelated settings preserved")
    with tempfile.TemporaryDirectory() as td:
        config = Path(td) / "config.yaml"
        config.write_text("model: test-model\nmcp_servers:\n  existing:\n    command: keep-me\n", encoding="utf-8")
        apply_hermes(config, RUNTIME, data)
        remove_hermes(config)
        final = yaml.safe_load(config.read_text(encoding="utf-8"))
        assert "lamf" not in final.get("mcp_servers", {})
        assert final["model"] == "test-model"
        assert final["mcp_servers"]["existing"]["command"] == "keep-me"
        assert list(Path(td).glob("config.yaml.bak.*"))
        print("PASS hermes disconnect: lamf entry removed, unrelated settings preserved")
    print(f"PASS matrix: {len(HARNESS_IDS)} harnesses, one LAMF installation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
