"""LAMF Windows uninstall helper.

This module is the entry point for ``uninstall.exe``. It is invoked in two
modes:

1. **Inno-driven uninstall** (``/INNO_MODE``) — run by Inno Setup before it
   removes the application files.  The helper disconnects every harness
   recorded in ``install-state.json``, stops LAMF processes, and *never*
   removes files or data.  Inno Setup owns file removal and honors a non-zero
   exit code by aborting the uninstall.

2. **Standalone uninstall** — run directly by the operator.  The helper stops
   processes, disconnects harnesses, removes the application directory, and
   preserves the private data directory unless the operator explicitly requests
   removal.

Command-line switches mirror Inno Setup conventions and also accept GNU-style
aliases for easier testing:

* ``/APP_DIR=<path>`` / ``--app-dir=<path>`` — location of ``lamf.exe``.
* ``/DATA_DIR=<path>`` / ``--data-dir=<path>`` — private memory directory.
* ``/REMOVE_DATA`` / ``--remove-data`` — request data deletion (standalone only).
* ``/FORCE`` / ``--force`` — skip the interactive confirmation (silent mode).
* ``/SILENT`` / ``--silent`` — non-interactive mode.
* ``/INNO_MODE`` / ``--inno-mode`` — Inno-driven mode: disconnect harnesses
  before stopping processes, requires ``--app-dir``, and never removes files
  or data.
* ``/LOG_FILE=<path>`` / ``--log-file=<path>`` — capture stdout/stderr to a
  UTF-8 log file (Inno mode only).

In interactive mode, ``/REMOVE_DATA`` triggers a second confirmation prompt.
In silent mode, data is removed only when both ``/REMOVE_DATA`` and ``/FORCE``
are present.  In Inno mode, ``/REMOVE_DATA`` is ignored and data is always
preserved.
"""

from __future__ import annotations

import argparse
import inspect
import os
import shutil
import signal
import subprocess
import sys
import time
import typing
from pathlib import Path
from typing import Iterable

from . import harness_adapters
from .harness_adapters import ADAPTERS, HarnessError
from .install_state import InstallState, InstallStateError

PID_NAMES = ("lamf", "lamf-control")


class UninstallError(RuntimeError):
    """Unrecoverable uninstall error."""


# ---------------------------------------------------------------------------
# harness cleanup
# ---------------------------------------------------------------------------


def _harness_config_dir(harness_id: str) -> Path:
    """Return the conventional user-level config directory for *harness_id*."""
    home = Path.home()
    mapping = {
        "codex": home / ".codex",
        "claude": home / ".claude",
        "kimi": home / ".kimi-code",
        "gemini": home / ".gemini",
        "grok": home / ".grok",
        "hermes": home / ".hermes",
        "openclaw": home / ".openclaw",
    }
    return mapping.get(harness_id, home)


def _adapter_accepts_none_config(func) -> bool:
    """Return ``True`` if *func* accepts ``config_dir=None``.

    A parameter is considered None-accepting when its default is ``None`` or
    its annotation includes ``type(None)`` (e.g. ``str | Path | None``).
    """
    sig = inspect.signature(func)
    param = sig.parameters.get("config_dir")
    if param is None:
        return False
    if param.default is None:
        return True
    annotation = param.annotation
    if annotation is inspect.Parameter.empty:
        return False
    return type(None) in typing.get_args(annotation)


def disconnect_harnesses(
    harnesses: Iterable[str],
    lamf_exe: str | Path,
    data_dir: str | Path,
    config_dir: Path | None = None,
) -> dict[str, dict]:
    """Disconnect every *harness_id* and return per-harness results.

    All harnesses are attempted even if one fails.  If any disconnect raises,
    the failures are aggregated into a single :class:`UninstallError` so the
    caller can abort before removing files.

    When *config_dir* is ``None`` the harness adapter API is inspected: if it
    accepts ``None`` for ``config_dir`` that is passed through, otherwise the
    conventional per-harness config directory is used.
    """
    lamf_exe = Path(lamf_exe)
    data_dir = Path(data_dir)
    results: dict[str, dict] = {}
    failures: dict[str, Exception] = {}

    pass_none = config_dir is None and _adapter_accepts_none_config(
        harness_adapters.disconnect
    )

    for harness_id in harnesses:
        try:
            if config_dir is not None:
                effective_config_dir = config_dir
            elif pass_none:
                effective_config_dir = None
            else:
                effective_config_dir = _harness_config_dir(harness_id)
            result = harness_adapters.disconnect(
                harness_id, lamf_exe, data_dir, effective_config_dir
            )
            results[harness_id] = result
        except Exception as exc:
            failures[harness_id] = exc

    if failures:
        details = "; ".join(
            f"{hid}: {exc}" for hid, exc in failures.items()
        )
        raise UninstallError(
            f"harness cleanup failed for {len(failures)} harness(es): {details}"
        )

    return results


# ---------------------------------------------------------------------------
# process control
# ---------------------------------------------------------------------------


def stop_from_pid_files(pid_dir: Path, names: Iterable[str] = PID_NAMES) -> list[int]:
    """Stop processes described by ``<name>.pid`` files in *pid_dir*.

    Returns the list of process IDs that were alive and successfully stopped.
    Missing pid files and stale pids for processes that no longer exist are
    ignored. Pid files are removed after the attempt regardless of success.
    """
    pid_dir = Path(pid_dir)
    stopped: list[int] = []
    for name in names:
        pidfile = pid_dir / f"{name}.pid"
        if not pidfile.is_file():
            continue
        try:
            pid = int(pidfile.read_text(encoding="utf-8").strip())
        except ValueError:
            pidfile.unlink(missing_ok=True)
            continue
        if _process_alive(pid) and _stop_process(pid):
            stopped.append(pid)
        pidfile.unlink(missing_ok=True)
    return stopped


def _stop_process(pid: int) -> bool:
    """Terminate *pid* and return ``True`` if it is no longer running."""
    if sys.platform == "win32":
        return _stop_windows(pid)
    return _stop_posix(pid)


def _stop_windows(pid: int) -> bool:
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    return not _process_alive(pid)


def _stop_posix(pid: int) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    for _ in range(50):  # up to 5 s for graceful shutdown
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return not _process_alive(pid)


def _process_alive(pid: int) -> bool:
    if sys.platform == "win32":
        try:
            import ctypes  # pragma: no cover - Windows-only path
            kernel = ctypes.windll.kernel32
            handle = kernel.OpenProcess(1, False, pid)  # PROCESS_TERMINATE
            if not handle:
                return False
            kernel.CloseHandle(handle)
            return True
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return False


# ---------------------------------------------------------------------------
# directory removal
# ---------------------------------------------------------------------------


def remove_directory(path: Path) -> None:
    """Recursively remove *path* if it exists.

    Raises :class:`UninstallError` when the path exists but cannot be removed.
    """
    path = Path(path)
    if not path.exists():
        return
    try:
        shutil.rmtree(path, ignore_errors=False)
    except OSError as exc:
        raise UninstallError(f"cannot remove {path}: {exc}") from exc


def preserve_directory(path: Path) -> None:
    """No-op placeholder that documents the preservation promise."""


# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------


def _normalize_switch(arg: str) -> str:
    """Convert ``/SWITCH`` or ``/SWITCH=VALUE`` to ``--switch`` form."""
    if sys.platform == "win32" and arg.startswith("/") and not arg.startswith("//"):
        body = arg[1:]
        if "=" in body:
            key, value = body.split("=", 1)
            # Inno Setup quotes values that contain spaces; strip those quotes
            # so the parsed path is usable.
            value = value.strip('"').strip("'")
            return f"--{key.lower().replace('_', '-')}={value}"
        return f"--{body.lower().replace('_', '-')}"
    return arg


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse Inno-Setup-style and GNU-style uninstall switches."""
    if argv is None:
        argv = sys.argv[1:]
    normalized = [_normalize_switch(a) for a in argv]

    p = argparse.ArgumentParser(
        prog="uninstall.exe",
        description="Remove LAMF. Data is preserved unless --remove-data is used.",
        allow_abbrev=False,
    )
    p.add_argument("--app-dir", default=None,
                   help="application directory (default: read from install-state.json)")
    p.add_argument("--data-dir", default=None,
                   help="data directory (default: read from install-state.json)")
    p.add_argument("--remove-data", action="store_true",
                   help="also remove the private data directory (standalone only)")
    p.add_argument("--force", action="store_true",
                   help="skip confirmation prompts (silent mode)")
    p.add_argument("--silent", action="store_true",
                   help="run non-interactively")
    p.add_argument("--inno-mode", action="store_true",
                   help="Inno-driven mode: disconnect harnesses before stopping "
                        "processes, requires --app-dir, and never removes files or data")
    p.add_argument("--log-file", default=None,
                   help="path to capture stdout and stderr (Inno mode only)")
    return p.parse_args(normalized)


# ---------------------------------------------------------------------------
# main orchestration
# ---------------------------------------------------------------------------


def locate_state(app_dir: Path | None, data_dir: Path | None) -> InstallState:
    """Load install state from explicit paths or discover it.

    The state is first looked for in *app_dir* if provided, then in *data_dir*.
    At least one directory must contain a readable ``install-state.json``.
    """
    candidates: list[Path] = []
    if app_dir is not None:
        candidates.append(Path(app_dir) / "install-state.json")
    if data_dir is not None:
        candidates.append(Path(data_dir) / "install-state.json")
    if not candidates:
        raise UninstallError(
            "no application or data directory given; cannot find install-state.json"
        )
    last_error: Exception | None = None
    for path in candidates:
        try:
            return InstallState.load(path)
        except InstallStateError as exc:
            last_error = exc
    raise UninstallError(f"cannot load install state: {last_error}")


def confirm_remove_data_interactive(
    data_dir: Path, input_func=input
) -> bool:
    """Ask for two explicit confirmations before deleting *data_dir*."""
    print()
    print("WARNING: removing the data directory permanently deletes:")
    print(f"    {data_dir}")
    print("This includes all LAMF memory, identity keys, and settings.")
    print()
    first = input_func("Type 'delete my LAMF data' to continue: ").strip()
    if first != "delete my LAMF data":
        print("First confirmation not given — data directory will be preserved.")
        return False
    second = input_func(
        "Are you absolutely sure? This cannot be undone. Type YES: ")
    second = second.strip()
    if second != "YES":
        print("Second confirmation not given — data directory will be preserved.")
        return False
    return True


def run_inno_mode_uninstall(
    app_dir: Path,
    data_dir: Path,
    state: InstallState,
) -> int:
    """Inno-driven ``/INNO_MODE`` uninstall: disconnect, then stop, then preserve.

    Harnesses are disconnected *before* processes are stopped.  The application
    directory and data directory are never removed.  Returns ``0`` on success
    and ``1`` if any harness disconnect fails.
    """
    print("LAMF uninstall helper (Inno-driven /INNO_MODE)")
    print()
    print(f"Application directory: {app_dir}")
    print(f"Data directory:        {data_dir}")
    print("Inno Setup will remove the application files; data will be preserved.")
    print()

    if state.harnesses:
        print(f"Disconnecting harnesses: {', '.join(state.harnesses)}")
        try:
            disconnect_harnesses(
                state.harnesses, app_dir / "lamf.exe", data_dir, config_dir=None
            )
        except UninstallError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print("Harness cleanup complete.")
    else:
        print("No harnesses configured; skipping harness cleanup.")

    print("Stopping LAMF processes...")
    stopped = stop_from_pid_files(data_dir / "run")
    if stopped:
        print(f"Stopped processes: {', '.join(str(pid) for pid in stopped)}")
    else:
        print("No running LAMF processes found.")

    print()
    print("Uninstall helper completed; leaving file removal to Inno Setup.")
    return 0


def run_uninstall(
    app_dir: Path,
    data_dir: Path,
    remove_data: bool,
    silent: bool,
    force: bool,
    state: InstallState,
    input_func=input,
) -> int:
    """Execute the standalone uninstall sequence.

    Returns ``0`` on success, ``1`` if the operator cancelled data removal,
    and raises :class:`UninstallError` for hard failures.
    """
    print("LAMF uninstaller")
    print()
    print(f"Application directory: {app_dir}")
    print(f"Data directory:        {data_dir}")
    if remove_data:
        if silent:
            if not force:
                print("/REMOVE_DATA in silent mode requires /FORCE — data preserved.")
                remove_data = False
        else:
            remove_data = confirm_remove_data_interactive(data_dir, input_func)
            if not remove_data:
                print()
    else:
        print("Your LAMF data directory will be preserved.")
        print()

    print("Stopping LAMF processes...")
    stopped = stop_from_pid_files(data_dir / "run")
    if stopped:
        print(f"Stopped processes: {', '.join(str(pid) for pid in stopped)}")
    else:
        print("No running LAMF processes found.")

    print("Disconnecting harnesses...")
    if state.harnesses:
        disconnect_harnesses(state.harnesses, app_dir / "lamf.exe", data_dir)
        print("Harness cleanup complete.")
    else:
        print("No harnesses configured; skipping harness cleanup.")

    print(f"Removing application directory: {app_dir}")
    remove_directory(app_dir)

    if remove_data:
        print(f"Removing data directory: {data_dir}")
        remove_directory(data_dir)
    else:
        print(f"Preserved data directory: {data_dir}")

    print()
    print("Uninstall complete.")
    return 0


def _open_inno_log(log_file: str | None) -> tuple:
    """Open *log_file* for UTF-8 capture and return (handle, old_stdout, old_stderr).

    Returns ``(None, sys.stdout, sys.stderr)`` when *log_file* is empty so the
    caller can use the same restore logic unconditionally.
    """
    if not log_file:
        return None, sys.stdout, sys.stderr
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "w", encoding="utf-8")  # noqa: SIM115
    return handle, sys.stdout, sys.stderr


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``uninstall.exe``."""
    args = parse_args(argv)

    # In Inno-driven mode stdout/stderr may be invalid handles (hidden process).
    # Redirect to an explicit UTF-8 log file for the entire execution so errors
    # are visible and the uninstall can be diagnosed.
    log_handle = None
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    if args.inno_mode and args.log_file:
        log_handle, old_stdout, old_stderr = _open_inno_log(args.log_file)
        sys.stdout = log_handle
        sys.stderr = log_handle

    try:
        if args.inno_mode:
            if not args.app_dir:
                print("Error: --inno-mode requires --app-dir", file=sys.stderr)
                return 1
            try:
                state = locate_state(Path(args.app_dir), None)
            except UninstallError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            return run_inno_mode_uninstall(
                app_dir=state.app_dir,
                data_dir=state.data_dir,
                state=state,
            )

        try:
            state = locate_state(
                Path(args.app_dir) if args.app_dir else None,
                Path(args.data_dir) if args.data_dir else None,
            )
        except UninstallError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        return run_uninstall(
            app_dir=state.app_dir,
            data_dir=state.data_dir,
            remove_data=args.remove_data,
            silent=args.silent,
            force=args.force,
            state=state,
        )
    finally:
        if log_handle is not None:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            log_handle.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UninstallError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled — nothing was deleted.")
        sys.exit(130)
