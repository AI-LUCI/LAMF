"""Tests for installer/windows/uninstall_helper.py."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from ..install_state import new_install_state
from ..uninstall_helper import (
    PID_NAMES,
    UninstallError,
    disconnect_harnesses,
    harness_adapters,
    locate_state,
    parse_args,
    remove_directory,
    run_inno_mode_uninstall,
    run_uninstall,
    stop_from_pid_files,
)


@pytest.fixture
def installed():
    """Create a fake installed LAMF layout and yield app/data directories."""
    with tempfile.TemporaryDirectory() as td:
        app = Path(td) / "LAMF"
        data = Path(td) / "LAMF-data"
        app.mkdir()
        data.mkdir()
        state = new_install_state("1.0.0", app, data)
        state.save(app / "install-state.json")
        state.save(data / "install-state.json")
        (data / "run").mkdir()
        yield app, data


class TestParseArgs:
    def test_gnu_style(self):
        args = parse_args(["--app-dir=C:\\LAMF", "--remove-data", "--force"])
        assert args.app_dir == "C:\\LAMF"
        assert args.remove_data is True
        assert args.force is True

    def test_windows_slash_style(self):
        # Only meaningful on Windows, but parsing is safe everywhere.
        args = parse_args(["/APP_DIR=C:\\LAMF", "/REMOVE_DATA", "/FORCE", "/SILENT"])
        assert args.app_dir == "C:\\LAMF"
        assert args.remove_data is True
        assert args.force is True
        assert args.silent is True

    def test_no_args(self):
        args = parse_args([])
        assert args.app_dir is None
        assert args.remove_data is False

    def test_inno_mode_gnu(self):
        args = parse_args(["--inno-mode", "--app-dir=C:\\LAMF"])
        assert args.inno_mode is True
        assert args.app_dir == "C:\\LAMF"

    def test_inno_mode_windows_slash(self):
        args = parse_args(["/INNO_MODE", "/APP_DIR=C:\\LAMF"])
        assert args.inno_mode is True
        assert args.app_dir == "C:\\LAMF"

    def test_log_file_gnu(self):
        args = parse_args(["--inno-mode", "--app-dir=C:\\LAMF", "--log-file=C:\\log.txt"])
        assert args.inno_mode is True
        assert args.log_file == "C:\\log.txt"

    def test_log_file_windows_slash(self):
        args = parse_args(["/INNO_MODE", "/APP_DIR=C:\\LAMF", "/LOG_FILE=C:\\log.txt"])
        assert args.inno_mode is True
        assert args.log_file == "C:\\log.txt"

    def test_legacy_inno_switch_is_rejected(self):
        """The legacy /INNO switch was removed; only /INNO_MODE remains."""
        with pytest.raises(SystemExit):
            parse_args(["/INNO", "/APP_DIR=C:\\LAMF"])


class TestLocateState:
    def test_from_app_dir(self, installed):
        app, data = installed
        state = locate_state(app, None)
        assert state.app_dir == app
        assert state.data_dir == data

    def test_from_data_dir(self, installed):
        app, data = installed
        state = locate_state(None, data)
        assert state.app_dir == app
        assert state.data_dir == data

    def test_no_directories_raises(self):
        with pytest.raises(UninstallError, match="no application or data directory"):
            locate_state(None, None)

    def test_missing_state_raises(self, installed):
        app, data = installed
        (app / "install-state.json").unlink()
        (data / "install-state.json").unlink()
        with pytest.raises(UninstallError, match="cannot load install state"):
            locate_state(app, data)


class TestRemoveDirectory:
    def test_removes_existing_directory(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "delete_me"
            target.mkdir()
            (target / "file.txt").write_text("x", encoding="utf-8")
            remove_directory(target)
            assert not target.exists()

    def test_missing_directory_is_noop(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "does_not_exist"
            remove_directory(target)
            assert not target.exists()


class TestStopFromPidFiles:
    def _start_dummy_process(self):
        """Start a long-running Python child and return its pid."""
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Give the OS a moment to actually start the process.
        time.sleep(0.1)
        return proc.pid

    def _alive(self, pid: int) -> bool:
        if sys.platform == "win32":
            try:
                import ctypes
                kernel = ctypes.windll.kernel32
                handle = kernel.OpenProcess(1, False, pid)
                if not handle:
                    return False
                kernel.CloseHandle(handle)
                return True
            except Exception:
                return False
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, OSError):
            return False

    def test_stops_running_process(self):
        with tempfile.TemporaryDirectory() as td:
            pid_dir = Path(td)
            pid = self._start_dummy_process()
            (pid_dir / "lamf.pid").write_text(str(pid), encoding="utf-8")
            stopped = stop_from_pid_files(pid_dir)
            assert pid in stopped
            assert not self._alive(pid)
            assert not (pid_dir / "lamf.pid").exists()

    def test_ignores_missing_pid_file(self):
        with tempfile.TemporaryDirectory() as td:
            pid_dir = Path(td)
            stopped = stop_from_pid_files(pid_dir)
            assert stopped == []

    def test_ignores_stale_pid_file(self):
        with tempfile.TemporaryDirectory() as td:
            pid_dir = Path(td)
            (pid_dir / "lamf-control.pid").write_text("99999999", encoding="utf-8")
            stopped = stop_from_pid_files(pid_dir)
            assert stopped == []
            assert not (pid_dir / "lamf-control.pid").exists()


class TestRunUninstall:
    def test_default_preserves_data_directory(self, installed, capsys):
        app, data = installed
        state = new_install_state("1.0.0", app, data)
        rc = run_uninstall(app, data, remove_data=False, silent=True, force=False, state=state)
        assert rc == 0
        assert not app.exists()
        assert data.exists()
        captured = capsys.readouterr()
        assert "Preserved data directory" in captured.out

    def test_remove_data_interactive_confirmed(self, installed):
        app, data = installed
        state = new_install_state("1.0.0", app, data)
        inputs = iter(["delete my LAMF data", "YES"])
        rc = run_uninstall(
            app, data, remove_data=True, silent=False, force=False, state=state,
            input_func=lambda _prompt: next(inputs),
        )
        assert rc == 0
        assert not app.exists()
        assert not data.exists()

    def test_remove_data_interactive_cancelled(self, installed):
        app, data = installed
        state = new_install_state("1.0.0", app, data)
        rc = run_uninstall(
            app, data, remove_data=True, silent=False, force=False, state=state,
            input_func=lambda _prompt: "no",
        )
        assert rc == 0
        assert not app.exists()
        assert data.exists()

    def test_silent_remove_data_requires_force(self, installed, capsys):
        app, data = installed
        state = new_install_state("1.0.0", app, data)
        rc = run_uninstall(app, data, remove_data=True, silent=True, force=False, state=state)
        assert rc == 0
        assert not app.exists()
        assert data.exists()
        captured = capsys.readouterr()
        assert "requires /FORCE" in captured.out

    def test_silent_force_removes_data(self, installed):
        app, data = installed
        state = new_install_state("1.0.0", app, data)
        rc = run_uninstall(app, data, remove_data=True, silent=True, force=True, state=state)
        assert rc == 0
        assert not app.exists()
        assert not data.exists()

    def test_stops_processes_before_removal(self, installed):
        app, data = installed
        state = new_install_state("1.0.0", app, data)
        pid = TestStopFromPidFiles()._start_dummy_process()
        (data / "run" / "lamf.pid").write_text(str(pid), encoding="utf-8")
        rc = run_uninstall(app, data, remove_data=True, silent=True, force=True, state=state)
        assert rc == 0
        assert not app.exists()
        assert not data.exists()
        alive = TestStopFromPidFiles()._alive(pid)
        assert not alive

    def test_run_uninstall_without_state_files_still_removes_app_dir(self, installed):
        app, data = installed
        (data / "run" / "lamf.pid").write_text("not-a-number", encoding="utf-8")
        state = new_install_state("1.0.0", app, data)
        rc = run_uninstall(app, data, remove_data=False, silent=True, force=False, state=state)
        assert rc == 0
        assert not app.exists()
        assert data.exists()


class TestDisconnectHarnessesConfigDir:
    def test_passes_none_when_adapter_supports_it(self, monkeypatch):
        calls = []

        def fake_disconnect(harness_id, lamf_exe, data_dir, config_dir=None):
            calls.append(config_dir)
            return {"success": True}

        monkeypatch.setattr(harness_adapters, "disconnect", fake_disconnect)
        disconnect_harnesses(
            ["kimi"], Path("/app/lamf.exe"), Path("/data"), config_dir=None
        )
        assert calls == [None]

    def test_falls_back_to_normal_config_dir(self, monkeypatch):
        calls = []

        def fake_disconnect(harness_id, lamf_exe, data_dir, config_dir: str | Path):
            calls.append(config_dir)
            return {"success": True}

        monkeypatch.setattr(harness_adapters, "disconnect", fake_disconnect)
        disconnect_harnesses(
            ["kimi"], Path("/app/lamf.exe"), Path("/data"), config_dir=None
        )
        assert calls == [Path.home() / ".kimi-code"]


class TestRunInnoMode:
    def _patch_disconnect(self, monkeypatch, calls):
        def fake_disconnect(harness_id, lamf_exe, data_dir, config_dir):
            calls.append(
                (harness_id, Path(lamf_exe), Path(data_dir), config_dir)
            )
            return {"success": True}

        monkeypatch.setattr(harness_adapters, "disconnect", fake_disconnect)

    def test_kimi_harness(self, installed, monkeypatch):
        app, data = installed
        state = new_install_state("1.0.0", app, data, harnesses=["kimi"])
        state.save(app / "install-state.json")
        calls = []
        self._patch_disconnect(monkeypatch, calls)

        rc = run_inno_mode_uninstall(app, data, state)

        assert rc == 0
        assert len(calls) == 1
        hid, lamf_exe, data_dir, config_dir = calls[0]
        assert hid == "kimi"
        assert lamf_exe == app / "lamf.exe"
        assert data_dir == data
        assert config_dir == Path.home() / ".kimi-code"
        assert app.exists()
        assert data.exists()

    def test_multiple_harnesses(self, installed, monkeypatch):
        app, data = installed
        state = new_install_state(
            "1.0.0", app, data, harnesses=["kimi", "claude"]
        )
        state.save(app / "install-state.json")
        calls = []
        self._patch_disconnect(monkeypatch, calls)

        rc = run_inno_mode_uninstall(app, data, state)

        assert rc == 0
        assert {call[0] for call in calls} == {"kimi", "claude"}
        assert app.exists()
        assert data.exists()

    def test_empty_harness_list(self, installed, capsys):
        app, data = installed
        state = new_install_state("1.0.0", app, data, harnesses=[])

        rc = run_inno_mode_uninstall(app, data, state)

        assert rc == 0
        assert "No harnesses configured" in capsys.readouterr().out
        assert app.exists()
        assert data.exists()

    def test_unicode_paths(self, monkeypatch):
        # Use the system temp dir so the paths are not inside the project
        # git worktree, which install_state rejects.
        with tempfile.TemporaryDirectory() as td:
            app = Path(td) / "LÄMF"
            data = Path(td) / "LÄMF-dätä"
            app.mkdir()
            data.mkdir()
            (data / "run").mkdir()
            state = new_install_state("1.0.0", app, data, harnesses=["kimi"])
            state.save(app / "install-state.json")
            calls = []
            self._patch_disconnect(monkeypatch, calls)

            rc = run_inno_mode_uninstall(app, data, state)

            assert rc == 0
            assert len(calls) == 1
            assert calls[0][1] == app / "lamf.exe"
            assert calls[0][2] == data
            assert app.exists()
            assert data.exists()

    def test_disconnect_failure_returns_nonzero(self, installed, monkeypatch):
        app, data = installed
        state = new_install_state("1.0.0", app, data, harnesses=["kimi"])

        def fake_disconnect(harness_id, lamf_exe, data_dir, config_dir):
            raise harness_adapters.HarnessError("disconnect failed")

        monkeypatch.setattr(harness_adapters, "disconnect", fake_disconnect)
        rc = run_inno_mode_uninstall(app, data, state)

        assert rc != 0
        assert app.exists()
        assert data.exists()

    def test_disconnect_runs_before_stopping_processes(self, installed, monkeypatch):
        app, data = installed
        state = new_install_state("1.0.0", app, data, harnesses=["kimi"])
        order = []

        def fake_disconnect(*args, **kwargs):
            order.append("disconnect")
            return {"success": True}

        monkeypatch.setattr(harness_adapters, "disconnect", fake_disconnect)
        monkeypatch.setattr(
            uninstall_helper_module(),
            "stop_from_pid_files",
            lambda *args, **kwargs: order.append("stop") or [],
        )

        rc = run_inno_mode_uninstall(app, data, state)

        assert rc == 0
        assert order == ["disconnect", "stop"]

    def test_main_inno_mode_requires_app_dir(self, capsys):
        rc = uninstall_helper_module().main(["--inno-mode"])
        assert rc == 1
        assert "--app-dir" in capsys.readouterr().err

    def test_main_inno_mode_loads_state_from_app_dir(self, installed, monkeypatch):
        app, data = installed
        state = new_install_state("1.0.0", app, data, harnesses=["kimi"])
        state.save(app / "install-state.json")
        calls = []
        self._patch_disconnect(monkeypatch, calls)

        mod = uninstall_helper_module()
        rc = mod.main(["--inno-mode", f"--app-dir={app}"])

        assert rc == 0
        assert len(calls) == 1
        assert calls[0][0] == "kimi"
        assert app.exists()
        assert data.exists()

    def test_inno_mode_log_file_captures_stdout_and_stderr(self, installed, monkeypatch):
        app, data = installed
        state = new_install_state("1.0.0", app, data, harnesses=["kimi"])
        state.save(app / "install-state.json")
        log_file = data / "uninstall.log"

        def fake_disconnect(*args, **kwargs):
            # Write to stderr as well as stdout to prove both are redirected.
            print("disconnect-stdout", flush=True)
            print("disconnect-stderr", file=sys.stderr, flush=True)
            return {"success": True}

        monkeypatch.setattr(harness_adapters, "disconnect", fake_disconnect)

        mod = uninstall_helper_module()
        rc = mod.main([
            "--inno-mode",
            f"--app-dir={app}",
            f"--log-file={log_file}",
        ])

        assert rc == 0
        assert log_file.is_file()
        log_text = log_file.read_text(encoding="utf-8")
        assert "disconnect-stdout" in log_text
        assert "disconnect-stderr" in log_text
        assert "Uninstall helper completed" in log_text

    def test_inno_mode_unicode_log_file_path(self, installed, monkeypatch):
        """A log path containing non-ASCII characters must be usable."""
        app, data = installed
        state = new_install_state("1.0.0", app, data, harnesses=[])
        state.save(app / "install-state.json")
        log_file = data / "LÄMF-uninstall 😀.log"

        mod = uninstall_helper_module()
        rc = mod.main([
            "--inno-mode",
            f"--app-dir={app}",
            f"--log-file={log_file}",
        ])

        assert rc == 0
        assert log_file.is_file()
        log_text = log_file.read_text(encoding="utf-8")
        assert "No harnesses configured" in log_text

    def test_inno_mode_log_captures_error_before_crash(self, installed, monkeypatch):
        """Errors emitted before the helper returns 1 must land in the log file."""
        app, data = installed
        state = new_install_state("1.0.0", app, data, harnesses=["kimi"])
        state.save(app / "install-state.json")
        log_file = data / "uninstall-error.log"

        def fake_disconnect(*args, **kwargs):
            raise harness_adapters.HarnessError("simulated disconnect failure")

        monkeypatch.setattr(harness_adapters, "disconnect", fake_disconnect)

        mod = uninstall_helper_module()
        rc = mod.main([
            "--inno-mode",
            f"--app-dir={app}",
            f"--log-file={log_file}",
        ])

        assert rc == 1
        assert log_file.is_file()
        log_text = log_file.read_text(encoding="utf-8")
        assert "simulated disconnect failure" in log_text
        assert "harness cleanup failed" in log_text

    def test_standalone_mode_ignores_log_file(self, installed, capsys):
        """The --log-file switch must not change stdout/stderr in standalone mode."""
        app, data = installed
        state = new_install_state("1.0.0", app, data)
        log_file = data / "should-not-exist.log"

        mod = uninstall_helper_module()
        rc = mod.main([
            "--app-dir", str(app),
            "--silent",
            f"--log-file={log_file}",
        ])

        assert rc == 0
        # Log file is not created in standalone mode.
        assert not log_file.exists()
        # Console output is still captured by pytest.
        captured = capsys.readouterr()
        assert "Uninstall complete" in captured.out


def uninstall_helper_module():
    """Return the uninstall_helper module for monkeypatching from tests."""
    from .. import uninstall_helper
    return uninstall_helper
