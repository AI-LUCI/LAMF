"""Transactional harness configuration driver (W-06).

Implements the per-harness transaction contract from
``docs/WINDOWS_INSTALLER_ARCHITECTURE.md`` §6:

* detect executable and candidate user-level config targets
* parse and validate existing configuration
* hash the inspected input and reject stale writes
* create a timestamped backup
* write a sibling temporary file, flush it, and atomically replace the target
* probe the configured MCP command
* commit a redacted receipt, or restore the backup on failure

Requirement IDs referenced: R-WIN-0601 through R-WIN-0608.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


class HarnessError(RuntimeError):
    """A harness transaction failed and, when possible, the backup was restored."""


HARNESS_CONFIG_CANDIDATES: dict[str, list[str]] = {
    "codex": ["~/.codex/config.toml"],
    "claude": ["~/.claude/mcp.json", "~/.config/claude/mcp.json"],
    # Kimi Code 0.23.x uses ~/.kimi-code/mcp.json. The legacy ~/.kimi/mcp.json
    # path is detected but not mutated unless the operator still uses it.
    "kimi": ["~/.kimi-code/mcp.json", "~/.kimi/mcp.json"],
    # Gemini CLI documents its user config as ~/.gemini/settings.json with a
    # top-level mcpServers object.
    "gemini": ["~/.gemini/settings.json"],
    "grok": ["~/.grok/config.toml"],
    "hermes": ["~/.hermes/config.yaml"],
    "openclaw": ["~/.openclaw/mcp.json"],
    "generic": [],
}


def detect_executable(name: str) -> Path | None:
    """Locate *name* on PATH, tolerating Windows ``.exe`` suffixes.

    R-WIN-0601: detect a harness executable before offering to configure it.
    """
    found = shutil.which(name)
    if found is None and os.name == "nt" and not name.lower().endswith(".exe"):
        found = shutil.which(f"{name}.exe")
    return Path(found) if found else None


def candidate_paths(harness_id: str) -> list[Path]:
    """Return the conventional user-level config paths for *harness_id*."""
    return [Path(p).expanduser() for p in HARNESS_CONFIG_CANDIDATES.get(harness_id, [])]


def parse_config(path: Path, format: str) -> dict:
    """Parse *path* as ``json``, ``toml``, or ``yaml``. Missing files return ``{}``.

    R-WIN-0602: parse and validate the existing harness configuration before
    mutating it. Malformed files raise ``HarnessError`` so the caller can
    surface a "Needs attention" state rather than overwriting user data.
    """
    path = Path(path)
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    try:
        if format == "json":
            loaded = json.loads(raw)
        elif format == "toml":
            try:
                import tomllib
            except ImportError as exc:  # pragma: no cover - CPython 3.11+
                raise RuntimeError("tomllib is required to parse TOML harness configs") from exc
            loaded = tomllib.loads(raw)
        elif format == "yaml":
            try:
                import yaml
            except ImportError as exc:  # pragma: no cover - declared dependency
                raise RuntimeError("PyYAML is required to parse YAML harness configs") from exc
            loaded = yaml.safe_load(raw)
        else:
            raise HarnessError(f"unsupported config format {format!r}")
    except Exception as exc:
        raise HarnessError(f"malformed {format} config at {path}: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise HarnessError(f"{format} config root must be an object/mapping: {path}")
    return loaded


def compute_hash(path: Path) -> str | None:
    """Return the SHA-256 hex digest of *path*, or ``None`` if it does not exist."""
    path = Path(path)
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_hash(path: Path, expected_hash: str | None) -> None:
    """Raise ``HarnessError`` if *path* no longer matches *expected_hash*.

    R-WIN-0603: reject stale writes caused by a concurrent edit.
    """
    if expected_hash is None:
        return
    current = compute_hash(path)
    if current != expected_hash:
        raise HarnessError(
            f"concurrent edit detected: expected {expected_hash[:16]}..., got {current[:16] if current else 'missing'}..."
        )


def backup(path: Path) -> Path | None:
    """Create a timestamped backup of *path* in its parent directory.

    R-WIN-0604: every mutation is preceded by a recoverable backup.
    Returns ``None`` when *path* does not exist (a create-then-rollback will
    simply delete the newly created file).
    """
    path = Path(path)
    if not path.exists():
        return None
    stamp = int(time.time())
    dest = path.with_name(f"{path.name}.bak.{stamp}")
    # Avoid collisions on sub-second tests.
    while dest.exists():
        stamp += 1
        dest = path.with_name(f"{path.name}.bak.{stamp}")
    shutil.copy2(path, dest)
    return dest


def atomic_write(path: Path, content: str) -> None:
    """Write *content* to a sibling temp file, flush, and atomically replace *path*.

    R-WIN-0605: harness config writes must be atomic so a crash leaves either
    the old file or the new file, never a partially written one.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    # Ensure the contents reach the storage device before the rename.
    try:
        fd = os.open(str(tmp), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except Exception:
        pass
    os.replace(tmp, path)


def _mcp_argv(lamf_exe: Path, harness_id: str) -> list[str]:
    """Build the argv for the MCP probe.

    A ``.py`` script is run through the current Python interpreter so tests
    can substitute a deterministic fake without building a binary.
    """
    lamf_exe = Path(lamf_exe)
    if lamf_exe.suffix.lower() == ".py":
        return [sys.executable, str(lamf_exe), "mcp", "--harness", harness_id]
    return [str(lamf_exe), "mcp", "--harness", harness_id]


def probe_mcp(lamf_exe: str | Path, data_dir: str | Path, harness_id: str) -> dict:
    """Start ``lamf_exe mcp --harness <id>`` and verify initialize/tools/list/memory_status.

    R-WIN-0606: after writing a harness config, perform an end-to-end MCP
    handshake against the chosen authoritative data directory.

    Raises ``HarnessError`` if the handshake fails or the expected tools are
    absent. The subprocess is always terminated before returning.
    """
    env = os.environ.copy()
    env["LAMF_DATA_DIR"] = str(data_dir)
    env["LAMF_HARNESS"] = harness_id
    argv = _mcp_argv(Path(lamf_exe), harness_id)
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        bufsize=1,
    )
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                    "clientInfo": {"name": "lamf-installer"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "memory_status", "arguments": {}}},
    ]
    input_text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in requests)
    try:
        stdout, stderr = proc.communicate(input=input_text, timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        raise HarnessError(f"MCP probe timed out for {harness_id}: {stderr.strip()}")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    if proc.returncode not in (0, None):
        raise HarnessError(
            f"MCP probe exited {proc.returncode} for {harness_id}: {stderr.strip()}")

    responses: dict[int, dict] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(msg, dict) and "id" in msg and msg["id"] is not None:
            responses[int(msg["id"])] = msg

    errors = []
    for req_id in (1, 2, 3):
        resp = responses.get(req_id)
        if resp is None:
            errors.append(f"missing response for request {req_id}")
            continue
        if "error" in resp:
            err = resp["error"]
            errors.append(f"request {req_id} error: {err.get('message', err)}")
    if errors:
        raise HarnessError(f"MCP probe failed for {harness_id}: {'; '.join(errors)}")

    init = responses[1].get("result", {})
    tools = responses[2].get("result", {}).get("tools", [])
    tool_names = {t.get("name") for t in tools if isinstance(t, dict)}
    if "memory_status" not in tool_names:
        raise HarnessError(f"MCP probe for {harness_id}: memory_status tool missing")

    return {
        "harness_id": harness_id,
        "protocol_version": init.get("protocolVersion"),
        "server_name": init.get("serverInfo", {}).get("name"),
        "tools": sorted(tool_names),
        "memory_status_ok": "memory_status" in tool_names,
    }


def _redact_receipt(result: dict) -> dict:
    """Return a receipt that records outcome without tokens, keys, or paths."""
    safe: dict = {
        "harness_id": result.get("harness_id"),
        "status": result.get("status", "ok"),
        "timestamp": int(time.time()),
    }
    for key in ("changed", "removed", "pre_hash", "post_hash", "server"):
        if key in result:
            safe[key] = result[key]
    if "error" in result:
        safe["error"] = str(result["error"])[:256]
    return safe


def commit_receipt(data_dir: str | Path, harness_id: str, result: dict) -> Path:
    """Write a redacted transaction receipt under ``<data_dir>/adapters/``.

    R-WIN-0607: every harness mutation is recorded, but receipts must never
    contain operator tokens, instance keys, or harness credentials.
    """
    adapters_dir = Path(data_dir).expanduser() / "adapters"
    adapters_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    path = adapters_dir / f"{harness_id}-{stamp}.receipt.json"
    while path.exists():
        stamp += 1
        path = adapters_dir / f"{harness_id}-{stamp}.receipt.json"
    path.write_text(json.dumps(_redact_receipt(result), indent=2), encoding="utf-8")
    return path


def rollback(backup_path: Path | None, path: Path) -> dict:
    """Restore *backup_path* to *path*, or remove *path* if no backup exists.

    R-WIN-0608: failures restore the prior configuration state.
    """
    path = Path(path)
    if backup_path is not None and Path(backup_path).exists():
        shutil.copy2(backup_path, path)
        return {"restored": True, "from": str(backup_path), "path": str(path)}
    if path.exists():
        path.unlink()
    return {"restored": False, "path": str(path)}
