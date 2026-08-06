"""Tests for installer/windows/post_install.py."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import install_state  # noqa: E402
from post_install import (  # noqa: E402
    PYTHON_UTF8_ENV_VARS,
    PostInstallError,
    _configure_optimizations,
    _data_dir_initialized,
    _doctor_succeeds,
    _harness_config_dir,
    _normalize_harnesses,
    _partial_instance_artifacts,
    _resolved_args,
    _run_init,
    _run_init_safe,
    _utf8_env,
    parse_args,
    run_post_install,
)

# The packaged runtime is available from the source tree during tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))
import lamf.optimizations as optimizations  # noqa: E402


ALL_MODULE_IDS = (
    "minimal-solution",
    "selective-workflows",
    "stale-context-guards",
    "surgical-changes",
    "verified-execution",
)


def _make_optimization_modules(root: Path) -> Path:
    """Create a fake optimization pack under *root* and return its modules dir."""
    modules_dir = root / "optimizations" / "modules"
    for module_id in ALL_MODULE_IDS:
        directory = modules_dir / module_id
        directory.mkdir(parents=True)
        (directory / "module.json").write_text(
            json.dumps({
                "id": module_id,
                "version": "1",
                "default_enabled": True,
                "instruction_file": "instruction.md",
            }),
            encoding="utf-8",
        )
        (directory / "instruction.md").write_text(
            f"instruction for {module_id}", encoding="utf-8"
        )
    return modules_dir


def test_parse_args_reads_environment():
    env = {
        "LAMF_APP_DIR": "C:\\app",
        "LAMF_DATA_DIR": "C:\\data",
        "LAMF_PROFILE": "locked",
        "LAMF_HARNESSES": "codex,kimi",
        "LAMF_MODULES": "minimal-solution",
        "LAMF_OPTIMIZATIONS_ENABLED": "1",
        "LAMF_SILENT": "true",
    }
    old = {k: os.environ.pop(k, None) for k in env}
    try:
        os.environ.update(env)
        args = parse_args([])
        assert args.app_dir == "C:\\app"
        assert args.data_dir == "C:\\data"
        assert args.profile == "locked"
        assert args.harnesses == "codex,kimi"
        assert args.modules == "minimal-solution"
        assert args.optimizations_enabled == "1"
        assert args.silent == "true"
    finally:
        for k, v in old.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)


def test_parse_args_normalizes_windows_switches():
    args = parse_args(["/APP_DIR=C:\\app", "/DATA_DIR=C:\\data", "/PROFILE=controlled"])
    assert args.app_dir == "C:\\app"
    assert args.data_dir == "C:\\data"
    assert args.profile == "controlled"


def test_normalize_harnesses_filters_unknown():
    assert _normalize_harnesses("codex,unknown,kimi,codex") == ["codex", "kimi"]


def test_harness_config_dir_returns_dot_directories():
    home = Path.home()
    assert _harness_config_dir("kimi") == home / ".kimi-code"
    assert _harness_config_dir("gemini") == home / ".gemini"
    assert _harness_config_dir("grok") == home / ".grok"


def _make_instance_artifacts(data_dir: Path, *, db_content: str = "sqlite") -> None:
    """Create a minimal complete LAMF instance layout for unit tests."""
    for name in ("lamf.db", "events", "spool", "policy.yaml",
                 "instance.key", "operator.token"):
        if name in ("events", "spool"):
            (data_dir / name).mkdir()
        elif name == "lamf.db":
            (data_dir / name).write_text(db_content, encoding="utf-8")
        else:
            (data_dir / name).write_text("", encoding="utf-8")


def test_data_dir_initialized_detects_instance():
    app_dir = Path(tempfile.mkdtemp())
    try:
        data = app_dir / "data"
        data.mkdir()
        assert not _data_dir_initialized(data, app_dir)
        _make_instance_artifacts(data)
        # Without a real embedded runtime, doctor would fail; patch it.
        with mock.patch("post_install._doctor_succeeds", return_value=True):
            assert _data_dir_initialized(data, app_dir)
    finally:
        shutil.rmtree(app_dir, ignore_errors=True)


def test_data_dir_initialized_rejects_partial_state():
    app_dir = Path(tempfile.mkdtemp())
    try:
        data = app_dir / "data"
        data.mkdir()
        (data / "lamf.db").write_text("nonzero", encoding="utf-8")
        with mock.patch("post_install._doctor_succeeds", return_value=True):
            assert not _data_dir_initialized(data, app_dir)
    finally:
        shutil.rmtree(app_dir, ignore_errors=True)


def test_partial_instance_artifacts_detects_partial():
    with tempfile.TemporaryDirectory() as td:
        data = Path(td) / "data"
        data.mkdir()
        assert _partial_instance_artifacts(data) == set()
        (data / "lamf.db").write_text("sqlite", encoding="utf-8")
        assert _partial_instance_artifacts(data) == {"lamf.db"}
        _make_instance_artifacts(data)
        assert _partial_instance_artifacts(data) == set()


def test_run_post_install_existing_data_is_preserved():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        app_dir = td / "app"
        app_dir.mkdir()
        data_dir = td / "data"
        data_dir.mkdir()
        # Mark data as a complete existing instance.
        _make_instance_artifacts(data_dir)

        # Fake lamf.exe that writes a marker instead of running init.
        (app_dir / "lamf.exe").write_text("", encoding="utf-8")
        version_file = app_dir / "version.json"
        version_file.write_text(json.dumps({"lamf_version": "2.0.0"}), encoding="utf-8")

        with mock.patch("post_install._doctor_succeeds", return_value=True):
            result = run_post_install(
                app_dir=app_dir,
                data_dir=data_dir,
                profile="controlled",
                harnesses=[],
                modules=[],
                optimizations_enabled=False,
                silent=True,
            )
        assert result["existing_data"] is True
        assert (app_dir / "install-state.json").is_file()
        assert (data_dir / "install-state.json").is_file()
        state = install_state.InstallState.load(app_dir / "install-state.json")
        assert state.data_dir == data_dir
        assert state.profile == "controlled"


def _fake_init_run(cmd, **_kwargs):
    """Simulate ``lamf init`` (and any incidental ``git`` probes) during tests."""
    if cmd and Path(cmd[0]).name.lower().startswith("git"):
        # Pretend the directory is not inside a git worktree.
        return subprocess.CompletedProcess(cmd, returncode=128, stdout="", stderr="")
    data_idx = cmd.index("--data-dir") + 1
    data = Path(cmd[data_idx])
    data.mkdir(parents=True, exist_ok=True)
    (data / "lamf.db").write_text("sqlite", encoding="utf-8")
    (data / "events").mkdir()
    (data / "spool").mkdir()
    (data / "policy.yaml").write_text("profile: controlled", encoding="utf-8")
    (data / "instance.key").write_text("", encoding="utf-8")
    (data / "operator.token").write_text("", encoding="utf-8")
    return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")


def test_run_post_install_initializes_new_data():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        app_dir = td / "app"
        app_dir.mkdir()
        data_dir = td / "data"
        version_file = app_dir / "version.json"
        version_file.write_text(json.dumps({"lamf_version": "2.0.0"}), encoding="utf-8")

        # Production code requires a python.exe to exist; it is never executed
        # because subprocess.run is mocked.
        python_dir = app_dir / "python"
        python_dir.mkdir()
        (python_dir / "python.exe").write_text("", encoding="utf-8")

        with mock.patch("post_install.subprocess.run", side_effect=_fake_init_run) as run_mock, \
             mock.patch("post_install._doctor_succeeds", return_value=True) as doctor_mock:
            result = run_post_install(
                app_dir=app_dir,
                data_dir=data_dir,
                profile="controlled",
                harnesses=[],
                modules=[],
                optimizations_enabled=False,
                silent=True,
            )

            assert result["existing_data"] is False
            assert _data_dir_initialized(data_dir, app_dir)
            assert (app_dir / "install-state.json").is_file()

        init_calls = [c for c in run_mock.call_args_list
                      if c.args[0] and Path(c.args[0][0]).name.lower() == "python.exe"]
        assert len(init_calls) == 1, "expected exactly one python.exe invocation"
        cmd = init_calls[0].args[0]
        assert cmd[1:4] == ["-B", "-m", "lamf.cli"]
        assert "--profile" in cmd
        assert cmd[cmd.index("--profile") + 1] == "controlled"
        assert "--data-dir" in cmd
        assert cmd[cmd.index("--data-dir") + 1] == str(data_dir)
        # Doctor must be invoked to confirm the fresh init is usable.
        doctor_calls = [c for c in doctor_mock.call_args_list
                        if c.args == (app_dir, data_dir)]
        assert len(doctor_calls) >= 1, "expected at least one doctor check"


def test_resolved_args_rejects_missing_app_dir():
    import argparse
    args = argparse.Namespace(
        app_dir=None, data_dir="C:\\data", profile="controlled",
        harnesses="", modules="", optimizations_enabled="", silent="", log_file="")
    try:
        _resolved_args(args)
    except Exception as exc:
        assert "LAMF_APP_DIR" in str(exc)
    else:
        raise AssertionError("expected error")


def test_configure_optimizations_enables_exactly_selected_modules():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        data_dir = td / "data"
        modules_root = _make_optimization_modules(td)

        with mock.patch.object(optimizations, "module_root", return_value=modules_root):
            status = _configure_optimizations(
                app_dir=td / "app",
                data_dir=data_dir,
                modules=["minimal-solution", "verified-execution"],
                optimizations_enabled=True,
            )

        assert status["enabled"] is True
        states = {item["id"]: item["enabled"] for item in status["modules"]}
        assert states["minimal-solution"] is True
        assert states["verified-execution"] is True
        assert states["selective-workflows"] is False
        assert states["stale-context-guards"] is False
        assert states["surgical-changes"] is False

        # Persisted config reflects the same choices.
        persisted = json.loads(optimizations.config_path(data_dir).read_text(encoding="utf-8"))
        assert persisted["enabled"] is True
        assert persisted["modules"]["minimal-solution"] is True
        assert persisted["modules"]["verified-execution"] is True
        assert persisted["modules"]["selective-workflows"] is False


def test_configure_optimizations_later_cli_toggle():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        data_dir = td / "data"
        modules_root = _make_optimization_modules(td)

        with mock.patch.object(optimizations, "module_root", return_value=modules_root):
            _configure_optimizations(
                app_dir=td / "app",
                data_dir=data_dir,
                modules=["minimal-solution", "verified-execution"],
                optimizations_enabled=True,
            )
            # Later CLI toggle: turn off one of the originally enabled modules.
            optimizations.set_module(data_dir, "minimal-solution", False)
            status = optimizations.status(data_dir)

        states = {item["id"]: item["enabled"] for item in status["modules"]}
        assert states["minimal-solution"] is False
        assert states["verified-execution"] is True
        assert all(not states[mid] for mid in ALL_MODULE_IDS if mid not in {
                   "minimal-solution", "verified-execution"})


def test_configure_optimizations_global_off():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        data_dir = td / "data"
        modules_root = _make_optimization_modules(td)

        with mock.patch.object(optimizations, "module_root", return_value=modules_root):
            status = _configure_optimizations(
                app_dir=td / "app",
                data_dir=data_dir,
                modules=["minimal-solution"],
                optimizations_enabled=False,
            )

        assert status["enabled"] is False
        assert all(not item["enabled"] for item in status["modules"])
        assert optimizations.compiled_instructions(data_dir) == ""


def test_configure_optimizations_rejects_unknown():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        data_dir = td / "data"
        modules_root = _make_optimization_modules(td)

        with mock.patch.object(optimizations, "module_root", return_value=modules_root):
            try:
                _configure_optimizations(
                    app_dir=td / "app",
                    data_dir=data_dir,
                    modules=["minimal-solution", "not-a-real-module"],
                    optimizations_enabled=True,
                )
            except PostInstallError as exc:
                assert "not-a-real-module" in str(exc)
                assert "unknown optimization modules" in str(exc)
            else:
                raise AssertionError("expected PostInstallError")


def test_run_post_install_updates_optimizations_on_existing_data():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        app_dir = td / "app"
        app_dir.mkdir()
        data_dir = td / "data"
        data_dir.mkdir()
        _make_instance_artifacts(data_dir)
        (app_dir / "lamf.exe").write_text("", encoding="utf-8")
        (app_dir / "version.json").write_text(
            json.dumps({"lamf_version": "2.0.0"}), encoding="utf-8"
        )

        modules_root = _make_optimization_modules(td)

        with mock.patch.object(optimizations, "module_root", return_value=modules_root), \
             mock.patch("post_install._doctor_succeeds", return_value=True):
            result = run_post_install(
                app_dir=app_dir,
                data_dir=data_dir,
                profile="controlled",
                harnesses=[],
                modules=["selective-workflows", "stale-context-guards"],
                optimizations_enabled=True,
                silent=True,
            )

        assert result["existing_data"] is True
        status = result["optimizations"]
        states = {item["id"]: item["enabled"] for item in status["modules"]}
        assert states["selective-workflows"] is True
        assert states["stale-context-guards"] is True
        assert states["minimal-solution"] is False
        assert states["verified-execution"] is False
        assert states["surgical-changes"] is False


def test_run_post_install_fails_on_partial_state():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        app_dir = td / "app"
        app_dir.mkdir()
        data_dir = td / "data"
        data_dir.mkdir()
        # Only one artifact: partial state that must not be overwritten.
        (data_dir / "lamf.db").write_text("", encoding="utf-8")
        (app_dir / "version.json").write_text(
            json.dumps({"lamf_version": "2.0.0"}), encoding="utf-8"
        )

        try:
            run_post_install(
                app_dir=app_dir,
                data_dir=data_dir,
                profile="controlled",
                harnesses=[],
                modules=[],
                optimizations_enabled=False,
                silent=True,
            )
        except PostInstallError as exc:
            assert "partial LAMF data" in str(exc)
            assert "lamf.db" in str(exc)
        else:
            raise AssertionError("expected PostInstallError for partial state")


def test_run_init_safe_cleans_up_failed_attempt():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        app_dir = td / "app"
        app_dir.mkdir()
        data_dir = td / "data"
        (app_dir / "python" / "python.exe").parent.mkdir(parents=True)
        (app_dir / "python" / "python.exe").write_text("", encoding="utf-8")

        def _failing_init(cmd, **_kwargs):
            data_idx = cmd.index("--data-dir") + 1
            data = Path(cmd[data_idx])
            data.mkdir(parents=True, exist_ok=True)
            (data / "lamf.db").write_text("", encoding="utf-8")
            (data / "events").mkdir()
            return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="init failed")

        with mock.patch("post_install.subprocess.run", side_effect=_failing_init):
            try:
                _run_init_safe(app_dir, data_dir, "controlled")
            except PostInstallError as exc:
                assert "init failed" in str(exc)
            else:
                raise AssertionError("expected PostInstallError")

        # Only artifacts from the failed attempt were removed.
        assert not data_dir.exists() or not any(data_dir.iterdir())


def test_run_init_safe_preserves_preexisting_files():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        app_dir = td / "app"
        app_dir.mkdir()
        data_dir = td / "data"
        data_dir.mkdir()
        preexisting = data_dir / "user-file.txt"
        preexisting.write_text("keep me", encoding="utf-8")
        (app_dir / "python" / "python.exe").parent.mkdir(parents=True)
        (app_dir / "python" / "python.exe").write_text("", encoding="utf-8")

        def _failing_init(cmd, **_kwargs):
            data_idx = cmd.index("--data-dir") + 1
            data = Path(cmd[data_idx])
            data.mkdir(parents=True, exist_ok=True)
            (data / "lamf.db").write_text("", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="init failed")

        with mock.patch("post_install.subprocess.run", side_effect=_failing_init):
            try:
                _run_init_safe(app_dir, data_dir, "controlled")
            except PostInstallError:
                pass
            else:
                raise AssertionError("expected PostInstallError")

        assert preexisting.is_file()
        assert preexisting.read_text(encoding="utf-8") == "keep me"
        # The artifact created by the failed attempt was removed.
        assert not (data_dir / "lamf.db").exists()


def test_utf8_env_preserves_inherited_env():
    """_utf8_env keeps existing variables and only adds Python UTF-8 flags."""
    original = os.environ.get("PYTHONUTF8")
    original_io = os.environ.get("PYTHONIOENCODING")
    original_path = os.environ.get("PATH")
    try:
        os.environ["LAMF_PRESERVE_TEST"] = "keep"
        env = _utf8_env()
        assert env["PYTHONUTF8"] == "1"
        assert env["PYTHONIOENCODING"] == "utf-8"
        assert env["LAMF_PRESERVE_TEST"] == "keep"
        assert env["PATH"] == original_path
        # Existing values are overwritten only for the Python UTF-8 keys.
        os.environ["PYTHONUTF8"] = "0"
        env = _utf8_env()
        assert env["PYTHONUTF8"] == "1"
    finally:
        os.environ.pop("LAMF_PRESERVE_TEST", None)
        if original is None:
            os.environ.pop("PYTHONUTF8", None)
        else:
            os.environ["PYTHONUTF8"] = original
        if original_io is None:
            os.environ.pop("PYTHONIOENCODING", None)
        else:
            os.environ["PYTHONIOENCODING"] = original_io


def test_run_init_forces_utf8_mode():
    """_run_init must invoke embedded Python with UTF-8 env and decoding."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        app_dir = td / "app"
        app_dir.mkdir()
        data_dir = td / "data Ω 😀"
        (app_dir / "python" / "python.exe").parent.mkdir(parents=True)
        (app_dir / "python" / "python.exe").write_text("", encoding="utf-8")

        def _capture_init(cmd, **kwargs):
            assert kwargs.get("encoding") == "utf-8"
            env = kwargs.get("env", {})
            for name, value in PYTHON_UTF8_ENV_VARS.items():
                assert env.get(name) == value
            assert "PATH" in env  # inherited environment preserved
            data_idx = cmd.index("--data-dir") + 1
            data = Path(cmd[data_idx])
            data.mkdir(parents=True, exist_ok=True)
            (data / "lamf.db").write_text("sqlite", encoding="utf-8")
            (data / "events").mkdir()
            (data / "spool").mkdir()
            (data / "policy.yaml").write_text("profile: controlled", encoding="utf-8")
            (data / "instance.key").write_text("", encoding="utf-8")
            (data / "operator.token").write_text("", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with mock.patch("post_install.subprocess.run", side_effect=_capture_init):
            _run_init(app_dir, data_dir, "controlled")

        assert data_dir.is_dir()


def test_doctor_succeeds_forces_utf8_mode():
    """_doctor_succeeds must invoke embedded Python with UTF-8 env and decoding."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        app_dir = td / "app"
        app_dir.mkdir()
        data_dir = td / "data Ω 😀"
        data_dir.mkdir()
        (app_dir / "python" / "python.exe").parent.mkdir(parents=True)
        (app_dir / "python" / "python.exe").write_text("", encoding="utf-8")

        captured = {}

        def _capture_doctor(cmd, **kwargs):
            captured["encoding"] = kwargs.get("encoding")
            captured["env"] = kwargs.get("env", {})
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with mock.patch("post_install.subprocess.run", side_effect=_capture_doctor):
            assert _doctor_succeeds(app_dir, data_dir) is True

        assert captured["encoding"] == "utf-8"
        for name, value in PYTHON_UTF8_ENV_VARS.items():
            assert captured["env"].get(name) == value
        assert "PATH" in captured["env"]


def test_run_post_install_handles_unicode_data_dir():
    """Regression test: paths containing Ω and non-BMP emoji must not crash."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        app_dir = td / "app"
        app_dir.mkdir()
        # Use a non-ASCII path that would fail under cp1252.
        data_dir = td / "LAMF Acceptance Ω 😀" / "Private Memory"
        version_file = app_dir / "version.json"
        version_file.write_text(json.dumps({"lamf_version": "2.0.0"}), encoding="utf-8")

        # Production code requires a python.exe to exist; it is never executed
        # because subprocess.run is mocked.
        python_dir = app_dir / "python"
        python_dir.mkdir()
        (python_dir / "python.exe").write_text("", encoding="utf-8")

        def _unicode_echo_init(cmd, **kwargs):
            if cmd and Path(cmd[0]).name.lower().startswith("git"):
                # Pretend the directory is not inside a git worktree.
                return subprocess.CompletedProcess(cmd, returncode=128, stdout="", stderr="")
            data_idx = cmd.index("--data-dir") + 1
            data = Path(cmd[data_idx])
            data.mkdir(parents=True, exist_ok=True)
            (data / "lamf.db").write_text("sqlite", encoding="utf-8")
            (data / "events").mkdir()
            (data / "spool").mkdir()
            (data / "policy.yaml").write_text("profile: controlled", encoding="utf-8")
            (data / "instance.key").write_text("", encoding="utf-8")
            (data / "operator.token").write_text("", encoding="utf-8")
            # Echo the Unicode path back as stdout to prove decoding works.
            return subprocess.CompletedProcess(
                cmd,
                returncode=0,
                stdout=f"initialized at {data}",
                stderr="",
            )

        with mock.patch("post_install.subprocess.run", side_effect=_unicode_echo_init) as run_mock, \
             mock.patch("post_install._doctor_succeeds", return_value=True):
            result = run_post_install(
                app_dir=app_dir,
                data_dir=data_dir,
                profile="controlled",
                harnesses=[],
                modules=[],
                optimizations_enabled=False,
                silent=True,
            )

            assert result["existing_data"] is False
            assert result["data_dir"] == str(data_dir)
            assert _data_dir_initialized(data_dir, app_dir)

        init_calls = [c for c in run_mock.call_args_list
                      if c.args[0] and Path(c.args[0][0]).name.lower() == "python.exe"]
        assert len(init_calls) == 1
        call = init_calls[0]
        assert call.kwargs.get("encoding") == "utf-8"
        assert call.kwargs.get("env", {}).get("PYTHONUTF8") == "1"
        assert call.kwargs.get("env", {}).get("PYTHONIOENCODING") == "utf-8"
        # The Unicode stdout must have been decoded, not replaced or dropped.
        assert any("Ω" in arg for arg in call.args[0])
        assert any("😀" in arg for arg in call.args[0])
