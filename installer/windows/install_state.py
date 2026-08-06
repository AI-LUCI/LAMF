"""Install-state persistence and validation for the LAMF Windows installer.

The install state is a small JSON file written to both the application
directory (``install-state.json``) and the data directory so that the
uninstaller can locate every path without relying on the registry or
environment variables. It intentionally stores only non-secret metadata:
paths, version, profile, and selected modules/harnesses.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REQUIRED_SCHEMA_VERSION = 1
DEFAULT_PROFILE = "controlled"


class InstallStateError(ValueError):
    """Validation or I/O error for install-state.json."""


@dataclass
class InstallState:
    """Canonical representation of an installed LAMF instance.

    Fields:
        schema_version: format version, must match
            :data:`REQUIRED_SCHEMA_VERSION`.
        version: LAMF release version string (e.g. ``"1.0.0"``).
        app_dir: absolute path to the application directory.
        data_dir: absolute path to the private memory/data directory.
        profile: security profile name selected during setup.
        modules: enabled optimization module identifiers.
        harnesses: configured harness identifiers.
        optimizations_enabled: global optimization enablement flag.
    """

    schema_version: int
    version: str
    app_dir: Path
    data_dir: Path
    profile: str
    modules: list[str] = field(default_factory=list)
    harnesses: list[str] = field(default_factory=list)
    optimizations_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-ready dictionary with string paths."""
        return {
            "schema_version": self.schema_version,
            "version": self.version,
            "app_dir": str(self.app_dir),
            "data_dir": str(self.data_dir),
            "profile": self.profile,
            "modules": list(self.modules),
            "harnesses": list(self.harnesses),
            "optimizations_enabled": self.optimizations_enabled,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a deterministic JSON string."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "InstallState":
        """Validate and deserialize a dictionary produced by :meth:`to_dict`."""
        _assert_mapping(raw)
        schema_version = _require_int(raw, "schema_version")
        if schema_version != REQUIRED_SCHEMA_VERSION:
            raise InstallStateError(
                f"unsupported schema version {schema_version}, "
                f"expected {REQUIRED_SCHEMA_VERSION}"
            )
        version = _require_str(raw, "version")
        app_dir = _require_absolute_path(raw, "app_dir")
        data_dir = _require_absolute_path(raw, "data_dir")
        profile = _require_str(raw, "profile")
        modules = _require_str_list(raw, "modules", optional=True)
        harnesses = _require_str_list(raw, "harnesses", optional=True)
        optimizations_enabled = bool(raw.get("optimizations_enabled", False))

        if app_dir == data_dir:
            raise InstallStateError(
                f"application directory cannot match data directory: {app_dir}"
            )

        _reject_data_inside_git_worktree(data_dir)

        return cls(
            schema_version=schema_version,
            version=version,
            app_dir=app_dir,
            data_dir=data_dir,
            profile=profile,
            modules=modules,
            harnesses=harnesses,
            optimizations_enabled=optimizations_enabled,
        )

    @classmethod
    def from_json(cls, text: str) -> "InstallState":
        """Parse and validate a JSON string."""
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InstallStateError(f"invalid JSON: {exc}") from exc
        return cls.from_dict(raw)

    @classmethod
    def load(cls, path: Path) -> "InstallState":
        """Load and validate ``install-state.json`` from *path*."""
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise InstallStateError(f"install state not found: {path}") from exc
        except OSError as exc:
            raise InstallStateError(f"cannot read install state: {exc}") from exc
        return cls.from_json(text)

    def save(self, path: Path) -> None:
        """Write this state to *path* atomically via a sibling temporary file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(self.to_json() + "\n", encoding="utf-8")
        tmp.replace(path)


def new_install_state(
    version: str,
    app_dir: Path,
    data_dir: Path,
    profile: str = DEFAULT_PROFILE,
    modules: list[str] | None = None,
    harnesses: list[str] | None = None,
    optimizations_enabled: bool = False,
) -> InstallState:
    """Create a validated :class:`InstallState` for a fresh install.

    This helper applies the same validation rules as
    :meth:`InstallState.from_dict`, so callers get immediate feedback during
    setup before anything is written to disk.
    """
    return InstallState.from_dict(
        {
            "schema_version": REQUIRED_SCHEMA_VERSION,
            "version": version,
            "app_dir": str(Path(app_dir).resolve()),
            "data_dir": str(Path(data_dir).resolve()),
            "profile": profile,
            "modules": list(modules or []),
            "harnesses": list(harnesses or []),
            "optimizations_enabled": optimizations_enabled,
        }
    )


def check_free_space(path: Path, min_bytes: int) -> tuple[int, bool]:
    """Return ``(available_bytes, sufficient)`` for *path*.

    *path* need not exist; its nearest existing ancestor is used. This is a
    thin, deterministic wrapper around :func:`shutil.disk_usage` so the UI can
    substitute a mock during tests.
    """
    path = Path(path)
    probe = path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    usage = shutil.disk_usage(probe)
    return usage.free, usage.free >= min_bytes


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------


def _assert_mapping(raw: Any) -> None:
    if not isinstance(raw, dict):
        raise InstallStateError("install state must be a JSON object")


def _require_int(raw: dict[str, Any], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise InstallStateError(f"{key} must be an integer")
    return value


def _require_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise InstallStateError(f"{key} must be a non-empty string")
    return value


def _require_absolute_path(raw: dict[str, Any], key: str) -> Path:
    value = _require_str(raw, key)
    path = Path(value)
    if not path.is_absolute():
        raise InstallStateError(f"{key} must be an absolute path: {value}")
    return path


def _require_str_list(raw: dict[str, Any], key: str, optional: bool = False) -> list[str]:
    value = raw.get(key)
    if value is None:
        if optional:
            return []
        raise InstallStateError(f"{key} is required")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InstallStateError(f"{key} must be a list of strings")
    return list(value)


def _reject_data_inside_git_worktree(data_dir: Path) -> None:
    """Refuse to install private memory inside a Git worktree.

    Only blocks when ``git`` is available and successfully reports a toplevel
    that contains *data_dir*. All failure modes (git missing, not a worktree,
    subprocess errors) are treated as "not a worktree" and are ignored.
    """
    toplevel = _git_toplevel(data_dir)
    if toplevel is None:
        return
    try:
        data_dir.relative_to(toplevel)
    except ValueError:
        return
    raise InstallStateError(
        f"data directory cannot be inside a Git worktree: {data_dir} "
        f"(toplevel: {toplevel})"
    )


def _git_toplevel(path: Path) -> Path | None:
    """Return the Git toplevel for *path*, or ``None`` if unavailable."""
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(
            [git, "rev-parse", "--show-toplevel"],
            cwd=str(path) if path.exists() else str(path.parent),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    toplevel = result.stdout.strip()
    if not toplevel:
        return None
    return Path(toplevel)
