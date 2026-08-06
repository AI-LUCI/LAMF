"""Build the LAMF Windows native launcher executables.

Compiles ``launcher.rs`` with the pinned Rust toolchain and emits two
identical executables that differ only by file name:

  * build/lamf.exe
  * build/lamf-control.exe

The Rust source decides its runtime behavior from ``std::env::current_exe()``,
so a single compilation plus copy is sufficient and guarantees identical code.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from build_config import RUSTC_VERSION  # noqa: E402


SOURCE = ROOT / "launcher.rs"
BUILD_DIR = ROOT / "build"


def parse_rustc_version(version_line: str) -> str:
    """Extract ``1.95.0`` from ``rustc 1.95.0 (59807616e 2026-04-14)``."""
    match = re.search(r"rustc\s+(\d+\.\d+\.\d+)", version_line)
    if not match:
        raise ValueError(f"cannot parse rustc version: {version_line!r}")
    return match.group(1)


def check_rustc() -> str:
    """Verify rustc is installed and matches the pinned version.

    Returns:
        The parsed version string.

    Raises:
        subprocess.CalledProcessError: if rustc cannot be executed.
        RuntimeError: if the installed version does not match ``RUSTC_VERSION``.
        ValueError: if rustc's version output cannot be parsed.
    """
    result = subprocess.run(
        ["rustc", "--version"], capture_output=True, text=True, check=True
    )
    version = parse_rustc_version(result.stdout.strip())
    if version != RUSTC_VERSION:
        raise RuntimeError(
            f"rustc version mismatch: found {version}, required {RUSTC_VERSION}"
        )
    return version


def derive_command(
    exe_path: Path, install_state: dict, argv: list[str]
) -> tuple[Path, list[str], dict[str, str]]:
    """Derive the pythonw.exe command line and environment for a launcher.

    This Python reimplementation mirrors the logic in ``launcher.rs`` and is
    used by unit tests so they do not require a compiled EXE.

    Args:
        exe_path: absolute path to the launcher executable.
        install_state: parsed contents of ``install-state.json``.
        argv: full argument vector, including the program name at index 0.

    Returns:
        Tuple of (python executable path, argument list, environment additions).

    Raises:
        ValueError: if ``data_dir`` is missing from the install state.
    """
    exe_path = Path(exe_path)
    exe_dir = exe_path.parent
    base = exe_path.stem.lower()

    data_dir = install_state.get("data_dir")
    if not data_dir:
        raise ValueError("data_dir missing from install-state.json")

    python = exe_dir / "python" / "pythonw.exe"
    env = {
        "LAMF_DATA_DIR": str(data_dir),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }

    if base == "uninstall":
        app_pkg = exe_dir / "app"
        # PYTHONPATH must include the packaged app directory so the module
        # package installer.windows can be resolved when run with -m.
        pythonpath = str(app_pkg)
        if existing := os.environ.get("PYTHONPATH"):
            pythonpath = f"{pythonpath};{existing}"
        env["PYTHONPATH"] = pythonpath
        # LAMF_DATA_DIR is not needed by the uninstall helper (it receives an
        # explicit /DATA_DIR switch) and is not set by the native launcher.
        env.pop("LAMF_DATA_DIR", None)
        args: list[str] = [
            "-m", "installer.windows.uninstall_helper",
            "/APP_DIR", str(exe_dir),
            "/DATA_DIR", str(data_dir),
        ]
        args.extend(argv[1:])
        return python, args, env

    args = ["-m", "lamf.cli"]

    if base == "lamf-control":
        args.extend(["serve", "--data-dir", str(data_dir)])

    # Append caller arguments, skipping the program name.
    args.extend(argv[1:])

    return python, args, env


def build() -> tuple[Path, Path, Path]:
    """Compile ``launcher.rs`` and copy the result to the three executables."""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    output = BUILD_DIR / "launcher.exe"

    subprocess.run(
        ["rustc", "-O", "--edition", "2021", "-o", str(output), str(SOURCE)],
        check=True,
    )

    lamf = BUILD_DIR / "lamf.exe"
    control = BUILD_DIR / "lamf-control.exe"
    uninstall = BUILD_DIR / "uninstall.exe"
    shutil.copy2(output, lamf)
    shutil.copy2(output, control)
    shutil.copy2(output, uninstall)
    return lamf, control, uninstall


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build LAMF Windows launchers")
    parser.add_argument(
        "--check", action="store_true", help="verify the Rust toolchain only"
    )
    args = parser.parse_args(argv)

    try:
        check_rustc()
    except (subprocess.CalledProcessError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.check:
        print(f"rustc {RUSTC_VERSION} OK")
        return 0

    try:
        lamf, control, uninstall = build()
    except Exception as exc:  # pragma: no cover - build failures surface as stderr
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"built {lamf}")
    print(f"built {control}")
    print(f"built {uninstall}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
