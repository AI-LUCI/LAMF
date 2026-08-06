"""Tests for installer/windows/payload.py.

These tests assemble a minimal payload with synthetic build inputs and verify
layout, manifest, and packaged-mode registration behavior.
"""

from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from payload import (  # noqa: E402
    FORBIDDEN_INSTALLER_DIRS,
    FORBIDDEN_INSTALLER_SUFFIXES,
    INSTALLER_WINDOWS_ALLOWED_FILES,
    PayloadError,
    _default_optimization_pack_source,
    _python_pth_name,
    assemble_payload,
)


def _write_zip(root: Path, dest: Path, members: dict[str, bytes]) -> None:
    """Create a zip at *dest* containing *members* relative to *root*."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)


def _make_python_embed(zip_path: Path, version: str = "3.11.9") -> None:
    base = _python_pth_name(version)
    _write_zip(
        zip_path,
        zip_path,
        {
            f"{base}.zip": b"",
            f"{base}._pth": (
                f"{base}.zip\n.\n# comment\n".encode("utf-8")
            ),
            "python.exe": b"",
            "pythonw.exe": b"",
            "Lib/site-packages/README.txt": b"site-packages\n",
        },
    )


def _make_wheel(zip_path: Path, package_name: str) -> None:
    _write_zip(
        zip_path,
        zip_path,
        {
            f"{package_name}/__init__.py": b"",
            f"{package_name}-1.0.0.dist-info/METADATA": b"Name: test\n",
        },
    )


def _make_runtime(src: Path) -> None:
    (src / "lamf").mkdir(parents=True)
    (src / "lamf" / "__init__.py").write_text('__version__ = "2.0.0"\n',
                                              encoding="utf-8")
    (src / "lamf_mcp.py").write_text("", encoding="utf-8")
    (src / "requirements.txt").write_text("pyyaml\npynacl\n", encoding="utf-8")


def _make_security_profiles(project_root: Path) -> None:
    profiles = project_root / "02_SECURITY" / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    (profiles / "controlled.yaml").write_text(
        "profile: controlled\nversion: 1\n", encoding="utf-8"
    )


def _make_storage_schema(project_root: Path) -> None:
    schema = project_root / "04_STORAGE" / "SCHEMA.sql"
    schema.parent.mkdir(parents=True, exist_ok=True)
    (schema).write_text(
        "CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY);\n",
        encoding="utf-8",
    )


def _make_optimization_pack(src: Path) -> None:
    (src / "optimizations" / "modules" / "minimal-solution").mkdir(parents=True)
    (src / "optimizations" / "modules" / "minimal-solution" / "module.json").write_text(
        json.dumps({"id": "minimal-solution", "version": "1", "default_enabled": True,
                    "instruction_file": "instruction.md"}),
        encoding="utf-8",
    )
    (src / "optimizations" / "modules" / "minimal-solution" / "instruction.md").write_text(
        "test instruction", encoding="utf-8")
    (src / "LICENSE").write_text("MIT", encoding="utf-8")
    (src / "Credit.md").write_text("credits", encoding="utf-8")
    # Initialize a real git repo so _verify_pack_commit can read HEAD.
    import subprocess
    subprocess.run(["git", "init", str(src)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(src), "config", "user.email", "test@example.com"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(src), "config", "user.name", "Test"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(src), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(src), "commit", "-m", "test"],
                   check=True, capture_output=True)
    # Force HEAD to the pinned commit so the test is deterministic.
    head_file = src / ".git" / "HEAD"
    head_file.write_text("e64160711f4ef3825c61ffd0e750aedc3260f29d\n",
                         encoding="utf-8")


def _make_launchers(src: Path) -> None:
    src.mkdir(parents=True, exist_ok=True)
    for name in ("lamf.exe", "lamf-control.exe", "uninstall.exe"):
        (src / name).write_bytes(b"exe")


def test_assemble_payload_creates_expected_layout():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        cache = td / "cache"
        cache.mkdir()
        python_zip = cache / "python-3.11.9-embed-amd64.zip"
        pyyaml_wheel = cache / "PyYAML-6.0.2-cp311-cp311-win_amd64.whl"
        pynacl_wheel = cache / "PyNaCl-1.5.0-cp36-abi3-win_amd64.whl"
        cffi_wheel = cache / "cffi-1.17.1-cp311-cp311-win_amd64.whl"
        pycparser_wheel = cache / "pycparser-2.22-py3-none-any.whl"
        _make_python_embed(python_zip)
        _make_wheel(pyyaml_wheel, "yaml")
        _make_wheel(pynacl_wheel, "nacl")
        _make_wheel(cffi_wheel, "cffi")
        _make_wheel(pycparser_wheel, "pycparser")

        launcher_dir = td / "launchers"
        _make_launchers(launcher_dir)

        runtime_src = td / "runtime"
        _make_runtime(runtime_src)

        opt_src = td / "optimizations"
        _make_optimization_pack(opt_src)

        project_root = td / "project"
        project_root.mkdir()
        _make_security_profiles(project_root)
        _make_storage_schema(project_root)
        for name in ("LICENSE", "CHANGELOG.md", "Credit.md"):
            (project_root / name).write_text(name, encoding="utf-8")

        output = td / "payload"
        result = assemble_payload(
            output_dir=output,
            launcher_dir=launcher_dir,
            python_embed_zip=python_zip,
            pyyaml_wheel=pyyaml_wheel,
            pynacl_wheel=pynacl_wheel,
            cffi_wheel=cffi_wheel,
            pycparser_wheel=pycparser_wheel,
            runtime_source=runtime_src,
            optimization_pack_source=opt_src,
            project_root=project_root,
        )
        assert result == output
        assert (output / "lamf.exe").is_file()
        assert (output / "lamf-control.exe").is_file()
        assert (output / "uninstall.exe").is_file()
        assert (output / "python" / "python.exe").is_file()
        assert (output / "python" / "pythonw.exe").is_file()
        assert (output / "app" / "lamf" / "__init__.py").is_file()
        assert (output / "app" / "lamf_mcp.py").is_file()
        assert (output / "app" / "installer" / "windows" / "__init__.py").is_file()
        assert (output / "post_install.py").is_file()
        assert (output / "02_SECURITY" / "profiles" / "controlled.yaml").is_file()
        assert (output / "04_STORAGE" / "SCHEMA.sql").is_file()
        assert (output / "optimizations" / "optimizations" / "modules" / "minimal-solution" / "module.json").is_file()
        assert (output / "licenses" / "LICENSE").is_file()
        assert (output / "licenses" / "optimizations" / "LICENSE").is_file()
        assert (output / "version.json").is_file()
        assert (output / "manifest.sha256").is_file()

        # Manifest should verify.
        from manifest import verify_manifest
        check = verify_manifest(output)
        assert check["ok"] is True, check

        # Version metadata should not leak build paths.
        version_text = (output / "version.json").read_text(encoding="utf-8")
        version = json.loads(version_text)
        assert version["lamf_version"] == "2.0.0"
        assert version["optimization_pack_commit"] == "e64160711f4ef3825c61ffd0e750aedc3260f29d"
        assert "E:/LAMF-Optimizations-GitHub" not in version_text

        # Only the allowlisted installer helper modules may be present.
        installer_dir = output / "app" / "installer" / "windows"
        found = {p.relative_to(installer_dir).as_posix()
                 for p in installer_dir.rglob("*") if p.is_file()}
        assert found == set(INSTALLER_WINDOWS_ALLOWED_FILES), found

        # No forbidden directories or suffixes inside the installer tree.
        for rel in found:
            for part in rel.split("/"):
                assert part not in FORBIDDEN_INSTALLER_DIRS, rel
            assert not rel.lower().endswith(FORBIDDEN_INSTALLER_SUFFIXES), rel


def test_python_pth_name_uses_major_minor_only():
    assert _python_pth_name("3.11.9") == "python311"
    assert _python_pth_name("3.13.0") == "python313"


class TestDefaultOptimizationPackSource:
    def test_uses_environment_variable(self, monkeypatch, tmp_path):
        env_dir = tmp_path / "from-env"
        env_dir.mkdir()
        monkeypatch.setenv("LAMF_OPTIMIZATION_PACK_SOURCE", str(env_dir))
        assert _default_optimization_pack_source() == env_dir

    def test_uses_sibling_checkout(self, tmp_path, monkeypatch):
        # Simulate a sibling LAMF-Optimizations checkout by monkeypatching the
        # module constant directly.
        sibling = tmp_path / "LAMF-Optimizations"
        sibling.mkdir()
        import payload
        monkeypatch.setattr(payload, "DEFAULT_OPTIMIZATION_PACK_SIBLING", sibling)
        monkeypatch.delenv("LAMF_OPTIMIZATION_PACK_SOURCE", raising=False)
        assert _default_optimization_pack_source() == sibling

    def test_fails_with_clear_message_when_unconfigured(self, monkeypatch):
        import payload
        monkeypatch.delenv("LAMF_OPTIMIZATION_PACK_SOURCE", raising=False)
        monkeypatch.setattr(
            payload, "DEFAULT_OPTIMIZATION_PACK_SIBLING", Path("/nonexistent/LAMF-Optimizations")
        )
        with pytest.raises(PayloadError, match="Optimization pack source not configured"):
            _default_optimization_pack_source()

    def test_environment_variable_overrides_sibling(self, monkeypatch, tmp_path):
        env_dir = tmp_path / "from-env"
        env_dir.mkdir()
        sibling = tmp_path / "LAMF-Optimizations"
        sibling.mkdir()
        monkeypatch.setenv("LAMF_OPTIMIZATION_PACK_SOURCE", str(env_dir))
        import payload
        monkeypatch.setattr(payload, "DEFAULT_OPTIMIZATION_PACK_SIBLING", sibling)
        assert _default_optimization_pack_source() == env_dir


def test_missing_launcher_raises():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        launcher_dir = td / "launchers"
        launcher_dir.mkdir()
        (launcher_dir / "lamf.exe").write_bytes(b"x")
        (launcher_dir / "lamf-control.exe").write_bytes(b"x")
        # uninstall.exe missing
        runtime_src = td / "runtime"
        _make_runtime(runtime_src)
        opt_src = td / "opt"
        _make_optimization_pack(opt_src)
        _make_security_profiles(td)
        _make_storage_schema(td)
        with tempfile.TemporaryDirectory() as cache_td:
            cache = Path(cache_td)
            _make_python_embed(cache / "python-3.11.9-embed-amd64.zip")
            _make_wheel(cache / "PyYAML-6.0.2-cp311-cp311-win_amd64.whl", "yaml")
            _make_wheel(cache / "PyNaCl-1.5.0-cp36-abi3-win_amd64.whl", "nacl")
            _make_wheel(cache / "cffi-1.17.1-cp311-cp311-win_amd64.whl", "cffi")
            _make_wheel(cache / "pycparser-2.22-py3-none-any.whl", "pycparser")
            try:
                assemble_payload(
                    output_dir=td / "out",
                    launcher_dir=launcher_dir,
                    python_embed_zip=cache / "python-3.11.9-embed-amd64.zip",
                    pyyaml_wheel=cache / "PyYAML-6.0.2-cp311-cp311-win_amd64.whl",
                    pynacl_wheel=cache / "PyNaCl-1.5.0-cp36-abi3-win_amd64.whl",
                    cffi_wheel=cache / "cffi-1.17.1-cp311-cp311-win_amd64.whl",
                    pycparser_wheel=cache / "pycparser-2.22-py3-none-any.whl",
                    runtime_source=runtime_src,
                    optimization_pack_source=opt_src,
                    project_root=td,
                )
            except PayloadError as exc:
                assert "uninstall.exe" in str(exc)
            else:
                raise AssertionError("expected PayloadError")
