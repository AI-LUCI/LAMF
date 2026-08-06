"""Post-installation orchestration run by Inno Setup after file extraction.

This script is executed by the embedded Python interpreter inside the installed
application directory.  It initializes (or upgrades) the LAMF data directory,
persists install-state.json, and configures the selected agent harnesses.

Inno Setup passes parameters either as environment variables or command-line
arguments:

  LAMF_APP_DIR                application directory (<install-dir>)
  LAMF_DATA_DIR               private memory directory
  LAMF_PROFILE                security profile (default: controlled)
  LAMF_HARNESSES              comma-separated harness ids, or empty
  LAMF_MODULES                comma-separated optimization module ids, or empty
  LAMF_OPTIMIZATIONS_ENABLED  "1"/"true" to enable the optimization master switch
  LAMF_SILENT                 "1"/"true" for non-interactive mode
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Make app/ importable when this script is run from the installed layout.
_APP_DIR = os.environ.get("LAMF_APP_DIR")
if _APP_DIR:
    _APP_PATH = Path(_APP_DIR) / "app"
    if str(_APP_PATH) not in sys.path:
        sys.path.insert(0, str(_APP_PATH))

try:
    from installer.windows import harness_adapters, install_state
except ImportError:  # pragma: no cover - source-tree fallback
    import harness_adapters
    import install_state


DEFAULT_PROFILE = "controlled"
# Complete set of artifacts created by a successful ``lamf init``.  A data
# directory is considered initialized only when every one of these exists,
# lamf.db is nonzero, and ``lamf doctor`` succeeds.
INSTANCE_ARTIFACTS = {"lamf.db", "events", "spool", "policy.yaml",
                      "instance.key", "operator.token"}

# Environment additions that force the embedded Python interpreter to use UTF-8
# for filesystem paths and stdio, even on Windows with a legacy ANSI code page.
# Inherited environment is preserved so PATH, HOME, and installer variables
# remain available to the child process.
PYTHON_UTF8_ENV_VARS = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def _utf8_env() -> dict[str, str]:
    """Return a copy of the current environment with UTF-8 Python flags set."""
    env = dict(os.environ)
    env.update(PYTHON_UTF8_ENV_VARS)
    return env
ALL_HARNESS_IDS = ("codex", "claude", "kimi", "gemini", "grok",
                   "openclaw", "hermes", "generic")
ALL_MODULE_IDS = (
    "minimal-solution",
    "verified-execution",
    "selective-workflows",
    "stale-context-guards",
    "surgical-changes",
)


class PostInstallError(RuntimeError):
    """A fatal post-install step failed."""


def _env_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _is_inside_git_worktree(path: Path) -> bool:
    """Return True when *path* or any ancestor lies inside a Git worktree."""
    if not path.exists():
        if path.parent == path:
            return False
        return _is_inside_git_worktree(path.parent)

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(path),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False

    if result.returncode == 0 and result.stdout.strip().lower() == "true":
        return True

    if path.parent != path:
        return _is_inside_git_worktree(path.parent)
    return False


def _normalize_harnesses(value: str | None) -> list[str]:
    """Return a deduplicated list of supported harness ids."""
    raw = _split_list(value)
    return [hid for hid in dict.fromkeys(raw) if hid in ALL_HARNESS_IDS]


def _normalize_modules(value: str | None) -> list[str]:
    """Return a deduplicated list of module ids (no validation here)."""
    return _split_list(value)


def _ensure_app_importable(app_dir: Path) -> None:
    """Insert ``<app_dir>/app`` at the front of ``sys.path`` for packaged imports."""
    app_path = str(Path(app_dir) / "app")
    if app_path not in sys.path:
        sys.path.insert(0, app_path)


def _import_optimizations(app_dir: Path):
    """Import ``lamf.optimizations`` after the packaged runtime is on ``sys.path``."""
    _ensure_app_importable(app_dir)
    import lamf.optimizations as opts  # noqa: E402
    return opts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse environment variables and command-line switches."""
    if argv is None:
        argv = sys.argv[1:]

    # Inno Setup passes parameters with a leading slash on Windows; normalize
    # them to GNU-style so argparse can handle them.
    normalized: list[str] = []
    for arg in argv:
        if os.name == "nt" and arg.startswith("/") and not arg.startswith("//"):
            body = arg[1:]
            if "=" in body:
                key, value = body.split("=", 1)
                normalized.append(f"--{key.lower().replace('_', '-')}={value}")
            else:
                normalized.append(f"--{body.lower().replace('_', '-')}")
        else:
            normalized.append(arg)

    parser = argparse.ArgumentParser(
        description="LAMF Windows post-installation orchestration",
    )
    parser.add_argument("--app-dir", default=os.environ.get("LAMF_APP_DIR"),
                        help="application directory")
    parser.add_argument("--data-dir", default=os.environ.get("LAMF_DATA_DIR"),
                        help="private memory directory")
    parser.add_argument("--profile", default=os.environ.get("LAMF_PROFILE", DEFAULT_PROFILE),
                        help="security profile")
    parser.add_argument("--harnesses", default=os.environ.get("LAMF_HARNESSES", ""),
                        help="comma-separated harness ids")
    parser.add_argument("--modules", "--optimizations",
                        default=os.environ.get("LAMF_MODULES", ""),
                        help="comma-separated optimization module ids")
    parser.add_argument("--optimizations-enabled",
                        default=os.environ.get("LAMF_OPTIMIZATIONS_ENABLED", ""),
                        help="master optimization switch")
    parser.add_argument("--silent",
                        default=os.environ.get("LAMF_SILENT", ""),
                        help="non-interactive mode")
    parser.add_argument("--log-file",
                        default=os.environ.get("LAMF_LOG_FILE", ""),
                        help="path to capture stdout and stderr")
    return parser.parse_args(normalized)


def _resolved_args(args: argparse.Namespace) -> tuple[Path, Path, str, list[str],
                                                       list[str], bool, bool, Path | None]:
    if not args.app_dir:
        raise PostInstallError("LAMF_APP_DIR is required")
    if not args.data_dir:
        raise PostInstallError("LAMF_DATA_DIR is required")
    app_dir = Path(args.app_dir).resolve()
    data_dir = Path(args.data_dir).resolve()
    profile = args.profile or DEFAULT_PROFILE
    harnesses = _normalize_harnesses(args.harnesses)
    modules = _normalize_modules(args.modules)
    optimizations_enabled = _env_bool(args.optimizations_enabled)
    silent = _env_bool(args.silent)
    log_file = Path(args.log_file) if args.log_file else None
    return (app_dir, data_dir, profile, harnesses, modules,
            optimizations_enabled, silent, log_file)


def _dir_contents(data_dir: Path) -> set[str]:
    """Return the set of top-level names inside *data_dir*, or an empty set."""
    if not data_dir.is_dir():
        return set()
    return {p.name for p in data_dir.iterdir()}


def _doctor_succeeds(app_dir: Path, data_dir: Path) -> bool:
    """Return True when ``lamf doctor`` reports the instance healthy."""
    python = app_dir / "python" / "python.exe"
    if not python.is_file():
        return False
    result = subprocess.run(
        [str(python), "-B", "-m", "lamf.cli", "doctor",
         "--data-dir", str(data_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_utf8_env(),
    )
    return result.returncode == 0


def _data_dir_initialized(data_dir: Path, app_dir: Path) -> bool:
    """True when *data_dir* holds a complete, usable LAMF instance.

    A partial instance (e.g. only lamf.db present) must never be treated as
    healthy, because downstream steps assume every required artifact exists.
    """
    if not data_dir.is_dir():
        return False
    present = _dir_contents(data_dir)
    if not INSTANCE_ARTIFACTS <= present:
        return False

    db_path = data_dir / "lamf.db"
    if not db_path.is_file() or db_path.stat().st_size == 0:
        return False

    return _doctor_succeeds(app_dir, data_dir)


def _partial_instance_artifacts(data_dir: Path) -> set[str]:
    """Return the subset of instance artifacts present when state is partial."""
    if not data_dir.is_dir():
        return set()
    present = _dir_contents(data_dir)
    found = present & INSTANCE_ARTIFACTS
    return found if found and not INSTANCE_ARTIFACTS <= present else set()


def _run_init(app_dir: Path, data_dir: Path, profile: str) -> None:
    """Run ``lamf init`` through the embedded Python interpreter."""
    python = app_dir / "python" / "python.exe"
    if not python.is_file():
        raise PostInstallError(f"embedded Python not found: {python}")

    data_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(python), "-B", "-m", "lamf.cli", "init",
        "--profile", profile,
        "--data-dir", str(data_dir),
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", env=_utf8_env()
    )
    if result.returncode != 0:
        raise PostInstallError(
            f"lamf init failed (exit {result.returncode}): {result.stderr.strip()}"
        )


def _run_init_safe(app_dir: Path, data_dir: Path, profile: str) -> None:
    """Run ``lamf init`` and roll back only artifacts created by this attempt.

    If *data_dir* did not exist before this call and init fails, the newly
    created empty directory is removed so the next retry starts clean.  Any
    pre-existing files are left untouched.
    """
    preexisting = _dir_contents(data_dir)
    created_dir = not data_dir.exists()
    try:
        _run_init(app_dir, data_dir, profile)
    except PostInstallError:
        # Remove only artifacts created by this failed attempt.
        for name in _dir_contents(data_dir) - preexisting:
            path = data_dir / name
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            except OSError:
                pass
        # If we created the directory and it is now empty, remove it.
        if created_dir and data_dir.is_dir() and not any(data_dir.iterdir()):
            try:
                data_dir.rmdir()
            except OSError:
                pass
        raise


def _write_install_state(
    app_dir: Path,
    data_dir: Path,
    profile: str,
    harnesses: list[str],
    modules: list[str],
    optimizations_enabled: bool,
) -> None:
    """Write validated install-state.json to both app and data directories."""
    version = _read_version(app_dir)
    state = install_state.new_install_state(
        version=version,
        app_dir=app_dir,
        data_dir=data_dir,
        profile=profile,
        modules=modules,
        harnesses=harnesses,
        optimizations_enabled=optimizations_enabled,
    )
    state.save(app_dir / "install-state.json")
    state.save(data_dir / "install-state.json")


def _read_version(app_dir: Path) -> str:
    """Read the LAMF version from the bundled version.json."""
    version_file = app_dir / "version.json"
    if version_file.is_file():
        import json
        data = json.loads(version_file.read_text(encoding="utf-8"))
        return str(data.get("lamf_version", "0.0.0"))
    return "0.0.0"


def _configure_optimizations(
    app_dir: Path,
    data_dir: Path,
    modules: list[str],
    optimizations_enabled: bool,
    opts=None,
) -> dict:
    """Initialize optimization config and enable exactly the selected modules."""
    if opts is None:
        opts = _import_optimizations(app_dir)

    # Discover what modules are actually packaged so we can reject unknown ids
    # and explicitly disable every unselected module.
    known = {item["id"] for item in opts.discover()}
    unknown = [m for m in modules if m not in known]
    if unknown:
        raise PostInstallError(
            f"unknown optimization modules: {', '.join(unknown)}; "
            f"expected: {', '.join(sorted(known))}"
        )

    selected = set(modules)
    opts.initialize(data_dir)
    opts.set_global(data_dir, optimizations_enabled)
    for module_id in sorted(known):
        opts.set_module(data_dir, module_id, module_id in selected)

    return opts.status(data_dir)


def _configure_harnesses(
    app_dir: Path,
    data_dir: Path,
    harnesses: list[str],
    *,
    silent: bool,
) -> dict[str, dict]:
    """Connect each selected harness and return per-harness results."""
    lamf_exe = app_dir / "lamf.exe"
    results: dict[str, dict] = {}
    for harness_id in harnesses:
        try:
            # Harness adapters resolve the user's config directory from the
            # environment; tests can override HOME/XDG_CONFIG_HOME to isolate.
            result = harness_adapters.connect(
                harness_id, lamf_exe, data_dir,
                config_dir=_harness_config_dir(harness_id),
            )
            results[harness_id] = {"success": True, **result}
        except Exception as exc:
            results[harness_id] = {"success": False, "error": str(exc)}
            if not silent:
                print(f"Warning: harness {harness_id} failed: {exc}")
    return results


def _harness_config_dir(harness_id: str) -> Path:
    """Return the directory where the harness adapter should look for configs.

    Each harness stores its user-level config in a dedicated dot-directory
    beneath the user's profile. The legacy Kimi path is handled by the adapter.
    """
    home = Path.home()
    mapping = {
        "codex": home / ".codex",
        "claude": home / ".claude",
        "kimi": home / ".kimi-code",
        "gemini": home / ".gemini",
        "grok": home / ".grok",
        "hermes": home / ".hermes",
        "openclaw": home / ".openclaw",
    }
    return mapping.get(harness_id, home)


def run_post_install(
    app_dir: Path,
    data_dir: Path,
    profile: str,
    harnesses: list[str],
    modules: list[str],
    optimizations_enabled: bool,
    *,
    silent: bool,
) -> dict:
    """Execute the full post-install sequence.

    Returns a summary dict for the caller.
    """
    existing = _data_dir_initialized(data_dir, app_dir)

    if existing:
        if not silent:
            print(f"Existing LAMF data found at {data_dir}; preserving memory.")
    else:
        partial = _partial_instance_artifacts(data_dir)
        if partial:
            raise PostInstallError(
                f"partial LAMF data found at {data_dir}: {sorted(partial)}. "
                "Repair the instance or remove the data directory before reinstalling."
            )
        if not silent:
            print(f"Initializing LAMF data at {data_dir} (profile={profile})...")
        _run_init_safe(app_dir, data_dir, profile)

    optimization_status = _configure_optimizations(
        app_dir, data_dir, modules, optimizations_enabled,
    )

    _write_install_state(
        app_dir, data_dir, profile, harnesses, modules, optimizations_enabled,
    )

    harness_results = _configure_harnesses(
        app_dir, data_dir, harnesses, silent=silent,
    )

    return {
        "app_dir": str(app_dir),
        "data_dir": str(data_dir),
        "profile": profile,
        "existing_data": existing,
        "optimizations": optimization_status,
        "harnesses": harness_results,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        (app_dir, data_dir, profile, harnesses, modules,
         optimizations_enabled, silent, log_file) = _resolved_args(args)
    except PostInstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Redirect stdout/stderr to a log file when requested by the installer.
    log_handle = None
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_handle = open(log_file, "w", encoding="utf-8")  # noqa: SIM115
        sys.stdout = log_handle
        sys.stderr = log_handle

    try:
        result = run_post_install(
            app_dir=app_dir,
            data_dir=data_dir,
            profile=profile,
            harnesses=harnesses,
            modules=modules,
            optimizations_enabled=optimizations_enabled,
            silent=silent,
        )
    except PostInstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        if log_handle:
            log_handle.close()

    if not silent:
        print(f"LAMF installed at {app_dir}")
        print(f"Data directory: {result['data_dir']}")
        print(f"Profile: {result['profile']}")
        if result["harnesses"]:
            for hid, hr in result["harnesses"].items():
                status = "ok" if hr["success"] else "failed"
                print(f"  harness {hid}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
