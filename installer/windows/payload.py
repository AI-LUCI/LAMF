"""Assemble the offline Windows installer payload.

The payload is a self-contained directory tree that Inno Setup compresses into
``LAMF-Setup-x64.exe``.  It contains the embedded CPython runtime, the LAMF
reference runtime, optional optimization modules, licenses, version metadata,
and a reproducible SHA-256 manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from build_config import (  # noqa: E402
    CFFI_WHEEL_FILENAME,
    OPTIMIZATION_PACK_COMMIT,
    OPTIMIZATION_PACK_DATE,
    OPTIMIZATION_PACK_TAG,
    PYCPARSER_WHEEL_FILENAME,
    PYTHON_EMBED_VERSION,
    BuildConfig,
    default_build_config,
)
from manifest import generate_manifest  # noqa: E402

PAYLOAD_DIR = ROOT.parent.parent / "dist" / "lamf-windows-payload"
BUILD_DIR = ROOT / "build"
LAUNCHER_DIR = BUILD_DIR / "launchers"
RUNTIME_SOURCE = ROOT.parent.parent / "runtime"
#: Portable default optimization pack location: a sibling checkout named
#: ``LAMF-Optimizations`` next to the project root.  This is overridable via
#: ``--optimization-pack-source`` or ``LAMF_OPTIMIZATION_PACK_SOURCE``.
DEFAULT_OPTIMIZATION_PACK_SIBLING = ROOT.parent.parent.parent / "LAMF-Optimizations"

LICENSE_FILES = ("LICENSE", "CHANGELOG.md", "Credit.md")

#: Required runtime data files that are resolved from the package root (not
#: from ``app/``).  These are copied into the payload root so the installed
#: runtime finds them after ``app/`` becomes the runtime directory.
#:   - ``02_SECURITY/profiles`` is read by ``lamf.policy``.
#:   - ``04_STORAGE/SCHEMA.sql`` is executed by ``lamf.store.Store.open``.
RUNTIME_DATA_PATHS: tuple[str, ...] = (
    "02_SECURITY/profiles",
    "04_STORAGE/SCHEMA.sql",
)

#: Only these installer helper modules are needed inside the installed ``app/``
#: tree.  Everything else (build scripts, setup.iss, tests, caches, compiled
#: build outputs, docs, and source-only files) must stay out of the payload.
INSTALLER_WINDOWS_ALLOWED_FILES: tuple[str, ...] = (
    "__init__.py",
    "install_state.py",
    "uninstall_helper.py",
    "harness_adapters.py",
    "harness_tx.py",
)

#: Forbidden directories and file suffixes that must never appear inside the
#: packaged ``app/installer/windows/`` tree.
FORBIDDEN_INSTALLER_DIRS: tuple[str, ...] = (
    "__pycache__",
    ".pytest_cache",
    "tests",
    "build",
    "cache",
    "innosetup",
)
FORBIDDEN_INSTALLER_SUFFIXES: tuple[str, ...] = (
    ".pdb",
    ".pyc",
    ".pyo",
    ".whl",
    ".zip",
    ".exe",
    ".iss",
    ".rs",
)


class PayloadError(RuntimeError):
    """The payload could not be assembled."""


def _utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _default_optimization_pack_source() -> Path:
    """Return the default optimization pack source path.

    Resolution order:

    1. ``LAMF_OPTIMIZATION_PACK_SOURCE`` environment variable.
    2. Sibling ``LAMF-Optimizations`` directory next to the project root.
    3. Raise :class:`PayloadError` with a clear action if neither is available.
    """
    if env_src := os.environ.get("LAMF_OPTIMIZATION_PACK_SOURCE"):
        return Path(env_src)
    if DEFAULT_OPTIMIZATION_PACK_SIBLING.is_dir():
        return DEFAULT_OPTIMIZATION_PACK_SIBLING
    raise PayloadError(
        "Optimization pack source not configured. "
        "Set the LAMF_OPTIMIZATION_PACK_SOURCE environment variable, "
        "place a LAMF-Optimizations checkout next to the project root, "
        "or pass --optimization-pack-source explicitly."
    )


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _verify_pack_commit(src: Path, expected_commit: str) -> None:
    """Ensure the local optimization pack checkout matches the pinned commit."""
    git_dir = src / ".git"
    if not git_dir.is_dir():
        raise PayloadError(
            f"optimization pack at {src} is not a git checkout; cannot verify commit"
        )
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(src),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise PayloadError("git is required to verify the optimization pack commit") from exc
    if result.returncode != 0:
        raise PayloadError(f"git rev-parse failed: {result.stderr.strip()}")
    actual = result.stdout.strip()
    if actual != expected_commit:
        raise PayloadError(
            f"optimization pack commit mismatch: expected {expected_commit}, got {actual}"
        )


def _copytree_filtered(
    src: Path,
    dst: Path,
    *,
    exclude_dirs: tuple[str, ...] = ("__pycache__", ".venv", "tests", ".pytest_cache"),
) -> None:
    """Recursively copy *src* to *dst* while skipping excluded directories."""
    if not dst.exists():
        dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in exclude_dirs:
            continue
        dest_item = dst / item.name
        if item.is_dir():
            _copytree_filtered(item, dest_item, exclude_dirs=exclude_dirs)
        else:
            shutil.copy2(item, dest_item)


def _extract_wheel(wheel_path: Path, site_packages: Path) -> None:
    """Extract a wheel into the site-packages directory.

    Bytecode directories and compiled files are stripped so the payload stays
    clean of ``__pycache__`` and ``.pyc`` artifacts.
    """
    site_packages.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel_path, "r") as zf:
        for member in zf.namelist():
            if member.endswith("/"):
                continue
            if "/__pycache__/" in member or member.startswith("__pycache__/"):
                continue
            if member.lower().endswith((".pyc", ".pyo")):
                continue
            zf.extract(member, site_packages)


def _python_pth_name(python_version: str) -> str:
    """Return the embeddable Python zip and ._pth base name (e.g. python311)."""
    parts = python_version.split(".")
    return f"python{parts[0]}{parts[1]}"


def _configure_python_pth(python_dir: Path) -> None:
    """Write the ``._pth`` file so ``app`` and site-packages are on sys.path."""
    # The embeddable package ships a ``pythonNNN._pth`` file that disables
    # ``site`` unless ``import site`` is present.
    pth_base = _python_pth_name(PYTHON_EMBED_VERSION)
    pth_candidates = [
        python_dir / f"{pth_base}._pth",
        python_dir / "python._pth",
    ]
    pth_file = None
    for candidate in pth_candidates:
        if candidate.exists():
            pth_file = candidate
            break
    if pth_file is None:
        pth_file = pth_candidates[0]

    lines = [
        f"{pth_base}.zip",
        ".",
        r"..\app",
        r"..\app\installer\windows",
        r".\Lib\site-packages",
        "import site",
    ]
    pth_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _extract_embedded_python(zip_path: Path, python_dir: Path) -> None:
    """Unpack the CPython embeddable zip into ``python/``."""
    if python_dir.exists():
        shutil.rmtree(python_dir)
    python_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(python_dir)
    _configure_python_pth(python_dir)


def _copy_launchers(
    launcher_dir: Path,
    output_dir: Path,
) -> None:
    """Copy the launcher executables to the payload root."""
    for name in ("lamf.exe", "lamf-control.exe", "uninstall.exe"):
        src = launcher_dir / name
        if not src.is_file():
            raise PayloadError(f"launcher not found: {src}")
        shutil.copy2(src, output_dir / name)


def _copy_runtime(runtime_source: Path, app_dir: Path) -> None:
    """Copy the LAMF runtime into ``app/``.

    Test directories, virtual environments, caches, and bytecode are skipped.
    """
    _copytree_filtered(runtime_source, app_dir,
                       exclude_dirs=("__pycache__", ".venv", "tests",
                                     ".pytest_cache"))


def _copy_installer_windows_modules(app_dir: Path) -> None:
    """Copy only the installer helper modules needed at runtime into ``app/``.

    This is an explicit allowlist; it never copies build scripts, tests,
    caches, compiled outputs, docs, or source-only files.
    """
    dst = app_dir / "installer" / "windows"
    dst.mkdir(parents=True, exist_ok=True)
    for name in INSTALLER_WINDOWS_ALLOWED_FILES:
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, dst / name)
        elif name == "__init__.py":
            (dst / name).write_text("", encoding="utf-8")


def _copy_security_profiles(project_root: Path, output_dir: Path) -> None:
    """Copy security profile YAML files to the payload root.

    The runtime resolves ``02_SECURITY/profiles`` from the package root, which
    in the installed layout is the payload root (``app`` is the runtime
    directory, so ``app/lamf/policy.py`` resolves two levels up).
    """
    src = project_root / "02_SECURITY" / "profiles"
    if not src.is_dir():
        raise PayloadError(f"security profiles not found: {src}")
    dst = output_dir / "02_SECURITY" / "profiles"
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for path in src.iterdir():
        if path.is_file() and path.suffix in (".yaml", ".yml"):
            shutil.copy2(path, dst / path.name)


def _copy_storage_schema(project_root: Path, output_dir: Path) -> None:
    """Copy the SQLite schema to the payload root.

    ``lamf.store.Store.open`` resolves ``04_STORAGE/SCHEMA.sql`` from the
    package root; in the installed layout the package root is the payload root
    and the runtime lives under ``app/``.
    """
    src = project_root / "04_STORAGE" / "SCHEMA.sql"
    if not src.is_file():
        raise PayloadError(f"storage schema not found: {src}")
    dst = output_dir / "04_STORAGE" / "SCHEMA.sql"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_optimizations(src: Path, dst: Path, expected_commit: str) -> None:
    """Copy the pinned optimization pack into ``optimizations/``."""
    _verify_pack_commit(src, expected_commit)
    if dst.exists():
        shutil.rmtree(dst)
    _copytree_filtered(src, dst, exclude_dirs=(".git", "__pycache__", ".venv",
                                               "tests", ".pytest_cache"))


def _copy_licenses(
    output_dir: Path,
    optimization_pack_dir: Path,
    project_root: Path,
) -> None:
    """Copy core and optimization-pack licenses/credits into ``licenses/``."""
    licenses_dir = output_dir / "licenses"
    if licenses_dir.exists():
        shutil.rmtree(licenses_dir)
    licenses_dir.mkdir(parents=True, exist_ok=True)

    for name in LICENSE_FILES:
        src = project_root / name
        if src.is_file():
            shutil.copy2(src, licenses_dir / name)

    opt_licenses = licenses_dir / "optimizations"
    opt_licenses.mkdir(parents=True, exist_ok=True)
    for name in ("LICENSE", "Credit.md"):
        src = optimization_pack_dir / name
        if src.is_file():
            shutil.copy2(src, opt_licenses / name)


def _write_version_json(
    output_dir: Path,
    *,
    lamf_version: str,
    python_version: str,
    optimization_commit: str,
    optimization_tag: str,
    optimization_date: str,
    build_timestamp: str,
) -> None:
    version_info = {
        "lamf_version": lamf_version,
        "python_version": python_version,
        "optimization_pack_commit": optimization_commit,
        "optimization_pack_tag": optimization_tag,
        "optimization_pack_date": optimization_date,
        "build_timestamp": build_timestamp,
    }
    (output_dir / "version.json").write_text(
        json.dumps(version_info, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _ensure_init_py(app_dir: Path, dotted_pkg: str) -> None:
    """Create empty ``__init__.py`` files for a dotted package under app/."""
    parts = dotted_pkg.split(".")
    for i in range(1, len(parts) + 1):
        init_file = app_dir.joinpath(*parts[:i]) / "__init__.py"
        if not init_file.exists():
            init_file.write_text("", encoding="utf-8")


def assemble_payload(
    *,
    output_dir: Path | None = None,
    launcher_dir: Path | None = None,
    python_embed_zip: Path | None = None,
    pyyaml_wheel: Path | None = None,
    pynacl_wheel: Path | None = None,
    cffi_wheel: Path | None = None,
    pycparser_wheel: Path | None = None,
    runtime_source: Path | None = None,
    optimization_pack_source: Path | None = None,
    project_root: Path | None = None,
    lamf_version: str | None = None,
    build_timestamp: str | None = None,
) -> Path:
    """Build the complete offline payload and return its root path."""
    output_dir = Path(output_dir) if output_dir is not None else PAYLOAD_DIR
    launcher_dir = Path(launcher_dir) if launcher_dir is not None else BUILD_DIR
    python_embed_zip = Path(python_embed_zip) if python_embed_zip is not None else (
        BUILD_DIR / "cache" / f"python-{PYTHON_EMBED_VERSION}-embed-amd64.zip"
    )
    pyyaml_wheel = Path(pyyaml_wheel) if pyyaml_wheel is not None else (
        BUILD_DIR / "cache" / f"PyYAML-6.0.2-cp311-cp311-win_amd64.whl"
    )
    pynacl_wheel = Path(pynacl_wheel) if pynacl_wheel is not None else (
        BUILD_DIR / "cache" / f"PyNaCl-1.5.0-cp36-abi3-win_amd64.whl"
    )
    cffi_wheel = Path(cffi_wheel) if cffi_wheel is not None else (
        BUILD_DIR / "cache" / CFFI_WHEEL_FILENAME
    )
    pycparser_wheel = Path(pycparser_wheel) if pycparser_wheel is not None else (
        BUILD_DIR / "cache" / PYCPARSER_WHEEL_FILENAME
    )
    runtime_source = Path(runtime_source) if runtime_source is not None else RUNTIME_SOURCE
    optimization_pack_source = (
        Path(optimization_pack_source)
        if optimization_pack_source is not None
        else _default_optimization_pack_source()
    )
    project_root = Path(project_root) if project_root is not None else ROOT.parent.parent
    if lamf_version is None:
        lamf_version = _read_lamf_version(runtime_source)
    build_timestamp = build_timestamp or _utc_timestamp()

    # Validate required inputs.
    for path, label in (
        (python_embed_zip, "CPython embeddable zip"),
        (pyyaml_wheel, "PyYAML wheel"),
        (pynacl_wheel, "PyNaCl wheel"),
        (cffi_wheel, "CFFI wheel"),
        (pycparser_wheel, "pycparser wheel"),
    ):
        if not path.is_file():
            raise PayloadError(f"{label} not found: {path}")
    for path, label in (
        (launcher_dir, "launcher build directory"),
        (runtime_source, "runtime source"),
        (optimization_pack_source, "optimization pack source"),
    ):
        if not path.is_dir():
            raise PayloadError(f"{label} not found: {path}")

    # Start with a clean output directory.
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Launchers.
    _copy_launchers(launcher_dir, output_dir)

    # Embedded Python runtime.
    python_dir = output_dir / "python"
    _extract_embedded_python(python_embed_zip, python_dir)

    # Wheels into site-packages.
    site_packages = python_dir / "Lib" / "site-packages"
    _extract_wheel(pyyaml_wheel, site_packages)
    _extract_wheel(pynacl_wheel, site_packages)
    _extract_wheel(cffi_wheel, site_packages)
    _extract_wheel(pycparser_wheel, site_packages)

    # LAMF runtime + explicitly-allowlisted installer helper modules needed at
    # install/uninstall/harness time.  No build scripts, setup.iss, tests,
    # caches, compiled outputs, docs, or source-only files are copied.
    app_dir = output_dir / "app"
    _copy_runtime(runtime_source, app_dir)
    _copy_installer_windows_modules(app_dir)
    _ensure_init_py(app_dir, "installer.windows")

    # Security profiles are runtime data; they live at the payload root because
    # ``app`` is the runtime directory in the installed layout.
    _copy_security_profiles(project_root, output_dir)

    # Storage schema is runtime data; same root-level resolution contract as
    # the security profiles.
    _copy_storage_schema(project_root, output_dir)

    # Optimization pack.
    opt_dir = output_dir / "optimizations"
    _copy_optimizations(optimization_pack_source, opt_dir, OPTIMIZATION_PACK_COMMIT)

    # Post-install script at the payload root so Inno Setup can run it without
    # exposing the internal app/ path layout to the wizard.
    post_install_src = ROOT / "post_install.py"
    if post_install_src.is_file():
        shutil.copy2(post_install_src, output_dir / "post_install.py")

    # Licenses and credits.
    _copy_licenses(output_dir, opt_dir, project_root)

    # Version metadata.
    _write_version_json(
        output_dir,
        lamf_version=lamf_version,
        python_version=PYTHON_EMBED_VERSION,
        optimization_commit=OPTIMIZATION_PACK_COMMIT,
        optimization_tag=OPTIMIZATION_PACK_TAG,
        optimization_date=OPTIMIZATION_PACK_DATE,
        build_timestamp=build_timestamp,
    )

    # Reproducible manifest.
    generate_manifest(output_dir)

    return output_dir


def _read_lamf_version(runtime_source: Path) -> str:
    """Read ``__version__`` from the runtime package."""
    init_file = runtime_source / "lamf" / "__init__.py"
    if not init_file.is_file():
        return "0.0.0"
    namespace: dict = {}
    exec(compile(init_file.read_text(encoding="utf-8"), str(init_file), "exec"), namespace)
    return str(namespace.get("__version__", "0.0.0"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assemble the LAMF Windows installer payload."
    )
    parser.add_argument(
        "--output-dir", type=Path, default=PAYLOAD_DIR,
        help="directory where the payload is assembled (default: dist/lamf-windows-payload)",
    )
    parser.add_argument(
        "--launcher-dir", type=Path, default=BUILD_DIR,
        help="directory containing lamf.exe and lamf-control.exe",
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=BUILD_DIR / "cache",
        help="directory containing downloaded wheels and Python zip",
    )
    parser.add_argument(
        "--runtime-source", type=Path, default=RUNTIME_SOURCE,
        help="path to the runtime/ source tree",
    )
    parser.add_argument(
        "--optimization-pack", type=Path, default=None,
        help="path to the local optimization pack checkout "
             "(default: LAMF_OPTIMIZATION_PACK_SOURCE env var or "
             "a sibling LAMF-Optimizations directory)",
    )
    parser.add_argument(
        "--project-root", type=Path, default=ROOT.parent.parent,
        help="path to the project root (for license files)",
    )
    args = parser.parse_args(argv)

    cache_dir = Path(args.cache_dir)
    try:
        assemble_payload(
            output_dir=args.output_dir,
            launcher_dir=args.launcher_dir,
            python_embed_zip=cache_dir / f"python-{PYTHON_EMBED_VERSION}-embed-amd64.zip",
            pyyaml_wheel=cache_dir / f"PyYAML-6.0.2-cp311-cp311-win_amd64.whl",
            pynacl_wheel=cache_dir / f"PyNaCl-1.5.0-cp36-abi3-win_amd64.whl",
            cffi_wheel=cache_dir / CFFI_WHEEL_FILENAME,
            pycparser_wheel=cache_dir / PYCPARSER_WHEEL_FILENAME,
            runtime_source=args.runtime_source,
            optimization_pack_source=args.optimization_pack,
            project_root=args.project_root,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
