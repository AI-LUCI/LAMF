#!/usr/bin/env python3
"""
LAMF uninstaller — cross-platform (stdlib only, Python >= 3.10).

What it does:
  1. stops the LAMF server and vault watcher (via the pid files the
     start-lamf helpers wrote);
  2. removes LAMF's OpenClaw registration (plugin entry, memory slot, MCP
     fallback server) and the agent skill — backing up openclaw.json first;
  3. KEEPS your data (~/LAMF) and your vault (~/LAMF Vault) unless you pass
     --purge AND confirm twice.

Contract: DECISIONS.md §W-04 (uninstall keeps memory data by default).
"""
from __future__ import annotations

# Old interpreter? Re-exec with python3 BEFORE anything else (same logic as
# install.py; importing install.py below does NOT re-exec, so we do it here).
import os
import shutil
import subprocess
import sys

if sys.version_info[:2] < (3, 10):
    for _exe in ("python3.13", "python3.12", "python3.11", "python3.10", "python3"):
        _path = shutil.which(_exe)
        if _path and os.path.realpath(_path) != os.path.realpath(sys.executable or ""):
            try:
                _v = subprocess.run(
                    [_path, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                    capture_output=True, text=True, timeout=20)
                _maj, _min = _v.stdout.strip().split(".")[:2]
                if (int(_maj), int(_min)) >= (3, 10):
                    os.execv(_path, [_path, os.path.abspath(__file__), *sys.argv[1:]])
            except Exception:
                continue
    print("\n  LAMF needs Python 3.10 or newer to uninstall. Install python3 and re-run.")
    sys.exit(1)

import argparse
import signal
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Reuse the installer core (paths, UI, OpenClaw merge/unmerge, helpers).
import install as inst  # noqa: E402

DEFAULT_VAULT = "~/LAMF Vault"


def stop_lamf(ui: inst.UI, data_dir: Path) -> None:
    """Stop serve/watch via pid files; fall back to a pattern kill on POSIX."""
    run_dir = data_dir / "run"
    stopped = False
    for name in ("serve", "watch"):
        pidfile = run_dir / f"{name}.pid"
        if not pidfile.is_file():
            continue
        try:
            pid = int(pidfile.read_text().strip())
        except ValueError:
            pidfile.unlink(missing_ok=True)
            continue
        try:
            if sys.platform == "win32":
                import subprocess
                subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                               capture_output=True, timeout=30)
            else:
                os.kill(pid, signal.SIGTERM)
                for _ in range(50):  # up to 5 s to exit gracefully
                    try:
                        os.kill(pid, 0)
                    except OSError:
                        break
                    time.sleep(0.1)
                else:
                    os.kill(pid, signal.SIGKILL)
            ui.ok(f"Stopped lamf {name} (pid {pid})")
            stopped = True
        except (OSError, Exception) as exc:  # already dead is fine
            ui.detail(f"pid {pid}: {exc}")
        pidfile.unlink(missing_ok=True)
    if not stopped:
        # Last resort on POSIX: match the exact module invocations.
        if sys.platform != "win32":
            import subprocess
            proc = subprocess.run(["pkill", "-f", "lamf\\.cli (serve|watch)"],
                                  capture_output=True)
            if proc.returncode == 0:
                ui.ok("Stopped LAMF processes (pattern match).")
                stopped = True
    if not stopped:
        ui.info("LAMF was not running.")


def purge(ui: inst.UI, data_dir: Path, vault: Path, assume_yes: bool) -> bool:
    """Delete data + vault + venv. Requires TWO explicit confirmations."""
    print()
    ui.warn("--purge permanently deletes:")
    print(f"       - all LAMF memory data : {data_dir}")
    print(f"       - your Obsidian vault  : {vault}  (YOUR NOTES!)")
    print(f"       - the Python venv      : {inst.venv_dir()}")
    print()
    if not assume_yes:
        if not inst.is_tty():
            ui.fail("--purge needs an interactive terminal (or --yes for scripts).")
            return False
        first = input("  Type  delete my LAMF data  to continue: ").strip()
        if first != "delete my LAMF data":
            ui.info("First confirmation not given — nothing was deleted.")
            return False
        second = input("  Are you absolutely sure? This cannot be undone. Type YES: ").strip()
        if second != "YES":
            ui.info("Second confirmation not given — nothing was deleted.")
            return False
    for path, label in ((data_dir, "data"), (vault, "vault"), (inst.venv_dir(), "venv")):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            ui.ok(f"Deleted {label}: {path}")
    return True


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="uninstall.py",
        description="LAMF uninstaller (keeps your data unless --purge).",
    )
    p.add_argument("--data-dir", default=inst.DEFAULT_DATA_DIR,
                   help=f"LAMF data directory (default: {inst.DEFAULT_DATA_DIR})")
    p.add_argument("--vault", default=DEFAULT_VAULT,
                   help=f"vault location, only touched with --purge (default: '{DEFAULT_VAULT}')")
    p.add_argument("--purge", action="store_true",
                   help="also delete data + vault + venv (asks twice)")
    p.add_argument("--yes", action="store_true",
                   help="skip the --purge confirmation prompts (scripts only — dangerous)")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    ui = inst.UI(verbose=args.verbose)
    data_dir = inst.expand(args.data_dir)
    vault = inst.expand(args.vault)

    ui.banner("LAMF uninstaller")
    print()
    print("  This stops LAMF and removes its OpenClaw registration.")
    if not args.purge:
        print("  Your memories and your vault are NOT touched.")

    ui.step(1, 3, "Stopping the LAMF server and watcher")
    stop_lamf(ui, data_dir)

    ui.step(2, 3, "Removing the OpenClaw registration and skill")
    if inst.unregister_openclaw(ui):
        ui.ok("OpenClaw registration removed (openclaw.json backed up first).")
    else:
        ui.info("No OpenClaw registration found — nothing to remove.")

    ui.step(3, 3, "Data")
    rc = 0
    if args.purge:
        if not purge(ui, data_dir, vault, args.yes):
            ui.warn("Purge did not complete — your data is untouched.")
            rc = 1
    else:
        ui.ok(f"Kept all data:  {data_dir}")
        ui.ok(f"Kept the vault: {vault}")
        print()
        print("  If you ever want LAMF back, just re-run installer/install.sh —")
        print("  everything is still here. To delete the data too, run:")
        print(f"    {sys.executable} {Path(__file__).name} --purge")

    print()
    if rc == 0:
        ui.ok("Uninstall complete.")
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print("\n\n  Cancelled — nothing was deleted.")
        sys.exit(130)
