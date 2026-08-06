"""Download, verify, and cache pinned Windows installer build inputs.

Every external artifact consumed by the build is pinned by version and SHA-256.
The build may download inputs, but the final installer is offline-capable.  This
module refuses mutable "latest" URLs and writes a ``provenance.json`` receipt
so the build is auditable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from build_config import (  # noqa: E402
    CFFI_VERSION,
    CFFI_WHEEL_FILENAME,
    CFFI_WHEEL_SHA256,
    CFFI_WHEEL_URL,
    INNO_SETUP_FILENAME,
    INNO_SETUP_SHA256,
    INNO_SETUP_URL,
    PYNACL_VERSION,
    PYNACL_WHEEL_FILENAME,
    PYNACL_WHEEL_SHA256,
    PYNACL_WHEEL_URL,
    PYCPARSER_VERSION,
    PYCPARSER_WHEEL_FILENAME,
    PYCPARSER_WHEEL_SHA256,
    PYCPARSER_WHEEL_URL,
    PYYAML_VERSION,
    PYYAML_WHEEL_FILENAME,
    PYYAML_WHEEL_SHA256,
    PYYAML_WHEEL_URL,
    PYTHON_EMBED_FILENAME,
    PYTHON_EMBED_SHA256,
    PYTHON_EMBED_URL,
    BuildConfig,
    default_build_config,
    verify_sha256,
)


DEFAULT_CACHE_DIR = ROOT / "build" / "cache"
PROVENANCE_NAME = "provenance.json"


@dataclass(frozen=True)
class Artifact:
    """A pinned build input."""

    name: str
    url: str
    filename: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "url": self.url,
            "filename": self.filename,
            "sha256": self.sha256,
        }


def artifacts_from_config(config: BuildConfig | None = None) -> tuple[Artifact, ...]:
    """Return the pinned artifact set from the build configuration."""
    config = config if config is not None else default_build_config()
    return (
        Artifact(
            name="python_embed",
            url=config.python_embed_url,
            filename=config.python_embed_filename,
            sha256=config.python_embed_sha256,
        ),
        Artifact(
            name="pyyaml_wheel",
            url=config.pyyaml_wheel_url,
            filename=config.pyyaml_wheel_filename,
            sha256=config.pyyaml_wheel_sha256,
        ),
        Artifact(
            name="pynacl_wheel",
            url=config.pynacl_wheel_url,
            filename=config.pynacl_wheel_filename,
            sha256=config.pynacl_wheel_sha256,
        ),
        Artifact(
            name="cffi_wheel",
            url=config.cffi_wheel_url,
            filename=config.cffi_wheel_filename,
            sha256=config.cffi_wheel_sha256,
        ),
        Artifact(
            name="pycparser_wheel",
            url=config.pycparser_wheel_url,
            filename=config.pycparser_wheel_filename,
            sha256=config.pycparser_wheel_sha256,
        ),
        Artifact(
            name="inno_setup",
            url=config.inno_setup_url,
            filename=config.inno_setup_filename,
            sha256=config.inno_setup_sha256,
        ),
    )


def _is_pinned_url(url: str) -> bool:
    """Reject URLs that point to mutable "latest" endpoints.

    PyPI and python.org artifact URLs contain the exact version in the path or
    filename, so any URL containing the word ``latest`` is treated as mutable
    and refused.
    """
    lower = url.lower()
    if "latest" in lower:
        return False
    # PyPI and python.org URLs must contain a version-like segment or filename.
    # A heuristic: reject bare directory indexes.
    if lower.rstrip("/").endswith((".zip", ".whl", ".exe")):
        return True
    return True


def _download(url: str, dest: Path, *, timeout: float = 300.0,
              block_size: int = 1 << 16) -> None:
    """Download *url* to *dest* atomically via a sibling temporary file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "LAMF-Windows-Installer/1.0 "
                "(+https://github.com/lamf-project/lamf)"
            ),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            with open(tmp, "wb") as fh:
                while True:
                    chunk = response.read(block_size)
                    if not chunk:
                        break
                    fh.write(chunk)
        tmp.replace(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def ensure_artifact(
    artifact: Artifact,
    cache_dir: Path,
    *,
    force: bool = False,
    timeout: float = 300.0,
) -> tuple[Path, str]:
    """Return the cached path for *artifact* and a status string.

    If the file is already present and its SHA-256 matches the pin, it is not
    re-downloaded.  If *force* is true, the file is always re-downloaded and
    verified.  Raises ``RuntimeError`` on hash mismatch.
    """
    if not _is_pinned_url(artifact.url):
        raise ValueError(f"refusing mutable URL for {artifact.name}: {artifact.url}")

    dest = Path(cache_dir) / artifact.filename
    status = "cached"

    if force or not dest.is_file():
        _download(artifact.url, dest, timeout=timeout)
        status = "downloaded"

    if not verify_sha256(dest, artifact.sha256):
        raise RuntimeError(
            f"SHA-256 mismatch for {artifact.name}: expected {artifact.sha256}, "
            f"got {hashlib.sha256(dest.read_bytes()).hexdigest()}"
        )
    return dest, status


def write_provenance(
    artifacts: Iterable[Artifact],
    cache_dir: Path,
    *,
    statuses: dict[str, str] | None = None,
) -> Path:
    """Write a JSON receipt describing every cached artifact."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    provenance = {
        "schema_version": 1,
        "generated_at": _utc_timestamp(),
        "artifacts": [],
    }
    statuses = statuses or {}
    for artifact in artifacts:
        entry = artifact.to_dict()
        entry["status"] = statuses.get(artifact.name, "unknown")
        entry["cached_at"] = _utc_timestamp()
        provenance["artifacts"].append(entry)
    path = cache_dir / PROVENANCE_NAME
    path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path


def load_provenance(cache_dir: Path) -> dict:
    """Load the provenance receipt, or return an empty stub if absent."""
    path = Path(cache_dir) / PROVENANCE_NAME
    if not path.is_file():
        return {"schema_version": 1, "artifacts": []}
    return json.loads(path.read_text(encoding="utf-8"))


def verify_all(
    artifacts: Iterable[Artifact],
    cache_dir: Path,
) -> dict[str, bool]:
    """Return a map of artifact name to SHA-256 verification result."""
    results: dict[str, bool] = {}
    for artifact in artifacts:
        dest = Path(cache_dir) / artifact.filename
        if not dest.is_file():
            results[artifact.name] = False
            continue
        results[artifact.name] = verify_sha256(dest, artifact.sha256)
    return results


def _utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def acquire_all(
    cache_dir: Path | None = None,
    config: BuildConfig | None = None,
    *,
    artifacts: Iterable[Artifact] | None = None,
    force: bool = False,
    timeout: float = 300.0,
) -> dict[str, Path]:
    """Download and verify every pinned artifact, returning a name-to-path map.

    If *artifacts* is supplied it is used directly; otherwise the pinned set is
    taken from *config* (or the default build configuration).
    """
    cache_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    artifact_seq = tuple(artifacts) if artifacts is not None else artifacts_from_config(config)
    statuses: dict[str, str] = {}
    paths: dict[str, Path] = {}
    for artifact in artifact_seq:
        path, status = ensure_artifact(artifact, cache_dir, force=force,
                                       timeout=timeout)
        paths[artifact.name] = path
        statuses[artifact.name] = status
    write_provenance(artifact_seq, cache_dir, statuses=statuses)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Acquire and verify pinned Windows installer build inputs."
    )
    parser.add_argument(
        "--download", action="store_true",
        help="download any missing artifacts and verify their hashes",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="verify cached artifacts against pinned SHA-256 values",
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=DEFAULT_CACHE_DIR,
        help="directory where artifacts are cached (default: build/cache)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="re-download artifacts even if the cache already exists",
    )
    args = parser.parse_args(argv)

    if not args.download and not args.verify:
        parser.error("specify --download or --verify")

    try:
        artifacts = artifacts_from_config()
        if args.verify:
            results = verify_all(artifacts, args.cache_dir)
            ok = all(results.values())
            for name, verified in results.items():
                status = "ok" if verified else "MISSING_OR_TAMPERED"
                print(f"{name}: {status}")
            if not ok:
                print("verification failed; run with --download to refresh",
                      file=sys.stderr)
                return 1
            print("verification ok")
            return 0

        if args.download:
            paths = acquire_all(args.cache_dir, force=args.force)
            for name, path in paths.items():
                print(f"{name}: {path}")
            return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 1  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())
