"""Harness-neutral adapter registry and configuration generator."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path


HARNESS_IDS = ("codex", "claude", "kimi", "grok", "openclaw", "hermes", "generic")


@dataclass(frozen=True)
class Harness:
    id: str
    label: str
    format: str
    config_path: str
    automatic_context: bool
    automatic_capture: bool


HARNESSES = {
    "codex": Harness("codex", "OpenAI Codex", "toml", "~/.codex/config.toml", False, False),
    "claude": Harness("claude", "Claude Code/Desktop", "json", "project .mcp.json or user MCP config", False, False),
    "kimi": Harness("kimi", "Kimi Code CLI", "json", "~/.kimi/mcp.json", False, False),
    "grok": Harness("grok", "Grok Build CLI", "toml", "~/.grok/config.toml", False, False),
    "openclaw": Harness("openclaw", "OpenClaw", "json", "openclaw mcp registry", True, True),
    "hermes": Harness("hermes", "Hermes Agent", "yaml", "~/.hermes/config.yaml", False, False),
    "generic": Harness("generic", "Generic MCP client", "json", "client-specific", False, False),
}


def server_spec(runtime_dir: Path, data_dir: Path, harness_id: str | None = None) -> dict:
    python = runtime_dir / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return {
        "command": str(python),
        "args": [str(runtime_dir / "lamf_mcp.py")],
        "env": {"LAMF_DATA_DIR": str(data_dir),
                "LAMF_HARNESS": harness_id or "generic"},
    }


def render(harness_id: str, runtime_dir: Path, data_dir: Path) -> str:
    if harness_id not in HARNESSES:
        raise ValueError(f"unknown harness {harness_id!r}")
    spec = server_spec(runtime_dir, data_dir, harness_id)
    command = spec["command"]
    launcher = spec["args"][0]
    env = spec["env"]
    if harness_id in ("codex", "grok"):
        return (
            '[mcp_servers.lamf]\n'
            f'command = {json.dumps(command)}\n'
            f'args = [{json.dumps(launcher)}]\n'
            f'env = {{ LAMF_DATA_DIR = {json.dumps(env["LAMF_DATA_DIR"])}, '
            f'LAMF_HARNESS = {json.dumps(env["LAMF_HARNESS"])} }}\n'
            'startup_timeout_sec = 30\n'
        )
    if harness_id == "hermes":
        return (
            'mcp_servers:\n  lamf:\n'
            f'    command: {json.dumps(command)}\n'
            f'    args: [{json.dumps(launcher)}]\n'
            '    env:\n'
            f'      LAMF_DATA_DIR: {json.dumps(env["LAMF_DATA_DIR"])}\n'
            f'      LAMF_HARNESS: {json.dumps(env["LAMF_HARNESS"])}\n'
        )
    entry = {"command": command, "args": [launcher], "env": env}
    if harness_id == "openclaw":
        return json.dumps({"mcp": {"servers": {"lamf-memory": {**entry, "transport": "stdio", "enabled": True}}}}, indent=2)
    return json.dumps({"mcpServers": {"lamf-memory": entry}}, indent=2)


def apply_hermes(config_path: Path, runtime_dir: Path, data_dir: Path) -> dict:
    """Idempotently merge LAMF into Hermes without disturbing other settings."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise RuntimeError("PyYAML is required to update Hermes config") from exc
    config_path = Path(config_path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if loaded is not None and not isinstance(loaded, dict):
            raise ValueError(f"Hermes config must be a YAML mapping: {config_path}")
        existing = loaded or {}
        backup = config_path.with_name(f"{config_path.name}.bak.{int(time.time())}")
        shutil.copy2(config_path, backup)
    else:
        backup = None
    servers = existing.setdefault("mcp_servers", {})
    if not isinstance(servers, dict):
        raise ValueError("Hermes mcp_servers must be a mapping")
    servers["lamf"] = server_spec(runtime_dir, data_dir, "hermes")
    tmp = config_path.with_suffix(config_path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(existing, sort_keys=False), encoding="utf-8")
    os.replace(tmp, config_path)
    return {"config": str(config_path), "backup": str(backup) if backup else None,
            "server": "lamf", "changed": True}


def apply_grok(config_path: Path, runtime_dir: Path, data_dir: Path) -> dict:
    """Idempotently maintain an owned LAMF block in Grok's TOML config."""
    config_path = Path(config_path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    begin, end = "# BEGIN LAMF MANAGED", "# END LAMF MANAGED"
    old = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    if old.count(begin) != old.count(end) or old.count(begin) > 1:
        raise ValueError(f"malformed LAMF managed block in {config_path}")
    backup = None
    if config_path.exists():
        backup = config_path.with_name(f"{config_path.name}.bak.{int(time.time())}")
        shutil.copy2(config_path, backup)
    block = f"{begin}\n{render('grok', runtime_dir, data_dir).rstrip()}\n{end}"
    if begin in old:
        prefix, rest = old.split(begin, 1)
        _, suffix = rest.split(end, 1)
        new = prefix.rstrip() + "\n\n" + block + suffix
    else:
        new = old.rstrip() + ("\n\n" if old.strip() else "") + block + "\n"
    tmp = config_path.with_suffix(config_path.suffix + ".tmp")
    tmp.write_text(new, encoding="utf-8")
    os.replace(tmp, config_path)
    return {"config": str(config_path), "backup": str(backup) if backup else None,
            "server": "lamf", "changed": old != new}


def matrix() -> list[dict]:
    return [
        {
            "id": h.id,
            "label": h.label,
            "transport": "mcp-stdio",
            "format": h.format,
            "config_path": h.config_path,
            "automatic_context": h.automatic_context,
            "automatic_capture": h.automatic_capture,
        }
        for h in HARNESSES.values()
    ]


def validate_all(runtime_dir: Path, data_dir: Path) -> list[str]:
    errors = []
    for hid in HARNESS_IDS:
        text = render(hid, runtime_dir, data_dir)
        server_marker = "lamf:" if hid == "hermes" else ("mcp_servers.lamf" if hid in ("codex", "grok") else "lamf-memory")
        if (server_marker not in text or "lamf_mcp.py" not in text
                or "LAMF_DATA_DIR" not in text or "LAMF_HARNESS" not in text):
            errors.append(f"{hid}: incomplete generated registration")
        if HARNESSES[hid].format == "json":
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                errors.append(f"{hid}: invalid JSON: {exc}")
    return errors
