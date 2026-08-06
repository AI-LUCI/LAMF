"""One-command orchestrator for the LAMF Windows installer.

The orchestrator coordinates acquisition, launcher compilation, payload
assembly, manifest generation, and Inno Setup compilation.  The final unsigned
development executable is written to ``dist/LAMF-Setup-x64.exe``.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from build_config import (  # noqa: E402
    CFFI_WHEEL_FILENAME,
    INNO_SETUP_FILENAME,
    INNO_SETUP_VERSION,
    PYCPARSER_WHEEL_FILENAME,
    BuildConfig,
    default_build_config,
)

DIST_DIR = ROOT.parent.parent / "dist"
PAYLOAD_DIR = DIST_DIR / "lamf-windows-payload"
FINAL_EXE = DIST_DIR / "LAMF-Setup-x64.exe"
SETUP_ISS = ROOT / "setup.iss"
BUILD_DIR = ROOT / "build"
CACHE_DIR = BUILD_DIR / "cache"


class BuildError(RuntimeError):
    """The installer build failed."""


def _check_rustc() -> None:
    """Ensure the pinned Rust toolchain is available."""
    import build_launcher
    build_launcher.check_rustc()


def _build_launchers() -> tuple[Path, Path]:
    """Compile the two native launcher executables."""
    import build_launcher
    return build_launcher.build()


def _acquire_inputs(cache_dir: Path, config: BuildConfig | None = None) -> dict[str, Path]:
    """Download and verify every pinned build input."""
    import acquire
    return acquire.acquire_all(cache_dir, config)


def _assemble_payload(
    cache_dir: Path,
    launcher_dir: Path,
    config: BuildConfig | None = None,
    optimization_pack_source: Path | None = None,
) -> Path:
    """Assemble the offline payload directory."""
    import payload
    config = config if config is not None else default_build_config()
    return payload.assemble_payload(
        output_dir=PAYLOAD_DIR,
        launcher_dir=launcher_dir,
        python_embed_zip=cache_dir / config.python_embed_filename,
        pyyaml_wheel=cache_dir / config.pyyaml_wheel_filename,
        pynacl_wheel=cache_dir / config.pynacl_wheel_filename,
        cffi_wheel=cache_dir / config.cffi_wheel_filename,
        pycparser_wheel=cache_dir / config.pycparser_wheel_filename,
        optimization_pack_source=optimization_pack_source,
    )


def _generate_manifest(payload_dir: Path) -> Path:
    """Generate the SHA-256 manifest for the payload."""
    import manifest
    return manifest.generate_manifest(payload_dir)


def _verify_payload(payload_dir: Path) -> None:
    """Run fatal payload verification gates (imports, init, manifest, allowlist)."""
    import verify_payload
    verify_payload.verify_payload(payload_dir)


def _find_iscc(cache_dir: Path) -> Path | None:
    """Return the path to ``iscc.exe`` if it is already available."""
    iscc = shutil.which("iscc.exe")
    if iscc:
        return Path(iscc)
    candidate = cache_dir / "innosetup" / "iscc.exe"
    if candidate.is_file():
        return candidate
    return None


def _install_inno_setup(cache_dir: Path, config: BuildConfig | None = None) -> Path:
    """Install the acquired Inno Setup compiler into a build-local directory."""
    config = config if config is not None else default_build_config()
    installer = cache_dir / config.inno_setup_filename
    if not installer.is_file():
        raise BuildError(f"Inno Setup installer not found: {installer}")
    install_dir = cache_dir / "innosetup"
    if install_dir.exists():
        shutil.rmtree(install_dir)
    install_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(installer),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/NOCANCEL",
        "/CURRENTUSER",
        f"/DIR={install_dir}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise BuildError(
            f"Inno Setup installer failed (exit {result.returncode}).\n"
            f"Command: {' '.join(cmd)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    iscc = install_dir / "iscc.exe"
    if not iscc.is_file():
        raise BuildError(f"iscc.exe not found after Inno Setup install: {iscc}")
    return iscc


def _compile_iss(iscc: Path, iss_file: Path, output_dir: Path) -> Path:
    """Compile the Inno Setup source into the final installer executable."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(iscc),
        f"/O{output_dir}",
        str(iss_file),
    ]
    subprocess.run(cmd, check=True)
    exe = output_dir / "LAMF-Setup-x64.exe"
    if not exe.is_file():
        raise BuildError(f"expected output not found after ISS compile: {exe}")
    return exe


def build_installer(
    *,
    cache_dir: Path | None = None,
    skip_iscc: bool = False,
    config: BuildConfig | None = None,
    optimization_pack_source: Path | None = None,
) -> Path:
    """Run the full build pipeline and return the output path.

    When *skip_iscc* is true, the pipeline stops after manifest generation and
    returns the payload directory instead of the final EXE.
    """
    cache_dir = Path(cache_dir) if cache_dir is not None else CACHE_DIR
    config = config if config is not None else default_build_config()

    print("[1/6] Acquiring pinned build inputs...")
    _acquire_inputs(cache_dir, config)

    print("[2/6] Building native launchers...")
    _check_rustc()
    launcher_dir = BUILD_DIR
    _build_launchers()

    print("[3/6] Assembling offline payload...")
    payload_dir = _assemble_payload(cache_dir, launcher_dir, config, optimization_pack_source)

    print("[4/6] Generating payload manifest...")
    _generate_manifest(payload_dir)

    print("[5/6] Verifying payload gates (imports, init, manifest, allowlist)...")
    _verify_payload(payload_dir)

    if skip_iscc:
        print("[6/6] Skipping Inno Setup compilation (--skip-iscc).")
        return payload_dir

    print("[6/6] Compiling Inno Setup installer...")
    iscc = _find_iscc(cache_dir)
    if iscc is None:
        iscc = _install_inno_setup(cache_dir, config)
    exe = _compile_iss(iscc, SETUP_ISS, DIST_DIR)
    print(f"Built unsigned installer: {exe}")
    return exe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the LAMF Windows installer executable."
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=CACHE_DIR,
        help="directory for downloaded build inputs (default: build/cache)",
    )
    parser.add_argument(
        "--skip-iscc", action="store_true",
        help="stop after payload assembly; do not compile the Inno Setup EXE",
    )
    parser.add_argument(
        "--payload-only", action="store_true",
        help="alias for --skip-iscc",
    )
    parser.add_argument(
        "--optimization-pack-source", type=Path, default=None,
        help="path to the local LAMF-Optimizations checkout "
             "(default: LAMF_OPTIMIZATION_PACK_SOURCE env var or "
             "a sibling LAMF-Optimizations directory)",
    )
    args = parser.parse_args(argv)

    try:
        output = build_installer(
            cache_dir=args.cache_dir,
            skip_iscc=args.skip_iscc or args.payload_only,
            optimization_pack_source=args.optimization_pack_source,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
