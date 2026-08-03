#!/usr/bin/env python3
"""Create an allowlist-only, privacy-safe LAMF issue report.

This helper intentionally does not accept a data directory and never scans the
filesystem, environment, logs, databases, vaults, exports, or memory content.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import re
import sys
from pathlib import Path


SCHEMA = "lamf-public-issue-report-1"
PROFILES = ("unspecified", "locked", "controlled", "trusted-local", "open-local")
MODES = ("unspecified", "core", "optimized")
HARNESSES = ("codex", "claude", "kimi", "grok", "openclaw", "hermes", "generic")
_PUBLIC_ATOM = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}\Z")
_VERSION = re.compile(r"[0-9][0-9A-Za-z.+-]{0,31}\Z")


def _public_atom(value: str) -> str:
    """Return a bounded public platform atom or a non-sensitive placeholder."""
    return value if _PUBLIC_ATOM.fullmatch(value) else "redacted"


def _lamf_version(package_root: Path) -> str:
    """Read only the public VERSION marker and reject unexpected contents."""
    try:
        value = (package_root / "VERSION").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return "unknown"
    return value if _VERSION.fullmatch(value) else "unknown"


def _dependency_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def build_report(*, package_root: Path, profile: str, mode: str,
                 harnesses: list[str]) -> dict:
    """Build a report solely from the explicit allowlist below."""
    system = platform.system()
    system = system if system in ("Windows", "Linux", "Darwin") else "Other"
    implementation = platform.python_implementation()
    implementation = implementation if implementation in ("CPython", "PyPy") else "Other"
    selected_harnesses = sorted(set(harnesses))
    return {
        "schema": SCHEMA,
        "lamf_version": _lamf_version(package_root),
        "platform": {
            "system": system,
            "release": _public_atom(platform.release()),
            "machine": _public_atom(platform.machine()),
        },
        "python": {
            "implementation": implementation,
            "version": ".".join(str(part) for part in sys.version_info[:3]),
            "supported": sys.version_info[:2] >= (3, 10),
        },
        "public_configuration": {
            "profile": profile,
            "mode": mode,
            "harnesses": selected_harnesses,
        },
        "sanitized_diagnostics": {
            "package_layout_present": (package_root / "runtime" / "lamf").is_dir(),
            "pyyaml_available": _dependency_available("yaml"),
            "pynacl_available": _dependency_available("nacl"),
        },
        "privacy": {
            "collection_policy": "allowlist-only",
            "data_directory_accessed": False,
            "personal_paths_included": False,
            "memory_content_included": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Print a privacy-safe, allowlist-only LAMF issue report as JSON."
    )
    parser.add_argument("--profile", choices=PROFILES, default="unspecified")
    parser.add_argument("--mode", choices=MODES, default="unspecified")
    parser.add_argument("--harness", action="append", choices=HARNESSES, default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    package_root = Path(__file__).resolve().parent.parent
    report = build_report(
        package_root=package_root,
        profile=args.profile,
        mode=args.mode,
        harnesses=args.harness,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
