"""Integration test that builds the real payload and runs every verification gate.

This test exercises the same path as the release build (up to Inno Setup
compilation) and fails fatally if any payload gate fails:

* embedded Python imports ``yaml`` and ``nacl.bindings``;
* ``lamf init`` succeeds using only the packaged runtime;
* the payload manifest verifies;
* ``app/installer/windows`` contains only the allowlisted helper modules.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_config  # noqa: E402
import build_installer  # noqa: E402


def _make_optimization_pack(src: Path) -> None:
    """Create a minimal fake optimization pack checkout for the build pipeline.

    The pack needs a git directory and a HEAD matching the pinned commit so
    ``payload._verify_pack_commit`` succeeds.  Content is kept minimal because
    the integration test only verifies packaging gates, not optimization logic.
    """
    (src / "optimizations" / "modules" / "minimal-solution").mkdir(parents=True)
    (src / "optimizations" / "modules" / "minimal-solution" / "module.json").write_text(
        '{"id": "minimal-solution", "version": "1"}', encoding="utf-8"
    )
    (src / "LICENSE").write_text("MIT", encoding="utf-8")
    (src / "Credit.md").write_text("credits", encoding="utf-8")
    subprocess.run(["git", "init", str(src)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(src), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(src), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "-C", str(src), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(src), "commit", "-m", "test"],
        check=True,
        capture_output=True,
    )
    (src / ".git" / "HEAD").write_text(
        f"{build_config.OPTIMIZATION_PACK_COMMIT}\n", encoding="utf-8"
    )


def test_full_payload_build_passes_verification() -> None:
    """Run the full build pipeline through payload verification."""
    with tempfile.TemporaryDirectory() as td:
        opt_src = Path(td) / "optimizations"
        _make_optimization_pack(opt_src)
        payload_dir = build_installer.build_installer(
            skip_iscc=True, optimization_pack_source=opt_src
        )
    assert payload_dir.is_dir()
    assert (payload_dir / "manifest.sha256").is_file()
    assert (payload_dir / "python" / "python.exe").is_file()
    assert (payload_dir / "app" / "lamf" / "__init__.py").is_file()
