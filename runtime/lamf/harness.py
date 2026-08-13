"""Harness-neutral adapter registry and configuration generator."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path


def _atomic_write(path: Path, content: str) -> None:
    """Write *content* to a sibling temp file and replace *path* atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


HARNESS_IDS = ("codex", "claude", "kimi", "gemini", "grok", "openclaw", "hermes", "generic")


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
    # Kimi Code 0.23.x uses ~/.kimi-code/mcp.json. The legacy ~/.kimi/mcp.json
    # path is detected at runtime but not mutated unless the operator still uses it.
    "kimi": Harness("kimi", "Kimi Code CLI", "json", "~/.kimi-code/mcp.json", False, False),
    # Gemini CLI documents its user config as ~/.gemini/settings.json with a
    # top-level mcpServers object.
    "gemini": Harness("gemini", "Gemini CLI", "json", "~/.gemini/settings.json", False, False),
    "grok": Harness("grok", "Grok Build CLI", "toml", "~/.grok/config.toml", False, False),
    "openclaw": Harness("openclaw", "OpenClaw", "json", "openclaw mcp registry", True, True),
    "hermes": Harness("hermes", "Hermes Agent", "yaml", "~/.hermes/config.yaml", False, False),
    "generic": Harness("generic", "Generic MCP client", "json", "client-specific", False, False),
}


KIMI_LEGACY_PATH = Path("~/.kimi/mcp.json")


def kimi_config_path(config_dir: Path | None = None) -> Path:
    """Return the active Kimi config path, preferring the modern default.

    If the legacy ~/.kimi/mcp.json exists and the modern ~/.kimi-code/mcp.json
    does not, the legacy path is returned for read-only detection. The
    installer mutates only the path the operator confirms.
    """
    if config_dir is not None:
        return Path(config_dir).expanduser() / "mcp.json"
    modern = Path(HARNESSES["kimi"].config_path).expanduser()
    legacy = KIMI_LEGACY_PATH.expanduser()
    if legacy.exists() and not modern.exists():
        return legacy
    return modern


def _is_packaged(runtime_dir: Path) -> bool:
    """True when *runtime_dir* is the app/ folder of an installed layout."""
    runtime_dir = Path(runtime_dir)
    install_dir = runtime_dir.parent
    packaged_lamf = install_dir / "lamf.exe"
    return packaged_lamf.is_file() and not (runtime_dir / ".venv").is_dir()


def server_spec(runtime_dir: Path, data_dir: Path, harness_id: str | None = None) -> dict:
    """Return the MCP server registration spec for *harness_id*.

    In a packaged installation the spec invokes the installed ``lamf.exe``
    directly with ``lamf.exe mcp --harness <id>``. In a source tree it falls
    back to the private venv Python launcher and ``lamf_mcp.py``.
    """
    runtime_dir = Path(runtime_dir)
    data_dir = Path(data_dir)
    harness_id = harness_id or "generic"
    if _is_packaged(runtime_dir):
        install_dir = runtime_dir.parent
        return {
            "command": str(install_dir / "lamf.exe"),
            "args": ["mcp", "--harness", harness_id],
            "env": {"LAMF_DATA_DIR": str(data_dir),
                    "LAMF_HARNESS": harness_id},
        }
    python = runtime_dir / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return {
        "command": str(python),
        "args": [str(runtime_dir / "lamf_mcp.py")],
        "env": {"LAMF_DATA_DIR": str(data_dir),
                "LAMF_HARNESS": harness_id},
    }


def render(harness_id: str, runtime_dir: Path, data_dir: Path) -> str:
    if harness_id not in HARNESSES:
        raise ValueError(f"unknown harness {harness_id!r}")
    spec = server_spec(runtime_dir, data_dir, harness_id)
    command = spec["command"]
    args = spec["args"]
    env = spec["env"]
    args_json = ", ".join(json.dumps(a) for a in args)
    if harness_id in ("codex", "grok"):
        return (
            '[mcp_servers.lamf]\n'
            f'command = {json.dumps(command)}\n'
            f'args = [{args_json}]\n'
            f'env = {{ LAMF_DATA_DIR = {json.dumps(env["LAMF_DATA_DIR"])}, '
            f'LAMF_HARNESS = {json.dumps(env["LAMF_HARNESS"])} }}\n'
            'startup_timeout_sec = 30\n'
        )
    if harness_id == "hermes":
        return (
            'mcp_servers:\n  lamf:\n'
            f'    command: {json.dumps(command)}\n'
            f'    args: [{args_json}]\n'
            '    env:\n'
            f'      LAMF_DATA_DIR: {json.dumps(env["LAMF_DATA_DIR"])}\n'
            f'      LAMF_HARNESS: {json.dumps(env["LAMF_HARNESS"])}\n'
        )
    entry = {"command": command, "args": list(args), "env": env}
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


def _apply_toml_block(config_path: Path, runtime_dir: Path, data_dir: Path,
                      harness_id: str) -> dict:
    """Idempotently maintain an owned LAMF block in a TOML config.

    Shared by Grok and Codex, which both use ``~/.<tool>/config.toml`` with an
    ``[mcp_servers.lamf]`` table. The managed block is delimited so unrelated
    settings are preserved verbatim and re-runs are idempotent.
    """
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
    block = f"{begin}\n{render(harness_id, runtime_dir, data_dir).rstrip()}\n{end}"
    if begin in old:
        prefix, rest = old.split(begin, 1)
        _, suffix = rest.split(end, 1)
        prefix = prefix.rstrip()
        new = (prefix + "\n\n" if prefix else "") + block + suffix
    else:
        new = old.rstrip() + ("\n\n" if old.strip() else "") + block + "\n"
    tmp = config_path.with_suffix(config_path.suffix + ".tmp")
    tmp.write_text(new, encoding="utf-8")
    os.replace(tmp, config_path)
    return {"config": str(config_path), "backup": str(backup) if backup else None,
            "server": "lamf", "changed": old != new}


def apply_grok(config_path: Path, runtime_dir: Path, data_dir: Path) -> dict:
    """Idempotently maintain an owned LAMF block in Grok's TOML config."""
    return _apply_toml_block(config_path, runtime_dir, data_dir, "grok")


def apply_codex(config_path: Path, runtime_dir: Path, data_dir: Path) -> dict:
    """Idempotently maintain an owned LAMF block in Codex's TOML config."""
    return _apply_toml_block(config_path, runtime_dir, data_dir, "codex")


def _remove_toml_block(config_path: Path) -> dict:
    """Remove the LAMF managed block from a TOML config (Grok/Codex)."""
    config_path = Path(config_path).expanduser()
    if not config_path.exists():
        return {"config": str(config_path), "removed": False, "changed": False}
    begin, end = "# BEGIN LAMF MANAGED", "# END LAMF MANAGED"
    old = config_path.read_text(encoding="utf-8")
    if begin not in old:
        return {"config": str(config_path), "removed": False, "changed": False}
    if old.count(begin) != old.count(end) or old.count(begin) > 1:
        raise ValueError(f"malformed LAMF managed block in {config_path}")
    backup = config_path.with_name(f"{config_path.name}.bak.{int(time.time())}")
    shutil.copy2(config_path, backup)
    prefix, rest = old.split(begin, 1)
    _, suffix = rest.split(end, 1)
    new = prefix.rstrip("\n") + "\n" + suffix.lstrip("\n")
    new = new.strip("\n") + "\n" if new.strip() else ""
    _atomic_write(config_path, new)
    return {"config": str(config_path), "backup": str(backup),
            "removed": True, "changed": True}


def apply_generic_json(config_path: Path, runtime_dir: Path, data_dir: Path,
                       owned_key: str = "lamf-memory",
                       harness_id: str | None = None) -> dict:
    """Idempotently merge a LAMF server into a JSON ``mcpServers`` config.

    Used for Kimi, Gemini, Claude, and the generic MCP adapter.
    """
    config_path = Path(config_path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    backup = None
    if config_path.exists():
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        if loaded is not None and not isinstance(loaded, dict):
            raise ValueError(f"JSON config must be an object: {config_path}")
        existing = loaded or {}
        backup = config_path.with_name(f"{config_path.name}.bak.{int(time.time())}")
        shutil.copy2(config_path, backup)
    servers = existing.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("mcpServers must be a mapping")
    servers[owned_key] = server_spec(runtime_dir, data_dir, harness_id or owned_key)
    _atomic_write(config_path, json.dumps(existing, indent=2) + "\n")
    return {"config": str(config_path), "backup": str(backup) if backup else None,
            "server": owned_key, "changed": True}


def remove_generic_json(config_path: Path, owned_key: str = "lamf-memory") -> dict:
    """Remove the LAMF-owned server entry from a JSON ``mcpServers`` config."""
    config_path = Path(config_path).expanduser()
    if not config_path.exists():
        return {"config": str(config_path), "removed": False, "changed": False}
    loaded = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"JSON config must be an object: {config_path}")
    servers = loaded.get("mcpServers")
    if not isinstance(servers, dict) or owned_key not in servers:
        return {"config": str(config_path), "removed": False, "changed": False}
    backup = config_path.with_name(f"{config_path.name}.bak.{int(time.time())}")
    shutil.copy2(config_path, backup)
    del servers[owned_key]
    if not servers:
        del loaded["mcpServers"]
    _atomic_write(config_path, json.dumps(loaded, indent=2) + "\n")
    return {"config": str(config_path), "backup": str(backup),
            "removed": True, "changed": True}


def remove_grok(config_path: Path) -> dict:
    """Remove the LAMF managed block from Grok's TOML config."""
    return _remove_toml_block(config_path)


def remove_codex(config_path: Path) -> dict:
    """Remove the LAMF managed block from Codex's TOML config."""
    return _remove_toml_block(config_path)


def apply_openclaw(config_path: Path, runtime_dir: Path, data_dir: Path) -> dict:
    """Idempotently merge the LAMF MCP fallback server into openclaw.json.

    Only the ``mcp.servers.lamf`` slot is owned here; the plugin entry, memory
    slot and agent skill are installed by ``installer/install.py``'s OpenClaw
    step (DECISIONS.md §W-03). Unrelated settings are preserved and a backup is
    made before any change.
    """
    config_path = Path(config_path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    backup = None
    if config_path.exists():
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        if loaded is not None and not isinstance(loaded, dict):
            raise ValueError(f"JSON config must be an object: {config_path}")
        existing = loaded or {}
        backup = config_path.with_name(f"{config_path.name}.bak.{int(time.time())}")
        shutil.copy2(config_path, backup)
    mcp = existing.setdefault("mcp", {})
    if not isinstance(mcp, dict):
        mcp = existing["mcp"] = {}
    servers = mcp.setdefault("servers", {})
    if not isinstance(servers, dict):
        servers = mcp["servers"] = {}
    spec = server_spec(runtime_dir, data_dir, "openclaw")
    servers["lamf"] = {**spec, "transport": "stdio", "enabled": True}
    _atomic_write(config_path, json.dumps(existing, indent=2) + "\n")
    return {"config": str(config_path), "backup": str(backup) if backup else None,
            "server": "lamf", "changed": True}


def remove_openclaw(config_path: Path) -> dict:
    """Remove the LAMF-owned ``mcp.servers.lamf`` entry from openclaw.json."""
    config_path = Path(config_path).expanduser()
    if not config_path.exists():
        return {"config": str(config_path), "removed": False, "changed": False}
    loaded = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"JSON config must be an object: {config_path}")
    servers = (loaded.get("mcp") or {}).get("servers")
    if not isinstance(servers, dict) or "lamf" not in servers:
        return {"config": str(config_path), "removed": False, "changed": False}
    backup = config_path.with_name(f"{config_path.name}.bak.{int(time.time())}")
    shutil.copy2(config_path, backup)
    del servers["lamf"]
    if not servers:
        del loaded["mcp"]["servers"]
        if not loaded["mcp"]:
            del loaded["mcp"]
    _atomic_write(config_path, json.dumps(loaded, indent=2) + "\n")
    return {"config": str(config_path), "backup": str(backup),
            "removed": True, "changed": True}


def remove_hermes(config_path: Path) -> dict:
    """Remove the LAMF server entry from Hermes' YAML config."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise RuntimeError("PyYAML is required to update Hermes config") from exc
    config_path = Path(config_path).expanduser()
    if not config_path.exists():
        return {"config": str(config_path), "removed": False, "changed": False}
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Hermes config must be a YAML mapping: {config_path}")
    servers = loaded.get("mcp_servers")
    if not isinstance(servers, dict) or "lamf" not in servers:
        return {"config": str(config_path), "removed": False, "changed": False}
    backup = config_path.with_name(f"{config_path.name}.bak.{int(time.time())}")
    shutil.copy2(config_path, backup)
    del servers["lamf"]
    if not servers:
        del loaded["mcp_servers"]
    _atomic_write(config_path, yaml.safe_dump(loaded, sort_keys=False))
    return {"config": str(config_path), "backup": str(backup),
            "removed": True, "changed": True}


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


# Default per-harness config locations. ``kimi`` is resolved by
# ``kimi_config_path`` (modern path, legacy detection); ``generic`` has no
# default and always requires an explicit target.
DEFAULT_CONFIG_PATHS = {
    "codex": "~/.codex/config.toml",
    "claude": "~/.claude/mcp.json",
    "gemini": "~/.gemini/settings.json",
    "grok": "~/.grok/config.toml",
    "openclaw": "~/.openclaw/openclaw.json",
    "hermes": "~/.hermes/config.yaml",
}


def default_config_path(harness_id: str) -> Path | None:
    """Return the default config path for *harness_id*, or None for generic."""
    if harness_id == "kimi":
        return kimi_config_path()
    raw = DEFAULT_CONFIG_PATHS.get(harness_id)
    return Path(raw).expanduser() if raw is not None else None


# Apply/remove dispatch. Every entry backs up the target before changing it,
# preserves unrelated settings, and is idempotent. ``generic`` shares the JSON
# mcpServers merge with the named JSON harnesses.
def apply(harness_id: str, runtime_dir: Path, data_dir: Path,
          config_path: Path | None = None) -> dict:
    """Merge the LAMF registration into *harness_id*'s host config."""
    if harness_id not in HARNESSES:
        raise ValueError(f"unknown harness {harness_id!r}")
    target = Path(config_path).expanduser() if config_path else default_config_path(harness_id)
    if target is None:
        raise ValueError(f"harness {harness_id!r} requires an explicit config path")
    if harness_id in ("codex", "grok"):
        return _apply_toml_block(target, runtime_dir, data_dir, harness_id)
    if harness_id == "hermes":
        return apply_hermes(target, runtime_dir, data_dir)
    if harness_id == "openclaw":
        return apply_openclaw(target, runtime_dir, data_dir)
    # claude, kimi, gemini, generic: JSON mcpServers merge
    return apply_generic_json(target, runtime_dir, data_dir,
                              owned_key="lamf-memory", harness_id=harness_id)


def remove(harness_id: str, config_path: Path | None = None) -> dict:
    """Remove the LAMF-owned entry from *harness_id*'s host config."""
    if harness_id not in HARNESSES:
        raise ValueError(f"unknown harness {harness_id!r}")
    target = Path(config_path).expanduser() if config_path else default_config_path(harness_id)
    if target is None:
        raise ValueError(f"harness {harness_id!r} requires an explicit config path")
    if harness_id in ("codex", "grok"):
        return _remove_toml_block(target)
    if harness_id == "hermes":
        return remove_hermes(target)
    if harness_id == "openclaw":
        return remove_openclaw(target)
    return remove_generic_json(target, owned_key="lamf-memory")
