"""Installer adapters for agent harness registration.

Each adapter implements two operations:

* ``connect(lamf_exe, data_dir, config_dir)`` — idempotently register LAMF
  with the target harness, probe the MCP handshake, and commit a receipt.
* ``disconnect(lamf_exe, data_dir, config_dir)`` — remove only the LAMF-owned
  server entry, preserving unrelated settings.

Supported harnesses: codex, claude, kimi, gemini, grok, hermes, openclaw,
and a generic MCP client JSON target.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

# The runtime package is a sibling of the installer directory in the source
# tree; in installed layouts it is expected to be importable without this shim.
_RUNTIME_ROOT = Path(__file__).resolve().parents[2] / "runtime"
if str(_RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_ROOT))

from lamf import harness as _harness

from . import harness_tx as _tx
from .harness_tx import HarnessError


_OWNED_KEY = "lamf-memory"
_BEGIN, _END = "# BEGIN LAMF MANAGED", "# END LAMF MANAGED"

_CONFIG_FILENAMES: dict[str, str] = {
    "codex": "config.toml",
    "claude": "mcp.json",
    # Kimi Code 0.23.x default; legacy ~/.kimi/mcp.json is detected, not mutated.
    "kimi": "mcp.json",
    "gemini": "settings.json",
    "grok": "config.toml",
    "hermes": "config.yaml",
    "openclaw": "mcp.json",
    "generic": "mcp.json",
}


def _config_path(config_dir: str | Path, harness_id: str) -> Path:
    path = Path(config_dir).expanduser() / _CONFIG_FILENAMES[harness_id]
    if harness_id == "kimi":
        # If the operator explicitly passed a config dir, use it. Otherwise
        # detect legacy ~/.kimi only when it exists and modern ~/.kimi-code
        # does not.
        modern = path
        legacy = Path("~/.kimi").expanduser() / "mcp.json"
        if legacy.exists() and not modern.exists():
            return legacy
    return path


def _runtime_dir(lamf_exe: str | Path) -> Path:
    """Derive the runtime directory from the launcher path.

    In the installed layout the launcher lives next to an ``app/`` directory
    that contains the LAMF runtime package. During development the launcher
    may sit directly inside the runtime tree.
    """
    exe_dir = Path(lamf_exe).resolve().parent
    app_dir = exe_dir / "app"
    return app_dir if app_dir.is_dir() else exe_dir


def _managed_block(harness_id: str, runtime_dir: Path, data_dir: Path) -> str:
    """Wrap a TOML harness render in managed-block markers."""
    snippet = _harness.render(harness_id, runtime_dir, data_dir).rstrip()
    return f"{_BEGIN}\n{snippet}\n{_END}\n"


def _apply_managed_toml(config_path: Path, harness_id: str, runtime_dir: Path,
                        data_dir: Path) -> dict:
    """Idempotently insert or replace a LAMF managed block in a TOML file."""
    config_path = Path(config_path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    old = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    if old.count(_BEGIN) != old.count(_END) or old.count(_BEGIN) > 1:
        raise HarnessError(f"malformed LAMF managed block in {config_path}")
    block = _managed_block(harness_id, runtime_dir, data_dir)
    if _BEGIN in old:
        prefix, rest = old.split(_BEGIN, 1)
        _, suffix = rest.split(_END, 1)
        new = prefix.rstrip("\n") + "\n\n" + block + suffix.lstrip("\n")
    else:
        sep = "\n\n" if old.strip() else ""
        new = old.rstrip("\n") + sep + block
    _tx.atomic_write(config_path, new)
    return {"config": str(config_path), "server": "lamf", "changed": True}


def _remove_managed_toml(config_path: Path) -> dict:
    """Remove a LAMF managed block from a TOML file."""
    config_path = Path(config_path).expanduser()
    if not config_path.exists():
        return {"config": str(config_path), "removed": False, "changed": False}
    old = config_path.read_text(encoding="utf-8")
    if _BEGIN not in old:
        return {"config": str(config_path), "removed": False, "changed": False}
    if old.count(_BEGIN) != old.count(_END) or old.count(_BEGIN) > 1:
        raise HarnessError(f"malformed LAMF managed block in {config_path}")
    prefix, rest = old.split(_BEGIN, 1)
    _, suffix = rest.split(_END, 1)
    new = prefix.rstrip("\n") + "\n" + suffix.lstrip("\n")
    new = new.strip("\n") + "\n" if new.strip() else ""
    _tx.atomic_write(config_path, new)
    return {"config": str(config_path), "removed": True, "changed": True}


def _apply_openclaw(config_path: Path, runtime_dir: Path, data_dir: Path) -> dict:
    """Idempotently maintain the LAMF server entry in OpenClaw's nested JSON."""
    config_path = Path(config_path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _tx.parse_config(config_path, "json")
    mcp = existing.setdefault("mcp", {})
    servers = mcp.setdefault("servers", {})
    if not isinstance(servers, dict):
        raise HarnessError("OpenClaw mcp.servers must be a mapping")
    spec = _harness.server_spec(runtime_dir, data_dir, "openclaw")
    servers[_OWNED_KEY] = {**spec, "transport": "stdio", "enabled": True}
    _tx.atomic_write(config_path, json.dumps(existing, indent=2) + "\n")
    return {"config": str(config_path), "server": _OWNED_KEY, "changed": True}


def _remove_openclaw(config_path: Path) -> dict:
    """Remove the LAMF server entry from OpenClaw's nested JSON."""
    config_path = Path(config_path).expanduser()
    if not config_path.exists():
        return {"config": str(config_path), "removed": False, "changed": False}
    existing = _tx.parse_config(config_path, "json")
    servers = (existing.get("mcp") or {}).get("servers")
    if not isinstance(servers, dict) or _OWNED_KEY not in servers:
        return {"config": str(config_path), "removed": False, "changed": False}
    del servers[_OWNED_KEY]
    if not servers:
        (existing.get("mcp") or {}).pop("servers", None)
    if existing.get("mcp") == {}:
        del existing["mcp"]
    _tx.atomic_write(config_path, json.dumps(existing, indent=2) + "\n")
    return {"config": str(config_path), "removed": True, "changed": True}


def _expected_spec(harness_id: str, runtime_dir: Path, data_dir: Path) -> dict:
    """Return the registration spec the harness config should contain."""
    return _harness.server_spec(runtime_dir, data_dir, harness_id)


def _config_contains(config_path: Path, harness_id: str, runtime_dir: Path,
                     data_dir: Path) -> bool:
    """Check whether *config_path* already contains the expected LAMF entry."""
    config_path = Path(config_path).expanduser()
    if not config_path.exists():
        return False
    fmt = _harness.HARNESSES[harness_id].format
    existing = _tx.parse_config(config_path, fmt)
    expected = _expected_spec(harness_id, runtime_dir, data_dir)
    if harness_id == "openclaw":
        servers = (existing.get("mcp") or {}).get("servers") or {}
        entry = servers.get(_OWNED_KEY)
    elif harness_id in ("codex", "grok"):
        # TOML managed block: re-render and compare text hashes.
        rendered = _harness.render(harness_id, runtime_dir, data_dir)
        return rendered.strip() in config_path.read_text(encoding="utf-8")
    elif harness_id == "hermes":
        servers = existing.get("mcp_servers") or {}
        entry = servers.get("lamf")
    else:
        servers = existing.get("mcpServers") or {}
        entry = servers.get(_OWNED_KEY)
    if not isinstance(entry, dict):
        return False
    return (
        entry.get("command") == expected.get("command")
        and entry.get("args") == expected.get("args")
        and entry.get("env", {}).get("LAMF_DATA_DIR")
        == expected.get("env", {}).get("LAMF_DATA_DIR")
    )


def _run_transaction(harness_id: str, lamf_exe: str | Path,
                     data_dir: str | Path, config_dir: str | Path,
                     mutate, *, skip_mcp_probe: bool = False) -> dict:
    """Backup, mutate, probe, commit receipt; rollback on failure."""
    config_path = _config_path(config_dir, harness_id)
    runtime_dir = _runtime_dir(lamf_exe)
    pre_hash = _tx.compute_hash(config_path)
    # Reading the config also validates its syntax before we mutate it.
    fmt = _harness.HARNESSES[harness_id].format
    if fmt == "toml":
        _tx.parse_config(config_path, "toml")
    elif fmt == "yaml":
        _tx.parse_config(config_path, "yaml")
    elif fmt == "json":
        _tx.parse_config(config_path, "json")
    backup = _tx.backup(config_path)
    try:
        result = mutate(config_path, runtime_dir, Path(data_dir).expanduser())
        post_hash = _tx.compute_hash(config_path)
        if not skip_mcp_probe:
            _tx.probe_mcp(lamf_exe, data_dir, harness_id)
        receipt = {
            "harness_id": harness_id,
            "status": "connected",
            "pre_hash": pre_hash,
            "post_hash": post_hash,
            "config": str(config_path),
        }
        _tx.commit_receipt(data_dir, harness_id, receipt)
        return {
            "success": True,
            "harness_id": harness_id,
            "config": str(config_path),
            "backup": str(backup) if backup else None,
            "changed": result.get("changed", True),
        }
    except Exception:
        _tx.rollback(backup, config_path)
        raise


def verify(harness_id: str, lamf_exe: str | Path, data_dir: str | Path,
           config_dir: str | Path) -> dict:
    """Verify an existing harness config matches the current LAMF spec and works.

    Does not write or mutate the config. Returns a dict with ``ok`` and the
    result of the MCP probe.
    """
    config_path = _config_path(config_dir, harness_id)
    runtime_dir = _runtime_dir(lamf_exe)
    fmt = _harness.HARNESSES[harness_id].format
    _tx.parse_config(config_path, fmt)
    if not _config_contains(config_path, harness_id, runtime_dir,
                            Path(data_dir).expanduser()):
        raise HarnessError(
            f"{harness_id}: config at {config_path} does not contain the expected LAMF entry")
    probe = _tx.probe_mcp(lamf_exe, data_dir, harness_id)
    return {
        "success": True,
        "harness_id": harness_id,
        "config": str(config_path),
        "verified": True,
        "probe": probe,
    }


# ---------------------------------------------------------------------------
# Per-harness public API
# ---------------------------------------------------------------------------

def connect_codex(lamf_exe: str | Path, data_dir: str | Path,
                  config_dir: str | Path) -> dict:
    return _run_transaction("codex", lamf_exe, data_dir, config_dir,
                            _apply_managed_toml)


def disconnect_codex(lamf_exe: str | Path, data_dir: str | Path,
                     config_dir: str | Path) -> dict:
    config_path = _config_path(config_dir, "codex")
    backup = _tx.backup(config_path)
    try:
        result = _remove_managed_toml(config_path)
        _tx.commit_receipt(data_dir, "codex",
                           {"harness_id": "codex", "status": "disconnected"})
        return {"success": True, "harness_id": "codex", **result}
    except Exception:
        _tx.rollback(backup, config_path)
        raise


def connect_claude(lamf_exe: str | Path, data_dir: str | Path,
                   config_dir: str | Path) -> dict:
    def _mutate(path, runtime_dir, ddir):
        return _harness.apply_generic_json(path, runtime_dir, ddir,
                                           owned_key=_OWNED_KEY, harness_id="claude")
    return _run_transaction("claude", lamf_exe, data_dir, config_dir, _mutate)


def disconnect_claude(lamf_exe: str | Path, data_dir: str | Path,
                      config_dir: str | Path) -> dict:
    config_path = _config_path(config_dir, "claude")
    backup = _tx.backup(config_path)
    try:
        result = _harness.remove_generic_json(config_path, _OWNED_KEY)
        _tx.commit_receipt(data_dir, "claude",
                           {"harness_id": "claude", "status": "disconnected"})
        return {"success": True, "harness_id": "claude", **result}
    except Exception:
        _tx.rollback(backup, config_path)
        raise


def connect_kimi(lamf_exe: str | Path, data_dir: str | Path,
                 config_dir: str | Path) -> dict:
    def _mutate(path, runtime_dir, ddir):
        return _harness.apply_generic_json(path, runtime_dir, ddir,
                                           owned_key=_OWNED_KEY, harness_id="kimi")
    return _run_transaction("kimi", lamf_exe, data_dir, config_dir, _mutate)


def disconnect_kimi(lamf_exe: str | Path, data_dir: str | Path,
                    config_dir: str | Path) -> dict:
    config_path = _config_path(config_dir, "kimi")
    backup = _tx.backup(config_path)
    try:
        result = _harness.remove_generic_json(config_path, _OWNED_KEY)
        _tx.commit_receipt(data_dir, "kimi",
                           {"harness_id": "kimi", "status": "disconnected"})
        return {"success": True, "harness_id": "kimi", **result}
    except Exception:
        _tx.rollback(backup, config_path)
        raise


def connect_gemini(lamf_exe: str | Path, data_dir: str | Path,
                   config_dir: str | Path) -> dict:
    def _mutate(path, runtime_dir, ddir):
        return _harness.apply_generic_json(path, runtime_dir, ddir,
                                           owned_key=_OWNED_KEY, harness_id="gemini")
    return _run_transaction("gemini", lamf_exe, data_dir, config_dir, _mutate)


def disconnect_gemini(lamf_exe: str | Path, data_dir: str | Path,
                      config_dir: str | Path) -> dict:
    config_path = _config_path(config_dir, "gemini")
    backup = _tx.backup(config_path)
    try:
        result = _harness.remove_generic_json(config_path, _OWNED_KEY)
        _tx.commit_receipt(data_dir, "gemini",
                           {"harness_id": "gemini", "status": "disconnected"})
        return {"success": True, "harness_id": "gemini", **result}
    except Exception:
        _tx.rollback(backup, config_path)
        raise


def connect_grok(lamf_exe: str | Path, data_dir: str | Path,
                 config_dir: str | Path) -> dict:
    def _mutate(path, runtime_dir, ddir):
        return _harness.apply_grok(path, runtime_dir, ddir)
    return _run_transaction("grok", lamf_exe, data_dir, config_dir, _mutate)


def disconnect_grok(lamf_exe: str | Path, data_dir: str | Path,
                    config_dir: str | Path) -> dict:
    config_path = _config_path(config_dir, "grok")
    backup = _tx.backup(config_path)
    try:
        result = _harness.remove_grok(config_path)
        _tx.commit_receipt(data_dir, "grok",
                           {"harness_id": "grok", "status": "disconnected"})
        return {"success": True, "harness_id": "grok", **result}
    except Exception:
        _tx.rollback(backup, config_path)
        raise


def connect_hermes(lamf_exe: str | Path, data_dir: str | Path,
                   config_dir: str | Path) -> dict:
    def _mutate(path, runtime_dir, ddir):
        return _harness.apply_hermes(path, runtime_dir, ddir)
    return _run_transaction("hermes", lamf_exe, data_dir, config_dir, _mutate)


def disconnect_hermes(lamf_exe: str | Path, data_dir: str | Path,
                      config_dir: str | Path) -> dict:
    config_path = _config_path(config_dir, "hermes")
    backup = _tx.backup(config_path)
    try:
        result = _harness.remove_hermes(config_path)
        _tx.commit_receipt(data_dir, "hermes",
                           {"harness_id": "hermes", "status": "disconnected"})
        return {"success": True, "harness_id": "hermes", **result}
    except Exception:
        _tx.rollback(backup, config_path)
        raise


def connect_openclaw(lamf_exe: str | Path, data_dir: str | Path,
                     config_dir: str | Path) -> dict:
    return _run_transaction("openclaw", lamf_exe, data_dir, config_dir,
                            _apply_openclaw)


def disconnect_openclaw(lamf_exe: str | Path, data_dir: str | Path,
                        config_dir: str | Path) -> dict:
    config_path = _config_path(config_dir, "openclaw")
    backup = _tx.backup(config_path)
    try:
        result = _remove_openclaw(config_path)
        _tx.commit_receipt(data_dir, "openclaw",
                           {"harness_id": "openclaw", "status": "disconnected"})
        return {"success": True, "harness_id": "openclaw", **result}
    except Exception:
        _tx.rollback(backup, config_path)
        raise


def connect_generic(lamf_exe: str | Path, data_dir: str | Path,
                    config_dir: str | Path) -> dict:
    def _mutate(path, runtime_dir, ddir):
        return _harness.apply_generic_json(path, runtime_dir, ddir,
                                           owned_key=_OWNED_KEY, harness_id="generic")
    return _run_transaction("generic", lamf_exe, data_dir, config_dir, _mutate)


def disconnect_generic(lamf_exe: str | Path, data_dir: str | Path,
                       config_dir: str | Path) -> dict:
    config_path = _config_path(config_dir, "generic")
    backup = _tx.backup(config_path)
    try:
        result = _harness.remove_generic_json(config_path, _OWNED_KEY)
        _tx.commit_receipt(data_dir, "generic",
                           {"harness_id": "generic", "status": "disconnected"})
        return {"success": True, "harness_id": "generic", **result}
    except Exception:
        _tx.rollback(backup, config_path)
        raise


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _verify_for(harness_id: str):
    def _verify(lamf_exe, data_dir, config_dir):
        return verify(harness_id, lamf_exe, data_dir, config_dir)
    return _verify


ADAPTERS: dict[str, SimpleNamespace] = {
    "codex": SimpleNamespace(connect=connect_codex, disconnect=disconnect_codex, verify=_verify_for("codex")),
    "claude": SimpleNamespace(connect=connect_claude, disconnect=disconnect_claude, verify=_verify_for("claude")),
    "kimi": SimpleNamespace(connect=connect_kimi, disconnect=disconnect_kimi, verify=_verify_for("kimi")),
    "gemini": SimpleNamespace(connect=connect_gemini, disconnect=disconnect_gemini, verify=_verify_for("gemini")),
    "grok": SimpleNamespace(connect=connect_grok, disconnect=disconnect_grok, verify=_verify_for("grok")),
    "hermes": SimpleNamespace(connect=connect_hermes, disconnect=disconnect_hermes, verify=_verify_for("hermes")),
    "openclaw": SimpleNamespace(connect=connect_openclaw, disconnect=disconnect_openclaw, verify=_verify_for("openclaw")),
    "generic": SimpleNamespace(connect=connect_generic, disconnect=disconnect_generic, verify=_verify_for("generic")),
}


def connect(harness_id: str, lamf_exe: str | Path, data_dir: str | Path,
            config_dir: str | Path) -> dict:
    """Connect *harness_id* using its registered adapter."""
    if harness_id not in ADAPTERS:
        raise HarnessError(f"unknown harness {harness_id!r}")
    return ADAPTERS[harness_id].connect(lamf_exe, data_dir, config_dir)


def disconnect(harness_id: str, lamf_exe: str | Path, data_dir: str | Path,
               config_dir: str | Path) -> dict:
    """Disconnect *harness_id* using its registered adapter."""
    if harness_id not in ADAPTERS:
        raise HarnessError(f"unknown harness {harness_id!r}")
    return ADAPTERS[harness_id].disconnect(lamf_exe, data_dir, config_dir)


def repair(harness_id: str, lamf_exe: str | Path, data_dir: str | Path,
           config_dir: str | Path) -> dict:
    """Repair *harness_id* using its registered adapter (idempotent connect)."""
    return connect(harness_id, lamf_exe, data_dir, config_dir)
