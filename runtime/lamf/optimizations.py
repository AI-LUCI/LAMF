"""Fail-open, independently switchable agent optimization modules.

Package modules are immutable inputs. Instance-local state lives in
``<data_dir>/optimizations.json``. Invalid modules are quarantined at read
time and never prevent LAMF from starting or serving memory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_VERSION = 1
MAX_FRAGMENT_CHARS = 1400
ENV_GLOBAL = "LAMF_OPTIMIZATIONS"


def module_root() -> Path:
    return Path(__file__).resolve().parents[2] / "05_INTEGRATIONS" / "optimizations" / "modules"


def config_path(data_dir: Path) -> Path:
    return Path(data_dir) / "optimizations.json"


def default_config() -> dict:
    return {"version": CONFIG_VERSION, "enabled": True, "modules": {}}


def _env_bool(name: str):
    value = os.environ.get(name)
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def load_config(data_dir: Path) -> tuple[dict, str | None]:
    path = config_path(data_dir)
    if not path.exists():
        return default_config(), None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("version") != CONFIG_VERSION:
            raise ValueError("unsupported configuration version")
        if not isinstance(value.get("enabled"), bool):
            raise ValueError("enabled must be boolean")
        if not isinstance(value.get("modules", {}), dict):
            raise ValueError("modules must be an object")
        return value, None
    except Exception as exc:  # fail open to original, unoptimized LAMF
        return {"version": CONFIG_VERSION, "enabled": False, "modules": {}}, str(exc)


def save_config(data_dir: Path, config: dict) -> None:
    path = config_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def initialize(data_dir: Path) -> None:
    if not config_path(data_dir).exists():
        save_config(data_dir, default_config())


def _validate_module(directory: Path) -> tuple[dict | None, str | None]:
    try:
        manifest = json.loads((directory / "module.json").read_text(encoding="utf-8"))
        required = {"id", "version", "default_enabled", "instruction_file"}
        missing = required - set(manifest)
        if missing:
            raise ValueError(f"missing manifest fields: {', '.join(sorted(missing))}")
        if manifest["id"] != directory.name:
            raise ValueError("manifest id must match directory name")
        if not isinstance(manifest["default_enabled"], bool):
            raise ValueError("default_enabled must be boolean")
        instruction_path = directory / str(manifest["instruction_file"])
        instruction = instruction_path.read_text(encoding="utf-8").strip()
        if not instruction:
            raise ValueError("instruction fragment is empty")
        if len(instruction) > MAX_FRAGMENT_CHARS:
            raise ValueError(f"instruction fragment exceeds {MAX_FRAGMENT_CHARS} characters")
        manifest["instruction"] = instruction
        return manifest, None
    except Exception as exc:
        return None, str(exc)


def discover(root: Path | None = None) -> list[dict]:
    root = Path(root or module_root())
    if not root.exists():
        return []
    modules = []
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        if not (directory / "module.json").exists():
            continue
        manifest, error = _validate_module(directory)
        modules.append({"id": directory.name, "manifest": manifest, "error": error})
    return modules


def status(data_dir: Path, root: Path | None = None) -> dict:
    config, config_error = load_config(data_dir)
    env_global = _env_bool(ENV_GLOBAL)
    global_enabled = config["enabled"] if env_global is None else env_global
    results = []
    for found in discover(root):
        manifest = found["manifest"]
        module_id = found["id"]
        configured = config.get("modules", {}).get(module_id)
        default = manifest["default_enabled"] if manifest else False
        enabled = default if configured is None else configured
        env_module = _env_bool("LAMF_OPTIMIZATION_" + module_id.upper().replace("-", "_"))
        if env_module is not None:
            enabled = env_module
        results.append({
            "id": module_id,
            "enabled": bool(global_enabled and enabled and manifest and not found["error"]),
            "configured": configured,
            "valid": found["error"] is None,
            "error": found["error"],
            "version": manifest.get("version") if manifest else None,
        })
    return {
        "enabled": bool(global_enabled),
        "configured_enabled": config["enabled"],
        "environment_override": env_global,
        "config_error": config_error,
        "config_path": str(config_path(data_dir)),
        "modules": results,
    }


def set_global(data_dir: Path, enabled: bool) -> dict:
    config, _ = load_config(data_dir)
    config["enabled"] = bool(enabled)
    save_config(data_dir, config)
    return status(data_dir)


def set_module(data_dir: Path, module_id: str, enabled: bool) -> dict:
    known = {item["id"] for item in discover()}
    if module_id not in known:
        raise ValueError(f"unknown optimization {module_id!r}; expected: {', '.join(sorted(known))}")
    config, _ = load_config(data_dir)
    config.setdefault("modules", {})[module_id] = bool(enabled)
    save_config(data_dir, config)
    return status(data_dir)


def compiled_instructions(data_dir: Path) -> str:
    current = status(data_dir)
    if not current["enabled"] or current["config_error"]:
        return ""
    enabled = {item["id"] for item in current["modules"] if item["enabled"]}
    fragments = []
    for found in discover():
        if found["id"] in enabled and found["manifest"]:
            fragments.append(found["manifest"]["instruction"])
    if not fragments:
        return ""
    return " Agent optimizations (independently switchable): " + " ".join(fragments)
