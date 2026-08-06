"""Payload verification used by the build and integration tests.

The checks run against the real assembled payload directory:

1. Embedded ``python/python.exe`` can import ``yaml`` and ``nacl.bindings``.
2. ``python -m lamf.cli init`` succeeds in a temporary data directory using
   only the packaged runtime.
3. The payload manifest is present and verifies.
4. The ``app/installer/windows`` tree contains only the allowlisted helper
   modules; no build scripts, tests, caches, compiled outputs, docs, or
   source-only files are present.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from manifest import verify_manifest  # noqa: E402
from payload import (  # noqa: E402
    FORBIDDEN_INSTALLER_DIRS,
    FORBIDDEN_INSTALLER_SUFFIXES,
    INSTALLER_WINDOWS_ALLOWED_FILES,
    RUNTIME_DATA_PATHS,
)


class PayloadVerificationError(RuntimeError):
    """A payload verification gate failed."""


#: Environment variables that must be stripped during verification so the
#: packaged runtime cannot accidentally resolve back to the source checkout.
_SANITIZE_ENV_VARS: tuple[str, ...] = (
    "PYTHONPATH",
    "PYTHONHOME",
    "LAMF_DATA_DIR",
    "LAMF_VAULT",
    "LAMF_VENV",
)


def _run_embedded_python(
    python: Path,
    code: str,
    *,
    env: dict | None = None,
    cwd: Path | None = None,
) -> str:
    """Run *code* through the embedded Python interpreter and return stdout."""
    result = subprocess.run(
        [str(python), "-B", "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd) if cwd else None,
    )
    if result.returncode != 0:
        raise PayloadVerificationError(
            f"embedded Python check failed (exit {result.returncode}):\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def _sanitized_env() -> dict[str, str]:
    """Return a copy of the current environment with source-tree leaks removed."""
    env = dict(os.environ)
    for name in _SANITIZE_ENV_VARS:
        env.pop(name, None)
    # Force a neutral temp directory so any accidental absolute fallback does
    # not land inside the repository.
    env["TMP"] = env["TEMP"] = tempfile.gettempdir()
    return env


def _verify_imports(python: Path) -> None:
    """Prove ``yaml`` and ``nacl.bindings`` import without errors."""
    _run_embedded_python(
        python,
        "import yaml, nacl.bindings; print('imports_ok')",
        env=_sanitized_env(),
    )


def _run_lamf(python: Path, args: list[str], *, cwd: Path, env: dict) -> str:
    """Run ``python -m lamf.cli <args>`` and return stdout, raising on failure."""
    result = subprocess.run(
        [str(python), "-B", "-m", "lamf.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
    )
    if result.returncode != 0:
        raise PayloadVerificationError(
            f"lamf {' '.join(args)} failed (exit {result.returncode}):\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def _verify_lamf_init(python: Path, app_dir: Path) -> None:
    """Run an actual ``lamf init`` in a temporary data directory.

    The subprocess runs with its cwd set to a fresh temp directory outside the
    source tree and with PYTHONPATH/LAMF_DATA_DIR removed, so a missing runtime
    asset cannot be satisfied by the repository checkout.
    """
    with tempfile.TemporaryDirectory(prefix="lamf-verify-") as td:
        td_path = Path(td)
        data_dir = td_path / "data"
        env = _sanitized_env()
        _run_lamf(
            python,
            ["init", "--profile", "controlled", "--data-dir", str(data_dir)],
            cwd=td_path,
            env=env,
        )

        required = {
            "lamf.db", "events", "spool", "policy.yaml",
            "instance.key", "operator.token",
        }
        missing = required - {p.name for p in data_dir.iterdir()}
        if missing:
            raise PayloadVerificationError(
                f"lamf init missing artifacts: {sorted(missing)}"
            )

        db_path = data_dir / "lamf.db"
        if not db_path.is_file() or db_path.stat().st_size == 0:
            raise PayloadVerificationError(
                f"lamf.db was not created or is empty: {db_path}"
            )

        print("[verify] packaged lamf doctor --deep")
        _run_lamf(python, ["doctor", "--deep", "--data-dir", str(data_dir)],
                  cwd=td_path, env=env)

        print("[verify] packaged lamf verify --deep")
        _run_lamf(python, ["verify", "--deep", "--data-dir", str(data_dir)],
                  cwd=td_path, env=env)


def _verify_runtime_data(payload_dir: Path) -> None:
    """Ensure every runtime data path resolved from the package root is present."""
    for rel in RUNTIME_DATA_PATHS:
        path = payload_dir / rel
        if not path.exists():
            raise PayloadVerificationError(f"missing runtime data asset: {rel}")


def _verify_manifest(payload_dir: Path) -> None:
    """Verify the payload manifest covers every file without mismatches."""
    result = verify_manifest(payload_dir)
    if not result["ok"]:
        details = []
        for category in ("missing", "mismatched", "extra", "errors"):
            items = result.get(category, [])
            if items:
                details.append(f"{category}: {items}")
        raise PayloadVerificationError(
            f"payload manifest verification failed: {'; '.join(details)}"
        )


def _verify_installer_allowlist(payload_dir: Path) -> None:
    """Ensure ``app/installer/windows`` contains only the allowlisted files."""
    installer_dir = payload_dir / "app" / "installer" / "windows"
    if not installer_dir.is_dir():
        raise PayloadVerificationError(
            f"installer helper directory missing: {installer_dir}"
        )

    allowed = set(INSTALLER_WINDOWS_ALLOWED_FILES)
    found_files: set[str] = set()
    for path in installer_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(installer_dir).as_posix()
        found_files.add(rel)
        for forbidden in FORBIDDEN_INSTALLER_DIRS:
            if forbidden in rel.split("/"):
                raise PayloadVerificationError(
                    f"forbidden directory {forbidden!r} in installer tree: {rel}"
                )
        if rel.lower().endswith(FORBIDDEN_INSTALLER_SUFFIXES):
            raise PayloadVerificationError(
                f"forbidden file suffix in installer tree: {rel}"
            )

    unexpected = found_files - allowed
    if unexpected:
        raise PayloadVerificationError(
            f"unexpected files in app/installer/windows: {sorted(unexpected)}"
        )


def verify_payload(payload_dir: Path) -> None:
    """Run every payload verification gate.

    Raises :class:`PayloadVerificationError` on the first failure.  The final
    build treats any failure here as fatal.
    """
    payload_dir = Path(payload_dir)
    python = payload_dir / "python" / "python.exe"
    app_dir = payload_dir / "app"
    if not python.is_file():
        raise PayloadVerificationError(f"embedded Python not found: {python}")
    if not app_dir.is_dir():
        raise PayloadVerificationError(f"application directory not found: {app_dir}")

    print("[verify] embedded Python imports: yaml + nacl.bindings")
    _verify_imports(python)

    print("[verify] packaged LAMF init in temporary data directory")
    _verify_lamf_init(python, app_dir)

    print("[verify] runtime data assets resolved from package root")
    _verify_runtime_data(payload_dir)

    print("[verify] payload manifest integrity")
    _verify_manifest(payload_dir)

    print("[verify] installer/windows allowlist")
    _verify_installer_allowlist(payload_dir)

    print("[verify] all gates passed")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_payload.py <payload-dir>")
    try:
        verify_payload(Path(sys.argv[1]))
    except PayloadVerificationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
