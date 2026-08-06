"""Tests for installer/windows/install_state.py."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from ..install_state import (
    InstallState,
    InstallStateError,
    check_free_space,
    new_install_state,
)


@pytest.fixture
def tmp_paths():
    """Yield a temporary application and data directory pair."""
    with tempfile.TemporaryDirectory() as td:
        app = Path(td) / "app"
        data = Path(td) / "data"
        app.mkdir()
        data.mkdir()
        yield app, data


def make_valid_dict(app_dir: Path, data_dir: Path) -> dict:
    return {
        "schema_version": 1,
        "version": "1.2.3",
        "app_dir": str(app_dir),
        "data_dir": str(data_dir),
        "profile": "controlled",
        "modules": ["minimal-solution"],
        "harnesses": ["kimi"],
        "optimizations_enabled": True,
    }


class TestInstallStateRoundTrip:
    def test_load_save_round_trip(self, tmp_paths):
        app, data = tmp_paths
        state = new_install_state(
            version="1.2.3",
            app_dir=app,
            data_dir=data,
            profile="controlled",
            modules=["minimal-solution"],
            harnesses=["kimi"],
            optimizations_enabled=True,
        )
        path = app / "install-state.json"
        state.save(path)
        loaded = InstallState.load(path)
        assert loaded.schema_version == 1
        assert loaded.version == "1.2.3"
        assert loaded.app_dir == app
        assert loaded.data_dir == data
        assert loaded.profile == "controlled"
        assert loaded.modules == ["minimal-solution"]
        assert loaded.harnesses == ["kimi"]
        assert loaded.optimizations_enabled is True

    def test_save_is_deterministic(self, tmp_paths):
        app, data = tmp_paths
        state = new_install_state("0.0.1", app, data)
        path = app / "install-state.json"
        state.save(path)
        first = path.read_text(encoding="utf-8")
        state.save(path)
        second = path.read_text(encoding="utf-8")
        assert first == second

    def test_from_json_handles_whitespace(self, tmp_paths):
        app, data = tmp_paths
        raw = make_valid_dict(app, data)
        loaded = InstallState.from_json(json.dumps(raw))
        assert loaded.app_dir == app


class TestInstallStateValidation:
    def test_schema_version_mismatch(self, tmp_paths):
        app, data = tmp_paths
        raw = make_valid_dict(app, data)
        raw["schema_version"] = 99
        with pytest.raises(InstallStateError, match="unsupported schema version"):
            InstallState.from_dict(raw)

    def test_missing_field(self, tmp_paths):
        app, data = tmp_paths
        raw = make_valid_dict(app, data)
        del raw["version"]
        with pytest.raises(InstallStateError, match="version"):
            InstallState.from_dict(raw)

    def test_empty_version(self, tmp_paths):
        app, data = tmp_paths
        raw = make_valid_dict(app, data)
        raw["version"] = ""
        with pytest.raises(InstallStateError, match="version"):
            InstallState.from_dict(raw)

    def test_app_dir_must_be_absolute(self, tmp_paths):
        app, data = tmp_paths
        raw = make_valid_dict(app, data)
        raw["app_dir"] = "app"
        with pytest.raises(InstallStateError, match="absolute path"):
            InstallState.from_dict(raw)

    def test_data_dir_must_be_absolute(self, tmp_paths):
        app, data = tmp_paths
        raw = make_valid_dict(app, data)
        raw["data_dir"] = "data"
        with pytest.raises(InstallStateError, match="absolute path"):
            InstallState.from_dict(raw)

    def test_app_dir_equals_data_dir_rejected(self, tmp_paths):
        app, _ = tmp_paths
        raw = make_valid_dict(app, app)
        with pytest.raises(InstallStateError, match="cannot match data directory"):
            InstallState.from_dict(raw)

    def test_modules_must_be_strings(self, tmp_paths):
        app, data = tmp_paths
        raw = make_valid_dict(app, data)
        raw["modules"] = ["ok", 123]
        with pytest.raises(InstallStateError, match="list of strings"):
            InstallState.from_dict(raw)

    def test_harnesses_must_be_strings(self, tmp_paths):
        app, data = tmp_paths
        raw = make_valid_dict(app, data)
        raw["harnesses"] = [{"id": "bad"}]
        with pytest.raises(InstallStateError, match="list of strings"):
            InstallState.from_dict(raw)


class TestGitWorktreeRejection:
    @pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
    def test_data_dir_inside_git_worktree_rejected(self, tmp_paths):
        app, _ = tmp_paths
        git_root = app.parent / "git_project"
        git_root.mkdir()
        data_dir = git_root / "LAMF"
        data_dir.mkdir()
        subprocess.run(["git", "init", str(git_root)], check=True, capture_output=True)
        raw = make_valid_dict(app, data_dir)
        with pytest.raises(InstallStateError, match="Git worktree"):
            InstallState.from_dict(raw)

    @pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
    def test_data_dir_outside_git_worktree_accepted(self, tmp_paths):
        app, data = tmp_paths
        git_root = app.parent / "git_project"
        git_root.mkdir()
        subprocess.run(["git", "init", str(git_root)], check=True, capture_output=True)
        # data is sibling to git_root, not inside it
        raw = make_valid_dict(app, data)
        state = InstallState.from_dict(raw)
        assert state.data_dir == data

    def test_git_missing_is_safe(self, tmp_paths, monkeypatch):
        app, data = tmp_paths
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        raw = make_valid_dict(app, data)
        state = InstallState.from_dict(raw)
        assert state.data_dir == data


class TestFreeSpace:
    def test_check_free_space_reports_positive(self, tmp_paths):
        _, data = tmp_paths
        available, ok = check_free_space(data, 1)
        assert available > 0
        assert ok is True

    def test_check_free_space_reports_insufficient(self, tmp_paths):
        _, data = tmp_paths
        available, _ = check_free_space(data, 1)
        available, ok = check_free_space(data, available + 2**40)
        assert ok is False

    def test_check_free_space_for_nonexistent_path(self, tmp_paths):
        app, _ = tmp_paths
        target = app.parent / "does_not_exist" / "nested"
        available, ok = check_free_space(target, 1)
        assert available > 0
        assert ok is True


class TestNewInstallState:
    def test_resolves_relative_paths(self, tmp_paths):
        app, data = tmp_paths
        original = os.getcwd()
        try:
            os.chdir(app.parent)
            state = new_install_state(
                version="1.0.0",
                app_dir=Path("app"),
                data_dir=Path("data"),
            )
            assert state.app_dir == app
            assert state.data_dir == data
        finally:
            os.chdir(original)

    def test_defaults(self, tmp_paths):
        app, data = tmp_paths
        state = new_install_state("1.0.0", app, data)
        assert state.profile == "controlled"
        assert state.modules == []
        assert state.harnesses == []
        assert state.optimizations_enabled is False
