"""Pinned build inputs and requirement IDs for the LAMF Windows 11 installer.

Every external artifact consumed by the build is pinned by version and SHA-256.
The installer itself is offline-capable: these constants are used to verify the
payloads that are bundled during the build, never to fetch mutable "latest" URLs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Requirement IDs from docs/WINDOWS_INSTALLER_ARCHITECTURE.md
# ---------------------------------------------------------------------------
BUILD_REQUIREMENTS: dict[str, str] = {
    "R-WIN-01": "All build inputs are pinned by version and SHA-256.",
    "R-WIN-02": "The final installer contains a reproducible payload manifest.",
    "R-WIN-03": "The embedded Python runtime is private and requires no system Python.",
    "R-WIN-04": "Application path and data path are separate and distinct.",
    "R-WIN-05": "Data path is rejected when it lies inside a Git worktree.",
    "R-WIN-06": "Uninstall preserves private memory unless explicitly removed.",
}


# ---------------------------------------------------------------------------
# Pinned third-party artifacts
# ---------------------------------------------------------------------------
#: CPython Windows x64 embeddable package.
#: <https://www.python.org/downloads/windows/>
PYTHON_EMBED_VERSION = "3.11.9"
PYTHON_EMBED_FILENAME = f"python-{PYTHON_EMBED_VERSION}-embed-amd64.zip"
PYTHON_EMBED_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_EMBED_VERSION}/{PYTHON_EMBED_FILENAME}"
)
PYTHON_EMBED_SHA256 = (
    "009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b"
)

#: PyYAML wheel for the same CPython ABI.
#: <https://pypi.org/project/PyYAML/6.0.2/>
PYYAML_VERSION = "6.0.2"
PYYAML_WHEEL_FILENAME = f"PyYAML-{PYYAML_VERSION}-cp311-cp311-win_amd64.whl"
PYYAML_WHEEL_URL = (
    "https://files.pythonhosted.org/packages/ed/23/8da0bbe2ab9dcdd11f4f4557ccaf95c10b9811b13ecced089d43ce59c3c8/"
    + PYYAML_WHEEL_FILENAME
)
PYYAML_WHEEL_SHA256 = (
    "e10ce637b18caea04431ce14fabcf5c64a1c61ec9c56b071a4b7ca131ca52d44"
)

#: PyNaCl wheel (abi3) for the same Windows x64 target.
#: <https://pypi.org/project/PyNaCl/1.5.0/>
PYNACL_VERSION = "1.5.0"
PYNACL_WHEEL_FILENAME = f"PyNaCl-{PYNACL_VERSION}-cp36-abi3-win_amd64.whl"
PYNACL_WHEEL_URL = (
    "https://files.pythonhosted.org/packages/5e/22/d3db169895faaf3e2eda892f005f433a62db2decbcfbc2f61e6517adfa87/"
    + PYNACL_WHEEL_FILENAME
)
PYNACL_WHEEL_SHA256 = (
    "20f42270d27e1b6a29f54032090b972d97f0a1b0948cc52392041ef7831fee93"
)

#: CFFI binary wheel required by PyNaCl at import time on CPython 3.11 Windows x64.
#: <https://pypi.org/project/cffi/1.17.1/>
CFFI_VERSION = "1.17.1"
CFFI_WHEEL_FILENAME = f"cffi-{CFFI_VERSION}-cp311-cp311-win_amd64.whl"
CFFI_WHEEL_URL = (
    "https://files.pythonhosted.org/packages/3d/97/50228be003bb2802627d28ec0627837ac0bf35c90cf769812056f235b2d1/"
    + CFFI_WHEEL_FILENAME
)
CFFI_WHEEL_SHA256 = (
    "caaf0640ef5f5517f49bc275eca1406b0ffa6aa184892812030f04c2abf589a0"
)

#: pycparser pure-Python wheel required by CFFI at import time.
#: <https://pypi.org/project/pycparser/2.22/>
PYCPARSER_VERSION = "2.22"
PYCPARSER_WHEEL_FILENAME = f"pycparser-{PYCPARSER_VERSION}-py3-none-any.whl"
PYCPARSER_WHEEL_URL = (
    "https://files.pythonhosted.org/packages/13/a3/a812df4e2dd5696d1f351d58b8fe16a405b234ad2886a0dab9183fb78109/"
    + PYCPARSER_WHEEL_FILENAME
)
PYCPARSER_WHEEL_SHA256 = (
    "c3702b6d3dd8c7abc1afa565d7e63d53a1d0bd86cdc24edd75470f4de499cfcc"
)

#: Inno Setup compiler installer (x86 installer contains the x64-capable compiler).
#: <https://jrsoftware.org/isinfo.php>
INNO_SETUP_VERSION = "6.7.3"
INNO_SETUP_FILENAME = f"innosetup-{INNO_SETUP_VERSION}.exe"
INNO_SETUP_URL = (
    f"https://github.com/jrsoftware/issrc/releases/download/"
    f"is-{INNO_SETUP_VERSION.replace('.', '_')}/{INNO_SETUP_FILENAME}"
)
INNO_SETUP_SHA256 = (
    "9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732"
)

#: Pinned LAMF Optimizations pack commit.
#: Sourced from a local release checkout configured at build time via
#: ``--optimization-pack-source`` or the ``LAMF_OPTIMIZATION_PACK_SOURCE``
#: environment variable (commit e64160711f4ef3825c61ffd0e750aedc3260f29d,
#: tag v1.0.0, date 2026-08-02). The build copies only this pinned snapshot;
#: it never fetches a mutable "latest" ref.
OPTIMIZATION_PACK_COMMIT = "e64160711f4ef3825c61ffd0e750aedc3260f29d"
OPTIMIZATION_PACK_TAG = "v1.0.0"
OPTIMIZATION_PACK_DATE = "2026-08-02"

#: Pinned Rust toolchain version used to compile the native launchers.
RUSTC_VERSION = "1.95.0"


# ---------------------------------------------------------------------------
# Build configuration dataclass
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BuildConfig:
    """Immutable view of the artifacts required to build the Windows installer."""

    python_version: str = PYTHON_EMBED_VERSION
    python_embed_url: str = PYTHON_EMBED_URL
    python_embed_filename: str = PYTHON_EMBED_FILENAME
    python_embed_sha256: str = PYTHON_EMBED_SHA256

    pyyaml_version: str = PYYAML_VERSION
    pyyaml_wheel_url: str = PYYAML_WHEEL_URL
    pyyaml_wheel_filename: str = PYYAML_WHEEL_FILENAME
    pyyaml_wheel_sha256: str = PYYAML_WHEEL_SHA256

    pynacl_version: str = PYNACL_VERSION
    pynacl_wheel_url: str = PYNACL_WHEEL_URL
    pynacl_wheel_filename: str = PYNACL_WHEEL_FILENAME
    pynacl_wheel_sha256: str = PYNACL_WHEEL_SHA256

    cffi_version: str = CFFI_VERSION
    cffi_wheel_url: str = CFFI_WHEEL_URL
    cffi_wheel_filename: str = CFFI_WHEEL_FILENAME
    cffi_wheel_sha256: str = CFFI_WHEEL_SHA256

    pycparser_version: str = PYCPARSER_VERSION
    pycparser_wheel_url: str = PYCPARSER_WHEEL_URL
    pycparser_wheel_filename: str = PYCPARSER_WHEEL_FILENAME
    pycparser_wheel_sha256: str = PYCPARSER_WHEEL_SHA256

    inno_setup_version: str = INNO_SETUP_VERSION
    inno_setup_url: str = INNO_SETUP_URL
    inno_setup_filename: str = INNO_SETUP_FILENAME
    inno_setup_sha256: str = INNO_SETUP_SHA256

    rustc_version: str = RUSTC_VERSION

    optimization_pack_commit: str = OPTIMIZATION_PACK_COMMIT


def default_build_config() -> BuildConfig:
    """Return the authoritative pinned build configuration."""
    return BuildConfig()


def verify_sha256(path: Path | str, expected_hex: str, *, block_size: int = 1 << 20) -> bool:
    """Return True if the SHA-256 hex digest of *path* matches *expected_hex*.

    The comparison is case-insensitive. The file is read in chunks to keep the
    memory footprint constant regardless of file size.
    """
    hasher = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(block_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest().lower() == expected_hex.lower()
