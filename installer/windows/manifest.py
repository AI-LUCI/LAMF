"""Reproducible SHA-256 manifest for the LAMF Windows installer payload.

A manifest lists every file in a directory tree in deterministic, sorted order.
It is generated at build time and verified at install time so that a tampered
or incomplete payload is rejected before any code is run.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Iterable


DEFAULT_MANIFEST_NAME = "manifest.sha256"


def _hash_file(path: Path, block_size: int = 1 << 20) -> str:
    """Return the lowercase SHA-256 hex digest of *path*."""
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(block_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _iter_files(root: Path) -> Iterable[Path]:
    """Yield every regular file under *root*, sorted by POSIX relative path."""
    files = [p for p in root.rglob("*") if p.is_file()]
    files.sort(key=lambda p: p.relative_to(root).as_posix())
    return files


def generate_manifest(
    root: Path,
    output: Path | None = None,
    *,
    manifest_name: str = DEFAULT_MANIFEST_NAME,
) -> Path:
    """Write a SHA-256 manifest for *root* and return the manifest path.

    The manifest contains one line per regular file in deterministic sorted
    order, formatted as ``<sha256>  <relative/path>``. The manifest file itself
    is never included in its own listing.
    """
    root = Path(root).resolve()
    if output is None:
        output = root / manifest_name
    else:
        output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    for path in _iter_files(root):
        if path == output:
            continue
        rel = path.relative_to(root).as_posix()
        digest = _hash_file(path)
        lines.append(f"{digest}  {rel}")

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def verify_manifest(
    root: Path,
    manifest_path: Path | None = None,
    *,
    manifest_name: str = DEFAULT_MANIFEST_NAME,
) -> dict[str, list[str] | bool]:
    """Verify the files under *root* against a previously generated manifest.

    Returns a dictionary with keys:
    - ``ok``: True if no mismatches, missing files, or unreadable entries.
    - ``missing``: relative paths listed in the manifest but absent on disk.
    - ``mismatched``: relative paths whose digest differs from the manifest.
    - ``extra``: relative paths present on disk but not listed in the manifest.
    - ``errors``: non-existent manifest or malformed lines.
    """
    root = Path(root).resolve()
    if manifest_path is None:
        manifest_path = root / manifest_name
    else:
        manifest_path = Path(manifest_path).resolve()

    result: dict[str, list[str] | bool] = {
        "ok": True,
        "missing": [],
        "mismatched": [],
        "extra": [],
        "errors": [],
    }

    if not manifest_path.is_file():
        result["ok"] = False
        result["errors"].append(f"manifest not found: {manifest_path}")
        return result

    expected: dict[str, str] = {}
    for lineno, line in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            result["ok"] = False
            result["errors"].append(f"malformed line {lineno}: {line!r}")
            continue
        digest, rel = parts[0], parts[1]
        expected[rel] = digest

    if result["errors"]:
        result["ok"] = False

    actual_files = {p.relative_to(root).as_posix() for p in _iter_files(root) if p != manifest_path}
    expected_files = set(expected)

    for rel in sorted(expected):
        file_path = root / rel
        if not file_path.is_file():
            result["ok"] = False
            result["missing"].append(rel)
            continue
        if _hash_file(file_path) != expected[rel]:
            result["ok"] = False
            result["mismatched"].append(rel)

    for rel in sorted(actual_files - expected_files):
        result["extra"].append(rel)

    return result


def _main(argv: list[str] | None = None) -> int:
    """Command-line entry point for manifest generation and verification."""
    parser = argparse.ArgumentParser(
        description="Generate or verify a SHA-256 manifest for a directory tree."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true", help="Generate a manifest for a directory.")
    group.add_argument("--verify", action="store_true", help="Verify files against a manifest.")
    parser.add_argument("directory", type=Path, help="Root directory to scan or verify.")
    parser.add_argument(
        "target",
        type=Path,
        nargs="?",
        help=(
            "With --generate, the optional manifest output path "
            "(default: <directory>/manifest.sha256). "
            "With --verify, the optional manifest path."
        ),
    )

    args = parser.parse_args(argv)

    if args.generate:
        out = generate_manifest(args.directory, args.target)
        print(out)
        return 0

    if args.verify:
        result = verify_manifest(args.directory, args.target)
        if result["ok"]:
            print("ok")
            return 0
        for category in ("missing", "mismatched", "extra", "errors"):
            items = result.get(category, [])
            for item in items:
                print(f"{category}: {item}")
        return 1

    return 2  # pragma: no cover - argparse prevents this


if __name__ == "__main__":
    raise SystemExit(_main())
