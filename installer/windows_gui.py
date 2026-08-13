#!/usr/bin/env python3
"""
LAMF Windows GUI installer — the friendly front door for install.py.

This module is the entry point for the one-file ``LAMF.exe`` produced by
``installer/LAMF.spec``. It owns presentation and packaging only; every
installation decision still belongs to ``installer/install.py``, which this
GUI stages to a permanent location and then runs as a subprocess.

Why staging matters
-------------------
A PyInstaller one-file build unpacks itself into a throwaway ``_MEIxxxxxx``
temp folder that is deleted the moment the process exits. ``install.py``
derives every durable path from its own location (``package_root()`` ->
``runtime/``, ``runtime/.venv``, ``05_INTEGRATIONS/openclaw-plugin``), and it
bakes those paths into the start/stop launchers and into every harness MCP
registration. Running install.py *from* ``_MEIPASS`` would therefore write
launchers and agent configs that point at a directory which no longer exists.

So the GUI does this, in order:

  1. copies the bundled payload (installer/, runtime/, 05_INTEGRATIONS/, docs)
     out of ``_MEIPASS`` into a permanent installation directory;
  2. runs the *staged* ``install.py`` with a real Python interpreter, so
     ``package_root()`` resolves to that permanent directory;
  3. verifies afterwards that no generated launcher or harness config contains
     a ``_MEI`` temp path, and that the launchers are anchored to the
     installation directory.

Everything below the ``Tk`` classes is deliberately import-safe and free of
Tk, so it can be unit-tested headlessly (runtime/tests/installer_gui_test.py).
"""
from __future__ import annotations

import importlib.util
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

WINDOWS = sys.platform == "win32"
# Keeps a console from flashing when the windowed EXE spawns a child process.
CREATE_NO_WINDOW = 0x08000000 if WINDOWS else 0

APP_NAME = "LAMF"
APP_TITLE = "LAMF Installer"
FALLBACK_VERSION = "2.0.0"
MIN_PYTHON = (3, 10)
INSTALL_RECORD = "lamf-install.json"

# Sub-directory inside the bundle that holds the staged package payload. Keeping
# it namespaced means the payload can never collide with PyInstaller's own
# runtime files in _MEIPASS.
PAYLOAD_DIR_NAME = "payload"

# Everything install.py needs at its permanent location. Order is cosmetic.
PAYLOAD_ITEMS = (
    "installer",
    "runtime",
    "02_SECURITY",
    "03_CONTRACTS",
    "04_STORAGE",
    "05_INTEGRATIONS",
    "vendor",
    "VERSION",
    "LICENSE",
    "README.md",
    "INSTALL.md",
    "SECURITY.md",
)

# Never staged: build residue and per-machine state. The venv in particular is
# machine-specific and is rebuilt by install.py at the destination.
STAGE_EXCLUDE_DIRS = frozenset({".venv", "__pycache__", ".git", "node_modules"})
STAGE_EXCLUDE_SUFFIXES = frozenset({".pyc", ".pyo"})

PROFILE_HELP = {
    "locked": "Strongest controls. Every disclosure and write is approved by you.",
    "controlled": "Recommended. Guarded default with sensible approval prompts.",
    "trusted-local": "Fewer prompts inside a machine you already trust.",
    "open-local": "Lowest friction on this machine. Still local-only, never public.",
}

WINGET_PYTHON = "winget install -e --id Python.Python.3.12"


# ---------------------------------------------------------------------------
# PyInstaller-friendly resource discovery
# ---------------------------------------------------------------------------
def is_frozen() -> bool:
    """True when running from a PyInstaller build."""
    return bool(getattr(sys, "frozen", False))


def payload_root() -> Path:
    """Directory that holds the package payload for THIS run.

    Frozen: ``<_MEIPASS>/payload`` (temporary — must be staged before use).
    Source: the repository root next to ``installer/`` (already permanent).
    """
    if is_frozen():
        base = Path(getattr(sys, "_MEIPASS", "") or Path(sys.executable).resolve().parent)
        candidate = base / PAYLOAD_DIR_NAME
        return candidate if candidate.is_dir() else base
    return Path(__file__).resolve().parent.parent


def temp_needles() -> list[str]:
    """Substrings that prove a written file points back into PyInstaller temp."""
    needles = ["_MEI"]
    mei = getattr(sys, "_MEIPASS", "")
    if mei:
        needles.append(str(Path(mei)))
    return list(dict.fromkeys(n for n in needles if n))


def package_version(root: Path | None = None) -> str:
    try:
        text = ((root or payload_root()) / "VERSION").read_text(encoding="utf-8").strip()
        return text or FALLBACK_VERSION
    except OSError:
        return FALLBACK_VERSION


_CORE_CACHE: dict[str, object] = {}


def load_installer_core(root: Path | None = None):
    """Import the bundled ``install.py`` as a module (never as ``__main__``).

    The GUI reads its harness list, profile list and path defaults straight from
    the installer core so there is exactly one source of truth. Importing under
    a non-``__main__`` name skips install.py's interpreter re-exec block.
    """
    root = (root or payload_root()).resolve()
    key = str(root)
    if key in _CORE_CACHE:
        return _CORE_CACHE[key]
    target = root / "installer" / "install.py"
    # Unique module name per root: the bundled copy and the staged copy are
    # both loadable in one process (the tests rely on exactly that).
    name = f"lamf_install_core_{abs(hash(key)):x}"
    spec = importlib.util.spec_from_file_location(name, target)
    if spec is None or spec.loader is None:  # pragma: no cover - corrupt bundle
        raise ImportError(f"cannot load installer core from {target}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec so decorators that look the module up by name
    # (dataclasses, typing) resolve, and so install.py's __name__ is never
    # "__main__" (which would trigger its interpreter re-exec block).
    sys.modules[name] = module
    spec.loader.exec_module(module)
    _CORE_CACHE[key] = module
    return module


def _import_runtime_harness(root: Path | None = None):
    """Import ``lamf.harness`` from the bundled runtime (stdlib-only module)."""
    runtime = (root or payload_root()).resolve() / "runtime"
    added = str(runtime)
    inserted = added not in sys.path
    if inserted:
        sys.path.insert(0, added)
    try:
        import lamf.harness as harness  # noqa: PLC0415 — deliberately late
        return harness
    except Exception:  # noqa: BLE001 — metadata is a nicety, never fatal
        return None
    finally:
        if inserted:
            try:
                sys.path.remove(added)
            except ValueError:  # pragma: no cover
                pass


@dataclass(frozen=True)
class HarnessChoice:
    id: str
    label: str
    config_hint: str


def harness_catalog(root: Path | None = None) -> list[HarnessChoice]:
    """Every harness the installer supports, with human labels.

    IDs come from ``install.HARNESSES`` and labels from the runtime registry, so
    a harness added to either is picked up by the GUI with no edit here.
    """
    core = load_installer_core(root)
    registry = _import_runtime_harness(root)
    meta = {}
    if registry is not None:
        meta = {hid: (h.label, h.config_path) for hid, h in registry.HARNESSES.items()}
    out: list[HarnessChoice] = []
    for hid in core.HARNESSES:
        label, hint = meta.get(hid, (hid.replace("-", " ").title(), ""))
        out.append(HarnessChoice(hid, label, hint))
    return out


def profile_catalog(root: Path | None = None) -> list[tuple[str, str]]:
    core = load_installer_core(root)
    return [(p, PROFILE_HELP.get(p, "")) for p in core.PROFILES]


# ---------------------------------------------------------------------------
# Default locations
# ---------------------------------------------------------------------------
def default_install_dir() -> Path:
    """Permanent home for the LAMF program files.

    Running from a source checkout installs in place, which keeps the developer
    workflow identical to ``python installer/install.py``.
    """
    if not is_frozen():
        return payload_root()
    if WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Programs" / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def default_data_dir(root: Path | None = None) -> Path:
    try:
        return expand_path(load_installer_core(root).DEFAULT_DATA_DIR)
    except Exception:  # noqa: BLE001
        return Path.home() / APP_NAME


def default_vault_dir(root: Path | None = None) -> Path:
    try:
        return expand_path(load_installer_core(root).DEFAULT_VAULT)
    except Exception:  # noqa: BLE001
        return Path.home() / f"{APP_NAME} Vault"


def expand_path(text: str | Path) -> Path:
    """``~`` and ``%VAR%`` aware, absolute, and safe on paths that do not exist."""
    raw = os.path.expandvars(os.path.expanduser(str(text).strip().strip('"')))
    path = Path(raw)
    try:
        return path.resolve()
    except OSError:  # pragma: no cover - exotic paths
        return path.absolute()


def is_within(child: Path, parent: Path) -> bool:
    try:
        Path(child).resolve().relative_to(Path(parent).resolve())
        return True
    except (ValueError, OSError):
        return False


# ---------------------------------------------------------------------------
# Staging the payload to a permanent location
# ---------------------------------------------------------------------------
def _stage_ignore(_dir: str, names: list[str]) -> set[str]:
    return {
        n for n in names
        if n in STAGE_EXCLUDE_DIRS or Path(n).suffix in STAGE_EXCLUDE_SUFFIXES
    }


def stage_payload(dest: Path, source: Path | None = None,
                  log=lambda _m: None) -> Path:
    """Copy the package payload to *dest* and return the staged root.

    Idempotent: an existing installation is overwritten file-by-file, so an
    already-built ``runtime/.venv`` at the destination survives an upgrade.
    Raises RuntimeError if the staged tree is not usable afterwards.
    """
    source = (source or payload_root()).resolve()
    dest = Path(dest).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    dest = dest.resolve()

    if source == dest:
        log(f"  Program files are already at {dest} — nothing to copy.")
        _assert_staged(dest)
        return dest

    log(f"  Copying program files to {dest}")
    staged = 0
    for item in PAYLOAD_ITEMS:
        src = source / item
        if not src.exists():
            log(f"    - {item} (not in this build; skipped)")
            continue
        target = dest / item
        if src.is_dir():
            shutil.copytree(src, target, dirs_exist_ok=True, ignore=_stage_ignore)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        staged += 1
        log(f"    + {item}")
    if staged == 0:
        raise RuntimeError(f"nothing to install: no payload found under {source}")
    _assert_staged(dest)
    log("  Program files staged to a permanent location.")
    return dest


def _assert_staged(dest: Path) -> None:
    required = (
        dest / "installer" / "install.py",
        dest / "runtime" / "lamf" / "cli.py",
        dest / "runtime" / "requirements.txt",
        dest / "02_SECURITY" / "profiles" / "controlled.yaml",
        dest / "03_CONTRACTS" / "schemas" / "security-policy.schema.json",
        dest / "04_STORAGE" / "SCHEMA.sql",
        dest / "05_INTEGRATIONS" / "codex" / "AGENTS.md",
    )
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise RuntimeError("incomplete installation payload; missing: " + ", ".join(missing))


# ---------------------------------------------------------------------------
# Finding a real Python interpreter (the frozen EXE cannot build a venv)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PythonInfo:
    path: str
    version: tuple[int, int]

    @property
    def label(self) -> str:
        return f"Python {self.version[0]}.{self.version[1]} ({self.path})"


_PROBE = (
    "import sys;"
    "print('%d.%d' % sys.version_info[:2]);"
    "print(sys.executable)"
)


def probe_python(argv: list[str]) -> PythonInfo | None:
    """Ask a candidate interpreter for its version and real executable path."""
    try:
        proc = subprocess.run([*argv, "-c", _PROBE], capture_output=True, text=True,
                              timeout=25, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    try:
        major, minor = (int(part) for part in lines[0].split(".")[:2])
    except ValueError:
        return None
    executable = lines[1]
    if not executable or not Path(executable).is_file():
        return None
    return PythonInfo(executable, (major, minor))


def _candidate_commands() -> list[list[str]]:
    names = ["python3.13", "python3.12", "python3.11", "python3.10", "python3", "python"]
    candidates: list[list[str]] = []
    if WINDOWS:
        py = shutil.which("py")
        if py:
            candidates.append([py, "-3"])
    if not is_frozen() and sys.executable:
        candidates.append([sys.executable])
    for name in names:
        found = shutil.which(name)
        if not found:
            continue
        # Windows Store "app execution alias" stubs are 0-byte reparse points
        # that open the Store instead of running Python.
        try:
            if Path(found).stat().st_size == 0:
                continue
        except OSError:
            continue
        candidates.append([found])
    return candidates


def find_system_python(minimum: tuple[int, int] = MIN_PYTHON) -> PythonInfo | None:
    """First interpreter on this machine at or above *minimum*, else None."""
    seen: set[str] = set()
    for argv in _candidate_commands():
        info = probe_python(argv)
        if info is None or info.path in seen:
            continue
        seen.add(info.path)
        if info.version >= minimum:
            return info
    return None


# ---------------------------------------------------------------------------
# Turning GUI choices into an install.py command line
# ---------------------------------------------------------------------------
@dataclass
class InstallOptions:
    data_dir: Path
    install_dir: Path
    profile: str = "controlled"
    harnesses: tuple[str, ...] = ()
    obsidian: bool = False
    vault: Path | None = None
    git_vault: bool = False
    start_server: bool = True
    allow_git_data_dir: bool = False
    verbose: bool = True


def build_install_argv(python_exe: str | Path, install_py: str | Path,
                       opts: InstallOptions) -> list[str]:
    """Exact argv for the staged install.py. Every choice is passed explicitly
    so install.py never needs to prompt (its stdin is closed)."""
    argv = [
        str(python_exe), str(install_py),
        "--data-dir", str(opts.data_dir),
        "--profile", opts.profile,
        "--obsidian", "parallel" if opts.obsidian else "none",
        "--git", "vault" if (opts.obsidian and opts.git_vault) else "none",
    ]
    if opts.obsidian and opts.vault is not None:
        argv += ["--vault", str(opts.vault)]
    if opts.harnesses:
        for harness_id in opts.harnesses:
            argv += ["--harness", harness_id]
    else:
        argv += ["--harness", "none"]
    if not opts.start_server:
        argv.append("--no-start")
    if opts.allow_git_data_dir:
        argv.append("--allow-git-data-dir")
    if opts.verbose:
        argv.append("--verbose")
    return argv


# ---------------------------------------------------------------------------
# Safe background execution
# ---------------------------------------------------------------------------
def start_process(argv: list[str], cwd: Path | None = None) -> subprocess.Popen:
    """Launch a child with no console window and a closed stdin."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["NO_COLOR"] = "1"
    return subprocess.Popen(
        [str(a) for a in argv],
        cwd=str(cwd) if cwd else None,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
        creationflags=CREATE_NO_WINDOW,
    )


def stream_process(proc: subprocess.Popen, on_line) -> int:
    """Pump a child's merged output line by line, then return its exit code."""
    if proc.stdout is not None:
        for line in proc.stdout:
            on_line(line.rstrip("\r\n"))
    return proc.wait()


def terminate_process_tree(proc: subprocess.Popen | None) -> None:
    """Stop a child and everything it started (install.py spawns pip)."""
    if proc is None or proc.poll() is not None:
        return
    if WINDOWS:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       capture_output=True, creationflags=CREATE_NO_WINDOW)
    else:  # pragma: no cover - Windows-first tool
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:  # pragma: no cover
        proc.kill()


# ---------------------------------------------------------------------------
# Post-install verification: nothing may point into PyInstaller temp
# ---------------------------------------------------------------------------
def installed_artifacts(data_dir: Path, harnesses: tuple[str, ...] = (),
                        root: Path | None = None) -> list[Path]:
    """Every file the install writes that embeds an absolute LAMF path."""
    data_dir = Path(data_dir)
    files: list[Path] = []
    for sub in ("bin", "adapters"):
        folder = data_dir / sub
        if folder.is_dir():
            files.extend(sorted(p for p in folder.iterdir() if p.is_file()))
    registry = _import_runtime_harness(root)
    if registry is not None:
        for harness_id in harnesses:
            try:
                target = registry.default_config_path(harness_id)
            except Exception:  # noqa: BLE001
                continue
            if target is not None and Path(target).is_file():
                files.append(Path(target))
    openclaw = Path.home() / ".openclaw" / "openclaw.json"
    if openclaw.is_file():
        files.append(openclaw)
    return list(dict.fromkeys(files))


def path_variants(text: str | Path) -> list[str]:
    """Every spelling a Windows path can take in a generated file.

    Launchers embed paths raw (``C:\\LAMF``), JSON/TOML registrations embed them
    escaped (``C:\\\\LAMF``), and some clients normalise to forward slashes.
    Matching only the raw form silently misses two of the three.
    """
    raw = str(text)
    return list(dict.fromkeys([raw, raw.replace("\\", "\\\\"), raw.replace("\\", "/")]))


def scan_for_temp_paths(files, needles: list[str] | None = None) -> list[tuple[Path, str]]:
    """Files that still reference a PyInstaller ``_MEI`` temp directory."""
    wanted = needles if needles is not None else temp_needles()
    expanded: list[str] = []
    for needle in wanted:
        if needle:
            expanded.extend(path_variants(needle))
    expanded = list(dict.fromkeys(expanded))
    hits: list[tuple[Path, str]] = []
    for candidate in files:
        path = Path(candidate)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for needle in expanded:
            if needle in text:
                hits.append((path, needle))
                break
    return hits


@dataclass
class VerifyReport:
    checked: list[Path] = field(default_factory=list)
    leaks: list[tuple[Path, str]] = field(default_factory=list)
    anchored: bool = False
    anchor_file: Path | None = None
    unanchored: list[Path] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.leaks and self.anchored and not self.unanchored


def _references(path: Path, target: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:  # pragma: no cover
        return False
    return any(variant in text for variant in path_variants(target))


def verify_permanent_paths(data_dir: Path, install_dir: Path,
                           harnesses: tuple[str, ...] = (),
                           root: Path | None = None,
                           needles: list[str] | None = None) -> VerifyReport:
    """Prove the install is anchored to *install_dir* and free of temp paths."""
    install_dir = Path(install_dir)
    report = VerifyReport()
    report.checked = installed_artifacts(data_dir, harnesses, root=root)
    report.leaks = scan_for_temp_paths(report.checked, needles)

    launcher = Path(data_dir) / "bin" / ("start-lamf.ps1" if WINDOWS else "start-lamf.sh")
    report.anchor_file = launcher
    if launcher.is_file():
        report.anchored = _references(launcher, install_dir)

    # Every emitted harness registration must name the permanent runtime too;
    # selection.json records the choice only and carries no program path.
    adapters = Path(data_dir) / "adapters"
    if adapters.is_dir():
        report.unanchored = [
            p for p in sorted(adapters.iterdir())
            if p.is_file() and p.name != "selection.json" and not _references(p, install_dir)
        ]
    return report


# ---------------------------------------------------------------------------
# Install record (lets a re-run pre-fill what you chose last time)
# ---------------------------------------------------------------------------
def write_install_record(install_dir: Path, opts: InstallOptions,
                         python_info: PythonInfo | None = None) -> Path:
    record = {
        "version": package_version(),
        "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "installed_by": "windows_gui",
        "install_dir": str(install_dir),
        "data_dir": str(opts.data_dir),
        "vault": str(opts.vault) if (opts.obsidian and opts.vault) else None,
        "profile": opts.profile,
        "harnesses": list(opts.harnesses),
        "python": python_info.path if python_info else None,
    }
    path = Path(install_dir) / INSTALL_RECORD
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def read_install_record(install_dir: Path) -> dict:
    try:
        data = json.loads((Path(install_dir) / INSTALL_RECORD).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------------------
# The installation job — runs entirely off the Tk thread
# ---------------------------------------------------------------------------
class InstallJob:
    """Stage, install, verify. Emits ``(kind, payload)`` events onto a queue.

    Kinds: ``line`` (log text), ``status`` (one-line progress), ``done``
    (``dict`` result). The Tk side drains the queue from the main thread only.
    """

    def __init__(self, opts: InstallOptions, python_info: PythonInfo,
                 events: "queue.Queue[tuple[str, object]]",
                 source: Path | None = None):
        self.opts = opts
        self.python = python_info
        self.events = events
        self.source = source or payload_root()
        self._proc: subprocess.Popen | None = None
        self._cancelled = threading.Event()
        self._thread: threading.Thread | None = None

    # -- events ------------------------------------------------------------
    def _log(self, text: str = "") -> None:
        self.events.put(("line", text))

    def _status(self, text: str) -> None:
        self.events.put(("status", text))

    # -- control -----------------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="lamf-install", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancelled.set()
        terminate_process_tree(self._proc)

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    # -- work --------------------------------------------------------------
    def _run(self) -> None:
        result = {"ok": False, "returncode": None, "message": "", "report": None}
        try:
            self._status("Copying program files ...")
            self._log("=" * 68)
            self._log(f"  {APP_TITLE} {package_version(self.source)}")
            self._log("=" * 68)
            self._log()
            self._log(f"  Interpreter : {self.python.label}")
            self._log(f"  Install to  : {self.opts.install_dir}")
            self._log(f"  Memory data : {self.opts.data_dir}")
            self._log(f"  Profile     : {self.opts.profile}")
            self._log(f"  Harnesses   : {', '.join(self.opts.harnesses) or 'none'}")
            if self.opts.obsidian and self.opts.vault:
                self._log(f"  Obsidian    : {self.opts.vault}")
            self._log()

            staged = stage_payload(self.opts.install_dir, self.source, log=self._log)
            if self._cancelled.is_set():
                raise _Cancelled()

            install_py = staged / "installer" / "install.py"
            argv = build_install_argv(self.python.path, install_py, self.opts)
            self._log()
            self._log(f"  Running: {' '.join(argv[1:])}")
            self._log()
            self._status("Installing (this can take a few minutes) ...")

            self._proc = start_process(argv, cwd=staged)
            code = stream_process(self._proc, self._log)
            result["returncode"] = code
            if self._cancelled.is_set():
                raise _Cancelled()

            self._status("Checking the installation ...")
            self._log()
            report = verify_permanent_paths(
                self.opts.data_dir, staged, self.opts.harnesses, root=staged)
            result["report"] = report
            self._log(f"  [..]   Verified {len(report.checked)} generated file(s) "
                      "for temporary-path leaks.")
            if report.leaks:
                for path, needle in report.leaks:
                    self._log(f"  [FAIL] {path} still references a temporary "
                              f"unpack directory ({needle}).")
            else:
                self._log("  [OK]   No launcher or harness config points into "
                          "PyInstaller temp.")
            if report.anchored:
                self._log(f"  [OK]   Launchers are anchored to {staged}")
            elif report.anchor_file is not None and not report.anchor_file.exists():
                self._log(f"  [WARN] Launcher {report.anchor_file} was not written; "
                          "the install did not get that far.")
            else:
                self._log(f"  [FAIL] {report.anchor_file} does not reference "
                          f"{staged}.")
            if report.unanchored:
                for path in report.unanchored:
                    self._log(f"  [FAIL] {path} does not point at the installed "
                              "runtime.")
            elif self.opts.harnesses:
                self._log(f"  [OK]   {len(self.opts.harnesses)} harness "
                          "registration(s) point at the installed runtime.")

            try:
                record = write_install_record(staged, self.opts, self.python)
                self._log(f"  [OK]   Installation recorded: {record}")
            except OSError as exc:
                self._log(f"  [WARN] Could not write the installation record: {exc}")

            leak_failure = bool(report.leaks)
            result["ok"] = code == 0 and not leak_failure
            if leak_failure:
                result["message"] = (
                    "Installation finished but generated files still point at a "
                    "temporary folder. Do not use this install; report it.")
            elif code == 0:
                result["message"] = "LAMF is installed and ready."
            elif code == 2:
                result["message"] = (
                    "The installer refused the chosen memory folder because it "
                    "sits inside a Git checkout. Choose a folder outside it.")
            else:
                result["message"] = (
                    f"The installer reported problems (exit code {code}). "
                    "The log above names the exact fix for each one.")
        except _Cancelled:
            result["message"] = "Installation cancelled. Nothing else was changed."
            self._log()
            self._log("  [WARN] Cancelled by you.")
        except Exception as exc:  # noqa: BLE001 — surface everything in the UI
            result["message"] = f"{type(exc).__name__}: {exc}"
            self._log()
            self._log(f"  [FAIL] {type(exc).__name__}: {exc}")
        finally:
            result["cancelled"] = self._cancelled.is_set()
            self.events.put(("done", result))


class _Cancelled(Exception):
    pass


# ---------------------------------------------------------------------------
# Tk user interface
# ---------------------------------------------------------------------------
def _enable_dpi_awareness() -> None:
    if not WINDOWS:
        return
    try:  # pragma: no cover - display-dependent
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass


class InstallerApp:
    """Two-page wizard: choices, then progress. Tk is touched only from here."""

    PAD = 10

    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = root
        self.events: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.job: InstallJob | None = None
        self.python_info: PythonInfo | None = None
        self.source = payload_root()

        root.title(f"{APP_TITLE} {package_version(self.source)}")
        root.minsize(720, 640)
        root.geometry("760x720")
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._init_style()
        self.container = ttk.Frame(root, padding=self.PAD)
        self.container.pack(fill="both", expand=True)

        self.options_page = ttk.Frame(self.container)
        self.progress_page = ttk.Frame(self.container)
        self._build_options_page()
        self._build_progress_page()
        self._show(self.options_page)
        self._detect_python()

    # -- chrome ------------------------------------------------------------
    def _init_style(self):
        style = self.ttk.Style()
        try:
            style.theme_use("vista" if WINDOWS else style.theme_use())
        except Exception:  # noqa: BLE001 # pragma: no cover
            pass
        base = ("Segoe UI", 10) if WINDOWS else ("TkDefaultFont", 10)
        style.configure(".", font=base)
        style.configure("Title.TLabel", font=(base[0], 16, "bold"))
        style.configure("Sub.TLabel", foreground="#4a5568")
        style.configure("Hint.TLabel", foreground="#718096", font=(base[0], 8))
        style.configure("Good.TLabel", foreground="#22683f")
        style.configure("Bad.TLabel", foreground="#9b1c1c")
        style.configure("Warn.TLabel", foreground="#8a5a00")
        style.configure("Result.TLabel", font=(base[0], 13, "bold"))

    def _show(self, page):
        for child in (self.options_page, self.progress_page):
            child.pack_forget()
        page.pack(fill="both", expand=True)

    # -- page 1: choices ---------------------------------------------------
    def _build_options_page(self):
        tk, ttk = self.tk, self.ttk
        page = self.options_page

        header = ttk.Frame(page)
        header.pack(fill="x")
        ttk.Label(header, text="Set up LAMF", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, style="Sub.TLabel", text=(
            "Your private, local agent memory. Nothing leaves this computer, and "
            "you can re-run this installer any time to repair or upgrade.")
        ).pack(anchor="w", pady=(2, 8))

        self.python_label = ttk.Label(header, text="Looking for Python ...",
                                      style="Sub.TLabel")
        self.python_label.pack(anchor="w")
        self.python_fix = ttk.Frame(header)

        record = read_install_record(default_install_dir())
        self.var_install = tk.StringVar(
            value=record.get("install_dir") or str(default_install_dir()))
        self.var_data = tk.StringVar(
            value=record.get("data_dir") or str(default_data_dir(self.source)))
        self.var_vault = tk.StringVar(
            value=record.get("vault") or str(default_vault_dir(self.source)))
        self.var_obsidian = tk.BooleanVar(value=bool(record.get("vault")))
        self.var_git = tk.BooleanVar(value=False)
        self.var_start = tk.BooleanVar(value=True)
        self.var_profile = tk.StringVar(
            value=record.get("profile") or self._default_profile())

        body = ttk.Frame(page)
        body.pack(fill="both", expand=True, pady=(8, 0))

        self._build_locations(body)
        self._build_profiles(body)
        self._build_harnesses(body, set(record.get("harnesses") or ()))
        self._build_extras(body)

        footer = ttk.Frame(page)
        footer.pack(fill="x", pady=(10, 0))
        self.install_button = ttk.Button(footer, text="Install LAMF",
                                         command=self._on_install)
        self.install_button.pack(side="right")
        ttk.Button(footer, text="Quit", command=self._on_close).pack(
            side="right", padx=(0, 8))

    def _default_profile(self) -> str:
        try:
            return load_installer_core(self.source).DEFAULT_PROFILE
        except Exception:  # noqa: BLE001
            return "controlled"

    def _path_row(self, parent, row, label, variable, hint):
        ttk = self.ttk
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row + 1, column=0, sticky="ew", padx=(0, 8))
        button = ttk.Button(parent, text="Browse ...", width=12,
                            command=lambda: self._browse(variable))
        button.grid(row=row + 1, column=1, sticky="e")
        ttk.Label(parent, text=hint, style="Hint.TLabel").grid(
            row=row + 2, column=0, columnspan=2, sticky="w", pady=(1, 8))
        return entry, button

    def _build_locations(self, parent):
        ttk = self.ttk
        box = ttk.LabelFrame(parent, text="  Where things live  ", padding=self.PAD)
        box.pack(fill="x")
        box.columnconfigure(0, weight=1)
        self._path_row(box, 0, "Your memories (permanent data folder)", self.var_data,
                       "Holds your memory database, keys and operator token. "
                       "Keep it outside any Git checkout.")
        self._path_row(box, 3, "Program files", self.var_install,
                       "Where LAMF itself is installed. Launchers and agent "
                       "configs point here, so it must stay put.")

    def _build_profiles(self, parent):
        ttk = self.ttk
        box = ttk.LabelFrame(parent, text="  Security profile  ", padding=self.PAD)
        box.pack(fill="x", pady=(10, 0))
        for name, help_text in profile_catalog(self.source):
            row = ttk.Frame(box)
            row.pack(fill="x", anchor="w")
            ttk.Radiobutton(row, text=name, value=name,
                            variable=self.var_profile, width=16).pack(side="left")
            ttk.Label(row, text=help_text, style="Hint.TLabel").pack(
                side="left", anchor="w")

    def _build_harnesses(self, parent, preselected: set[str]):
        ttk = self.ttk
        box = ttk.LabelFrame(
            parent, text="  Connect your agents (pick any number, or none)  ",
            padding=self.PAD)
        box.pack(fill="both", expand=True, pady=(10, 0))

        grid = ttk.Frame(box)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1, uniform="h")
        grid.columnconfigure(1, weight=1, uniform="h")

        self.harness_vars: dict[str, object] = {}
        catalog = harness_catalog(self.source)
        half = (len(catalog) + 1) // 2
        for index, choice in enumerate(catalog):
            column, row = (0, index) if index < half else (1, index - half)
            cell = ttk.Frame(grid)
            cell.grid(row=row, column=column, sticky="ew", pady=1)
            var = self.tk.BooleanVar(value=choice.id in preselected)
            self.harness_vars[choice.id] = var
            ttk.Checkbutton(cell, text=choice.label, variable=var).pack(anchor="w")
            if choice.config_hint:
                ttk.Label(cell, text=f"    {choice.config_hint}",
                          style="Hint.TLabel").pack(anchor="w")

        actions = ttk.Frame(box)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Select all", width=12,
                   command=lambda: self._set_all_harnesses(True)).pack(side="left")
        ttk.Button(actions, text="Select none", width=12,
                   command=lambda: self._set_all_harnesses(False)).pack(
                       side="left", padx=(6, 0))
        ttk.Label(actions, style="Hint.TLabel", text=(
            "Each selected agent gets its own config merged safely — a backup is "
            "taken first and unrelated settings are preserved.")
        ).pack(side="left", padx=(10, 0))

    def _set_all_harnesses(self, value: bool):
        for var in self.harness_vars.values():
            var.set(value)

    def _build_extras(self, parent):
        ttk = self.ttk
        box = ttk.LabelFrame(parent, text="  Options  ", padding=self.PAD)
        box.pack(fill="x", pady=(10, 0))
        box.columnconfigure(0, weight=1)

        ttk.Checkbutton(box, variable=self.var_obsidian,
                        text="Also project my memory into an Obsidian vault (optional)",
                        command=self._sync_obsidian).grid(
                            row=0, column=0, columnspan=2, sticky="w")
        self.vault_entry = ttk.Entry(box, textvariable=self.var_vault)
        self.vault_entry.grid(row=1, column=0, sticky="ew", padx=(20, 8), pady=(4, 0))
        self.vault_button = ttk.Button(box, text="Browse ...", width=12,
                                       command=lambda: self._browse(self.var_vault))
        self.vault_button.grid(row=1, column=1, sticky="e", pady=(4, 0))
        self.git_check = ttk.Checkbutton(
            box, variable=self.var_git,
            text="Track that vault as a local Git project (never pushed anywhere)")
        self.git_check.grid(row=2, column=0, columnspan=2, sticky="w",
                            padx=(20, 0), pady=(4, 6))

        ttk.Checkbutton(box, variable=self.var_start,
                        text="Start LAMF as soon as the installation finishes").grid(
                            row=3, column=0, columnspan=2, sticky="w")
        self._sync_obsidian()

    def _sync_obsidian(self):
        state = "normal" if self.var_obsidian.get() else "disabled"
        for widget in (self.vault_entry, self.vault_button, self.git_check):
            widget.configure(state=state)

    def _browse(self, variable):
        from tkinter import filedialog
        current = variable.get().strip()
        initial = current if current and Path(current).is_dir() else str(Path.home())
        chosen = filedialog.askdirectory(parent=self.root, initialdir=initial,
                                         mustexist=False, title="Choose a folder")
        if chosen:
            variable.set(str(Path(chosen)))

    # -- python detection --------------------------------------------------
    def _detect_python(self):
        self.install_button.configure(state="disabled")
        self.python_label.configure(text="Looking for Python 3.10 or newer ...",
                                    style="Sub.TLabel")

        def worker():
            info = find_system_python()
            self.root.after(0, lambda: self._python_found(info))

        threading.Thread(target=worker, name="lamf-python-probe", daemon=True).start()

    def _python_found(self, info: PythonInfo | None):
        ttk = self.ttk
        self.python_info = info
        for child in self.python_fix.winfo_children():
            child.destroy()
        if info is not None:
            self.python_fix.pack_forget()
            self.python_label.configure(text=f"Using {info.label}", style="Good.TLabel")
            self.install_button.configure(state="normal")
            return
        self.python_label.configure(style="Bad.TLabel", text=(
            "LAMF needs Python 3.10 or newer and could not find it on this computer."))
        self.python_fix.pack(fill="x", pady=(2, 6))
        ttk.Label(self.python_fix, style="Sub.TLabel", text=(
            "Install it once with this line in PowerShell, then press "
            "'Check again':")).pack(anchor="w")
        entry = ttk.Entry(self.python_fix)
        entry.insert(0, WINGET_PYTHON)
        entry.configure(state="readonly")
        entry.pack(fill="x", pady=(2, 4))
        ttk.Button(self.python_fix, text="Check again",
                   command=self._detect_python).pack(anchor="w")
        self.install_button.configure(state="disabled")

    # -- page 2: progress --------------------------------------------------
    def _build_progress_page(self):
        tk, ttk = self.tk, self.ttk
        page = self.progress_page

        ttk.Label(page, text="Installing LAMF", style="Title.TLabel").pack(anchor="w")
        self.status_label = ttk.Label(page, text="Starting ...", style="Sub.TLabel")
        self.status_label.pack(anchor="w", pady=(2, 6))
        self.progress = ttk.Progressbar(page, mode="indeterminate")
        self.progress.pack(fill="x")

        wrap = ttk.Frame(page)
        wrap.pack(fill="both", expand=True, pady=(10, 0))
        mono = ("Consolas", 9) if WINDOWS else ("TkFixedFont", 9)
        self.output = tk.Text(wrap, wrap="none", height=18, font=mono,
                              background="#11161d", foreground="#d7dee8",
                              insertbackground="#d7dee8", relief="flat",
                              padx=8, pady=6, state="disabled")
        yscroll = ttk.Scrollbar(wrap, orient="vertical", command=self.output.yview)
        xscroll = ttk.Scrollbar(wrap, orient="horizontal", command=self.output.xview)
        self.output.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.output.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.output.tag_configure("ok", foreground="#6ee7a0")
        self.output.tag_configure("fail", foreground="#ff8a8a")
        self.output.tag_configure("warn", foreground="#ffcf6e")
        self.output.tag_configure("head", foreground="#7cc4ff")

        self.result_label = ttk.Label(page, text="", style="Result.TLabel",
                                      wraplength=700, justify="left")
        self.result_label.pack(anchor="w", pady=(10, 0))

        footer = ttk.Frame(page)
        footer.pack(fill="x", pady=(8, 0))
        self.close_button = ttk.Button(footer, text="Close", command=self._on_close,
                                       state="disabled")
        self.close_button.pack(side="right")
        self.cancel_button = ttk.Button(footer, text="Cancel", command=self._on_cancel)
        self.cancel_button.pack(side="right", padx=(0, 8))
        self.back_button = ttk.Button(footer, text="Change choices",
                                      command=self._on_back, state="disabled")
        self.back_button.pack(side="right", padx=(0, 8))
        self.save_button = ttk.Button(footer, text="Save log ...",
                                      command=self._on_save_log, state="disabled")
        self.save_button.pack(side="left")
        self.open_button = ttk.Button(footer, text="Open LAMF",
                                      command=self._on_open_workspace)
        self.open_button.pack(side="left", padx=(8, 0))
        self.open_button.pack_forget()

    def _append(self, text: str):
        tag = ""
        stripped = text.strip()
        if "[OK]" in stripped:
            tag = "ok"
        elif "[FAIL]" in stripped:
            tag = "fail"
        elif "[WARN]" in stripped:
            tag = "warn"
        elif stripped.startswith(("[Step", "===", "LAMF installer")) or set(stripped) == {"="}:
            tag = "head"
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n", tag)
        self.output.see("end")
        self.output.configure(state="disabled")

    # -- actions -----------------------------------------------------------
    def _collect_options(self) -> InstallOptions | None:
        from tkinter import messagebox

        data_dir = expand_path(self.var_data.get())
        install_dir = expand_path(self.var_install.get())
        if not str(self.var_data.get()).strip() or not str(self.var_install.get()).strip():
            messagebox.showerror(APP_TITLE, "Please choose both folders.", parent=self.root)
            return None
        if data_dir == install_dir or is_within(data_dir, install_dir):
            messagebox.showerror(APP_TITLE, (
                "Your memory folder must be separate from the program files, so "
                "upgrading LAMF can never touch your memories.\n\n"
                f"Memory folder: {data_dir}\nProgram files:  {install_dir}"),
                parent=self.root)
            return None

        obsidian = bool(self.var_obsidian.get())
        vault = expand_path(self.var_vault.get()) if obsidian else None
        if obsidian and not str(self.var_vault.get()).strip():
            messagebox.showerror(APP_TITLE, "Please choose an Obsidian vault folder.",
                                 parent=self.root)
            return None

        allow_git = False
        try:
            checkout = load_installer_core(self.source).git_checkout_root(data_dir)
        except Exception:  # noqa: BLE001
            checkout = None
        if checkout is not None:
            allow_git = messagebox.askyesno(APP_TITLE, (
                f"The memory folder you chose is inside a Git checkout:\n\n{checkout}\n\n"
                "That folder will hold your instance key, operator token and "
                "database — one commit away from being published.\n\n"
                "Choose 'No' to pick a different folder (recommended).\n"
                "Choose 'Yes' only if you are repairing an instance already there."),
                icon="warning", default="no", parent=self.root)
            if not allow_git:
                return None

        harnesses = tuple(hid for hid, var in self.harness_vars.items() if var.get())
        return InstallOptions(
            data_dir=data_dir,
            install_dir=install_dir,
            profile=self.var_profile.get(),
            harnesses=harnesses,
            obsidian=obsidian,
            vault=vault,
            git_vault=bool(self.var_git.get()) and obsidian,
            start_server=bool(self.var_start.get()),
            allow_git_data_dir=allow_git,
        )

    def _on_install(self):
        from tkinter import messagebox
        if self.python_info is None:
            messagebox.showerror(APP_TITLE, "No suitable Python was found yet.",
                                 parent=self.root)
            return
        opts = self._collect_options()
        if opts is None:
            return
        self.options = opts
        self._show(self.progress_page)
        self.progress.start(12)
        self.close_button.configure(state="disabled")
        self.back_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.save_button.configure(state="disabled")
        self.open_button.pack_forget()
        self.result_label.configure(text="", style="Result.TLabel")
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")

        self.job = InstallJob(opts, self.python_info, self.events, self.source)
        self.job.start()
        self.root.after(80, self._pump)

    def _pump(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "line":
                    self._append(str(payload))
                elif kind == "status":
                    self.status_label.configure(text=str(payload))
                elif kind == "done":
                    self._finish(payload)  # type: ignore[arg-type]
                    return
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def _finish(self, result: dict):
        self.progress.stop()
        self.progress.configure(mode="determinate", value=100 if result.get("ok") else 0)
        self.cancel_button.configure(state="disabled")
        self.close_button.configure(state="normal")
        self.back_button.configure(state="normal")
        self.save_button.configure(state="normal")
        message = str(result.get("message") or "")
        if result.get("ok"):
            self.status_label.configure(text="Finished.", style="Good.TLabel")
            self.result_label.configure(text="Success — " + message, style="Result.TLabel",
                                        foreground="#22683f")
            if self.options.start_server:
                self.open_button.pack(side="left", padx=(8, 0))
        elif result.get("cancelled"):
            self.status_label.configure(text="Cancelled.", style="Warn.TLabel")
            self.result_label.configure(text=message, foreground="#8a5a00")
        else:
            self.status_label.configure(text="Did not complete.", style="Bad.TLabel")
            self.result_label.configure(text="Not finished — " + message,
                                        foreground="#9b1c1c")
        self.job = None

    def _on_cancel(self):
        from tkinter import messagebox
        if self.job is None:
            return
        if messagebox.askyesno(APP_TITLE, (
                "Stop the installation?\n\nAnything already written stays on disk; "
                "re-running the installer repairs it."), parent=self.root):
            self.status_label.configure(text="Stopping ...")
            self.cancel_button.configure(state="disabled")
            threading.Thread(target=self.job.cancel, daemon=True).start()

    def _on_back(self):
        self._show(self.options_page)

    def _on_save_log(self):
        from tkinter import filedialog, messagebox
        target = filedialog.asksaveasfilename(
            parent=self.root, title="Save the installation log",
            defaultextension=".txt", initialfile="lamf-install-log.txt",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")])
        if not target:
            return
        try:
            Path(target).write_text(self.output.get("1.0", "end-1c"), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Could not save the log:\n{exc}",
                                 parent=self.root)

    def _on_open_workspace(self):
        url = getattr(load_installer_core(self.source), "LAMF_URL", "http://127.0.0.1:8734")
        import webbrowser
        webbrowser.open(url)

    def _on_close(self):
        from tkinter import messagebox
        if self.job is not None:
            if not messagebox.askyesno(APP_TITLE, (
                    "An installation is still running. Quit anyway?"), parent=self.root):
                return
            self.job.cancel()
        self.root.destroy()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--version" in argv:
        print(f"{APP_TITLE} {package_version()}")
        return 0
    _enable_dpi_awareness()
    try:
        import tkinter as tk
    except ImportError as exc:  # pragma: no cover - Windows always has Tk
        print(f"This installer needs Tk: {exc}", file=sys.stderr)
        return 1
    try:
        root = tk.Tk()
    except Exception as exc:  # frozen Tk startup failures otherwise disappear
        error_file = Path(os.environ.get("TEMP", ".")) / "LAMF-installer-startup-error.log"
        error_file.write_text(
            f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        return 1
    try:
        InstallerApp(root)
    except Exception as exc:  # noqa: BLE001 — a broken bundle must still explain itself
        error_file = Path(os.environ.get("TEMP", ".")) / "LAMF-installer-startup-error.log"
        error_file.write_text(
            f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        from tkinter import messagebox
        root.withdraw()
        messagebox.showerror(APP_TITLE,
                             f"The installer could not start:\n\n{type(exc).__name__}: {exc}")
        return 1
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
