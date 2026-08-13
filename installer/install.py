#!/usr/bin/env python3
"""
LAMF noob-proof installer — cross-platform core (stdlib only, Python >= 3.10).

One entry per OS wraps this file:
  install.sh              (macOS / Linux)
  Install-LAMF.ps1        (Windows)
  install-lamf.command    (macOS double-click)

Everything this installer does is idempotent: re-running it repairs or
upgrades an existing install. Every failure message names the exact fix.

Contract: DECISIONS.md §W-04. OpenClaw merge contract: §W-03 (verified
2026-07-30). This script must run BEFORE any project dependencies exist,
so it uses the Python standard library only.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Step 0: make sure we are running on Python >= 3.10 — re-exec if not.
# This runs before ANY other import beyond sys/os/shutil/subprocess.
# ---------------------------------------------------------------------------
import os
import shutil
import subprocess
import sys

MIN_PYTHON = (3, 10)


def _os_install_hints() -> str:
    """Exact one-line install commands per OS, for the 'no python' case."""
    if sys.platform == "darwin":
        return (
            "  Install Python with this one line (needs Homebrew, https://brew.sh):\n"
            "    brew install python@3.12"
        )
    if sys.platform == "win32":
        return (
            "  Install Python with this one line (in PowerShell):\n"
            "    winget install -e --id Python.Python.3.12"
        )
    return (
        "  Install Python with the one line for your distribution:\n"
        "    Debian/Ubuntu : sudo apt update && sudo apt install -y python3 python3-venv\n"
        "    Fedora        : sudo dnf install -y python3\n"
        "    Arch          : sudo pacman -S --needed python"
    )


def _python_version_of(exe: str, prefix: list[str]) -> tuple[int, int] | None:
    try:
        out = subprocess.run(
            [exe, *prefix, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if out.returncode != 0:
            return None
        major, minor = out.stdout.strip().split(".")[:2]
        return (int(major), int(minor))
    except Exception:
        return None


def _reexec_with_modern_python() -> None:
    """If this interpreter is too old, find python3.x and re-exec; else exit 1."""
    if sys.version_info[:2] >= MIN_PYTHON:
        return
    candidates: list[tuple[str, list[str]]] = [
        ("python3.13", []), ("python3.12", []), ("python3.11", []),
        ("python3.10", []), ("python3", []),
    ]
    if sys.platform == "win32":
        candidates.append(("py", ["-3"]))  # Windows pylauncher
    me = os.path.realpath(sys.executable or "")
    for exe, prefix in candidates:
        path = shutil.which(exe)
        if not path or os.path.realpath(path) == me:
            continue
        ver = _python_version_of(path, prefix)
        if ver and ver >= MIN_PYTHON:
            os.execv(path, [path, *prefix, os.path.abspath(__file__), *sys.argv[1:]])
    print()
    print("  LAMF needs Python 3.10 or newer, and we couldn't find it on this computer.")
    print(_os_install_hints())
    print()
    print("  Then re-run this installer the same way you just did.")
    sys.exit(1)


if __name__ == "__main__":
    _reexec_with_modern_python()
# (uninstall.py performs the same check itself before importing this module.)

# ---------------------------------------------------------------------------
# Now the full stdlib import set is safe.
# ---------------------------------------------------------------------------
import argparse
import hashlib
import json
import platform
import stat
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

VERSION = "2.0.0"
PLUGIN_ID = "lamf-memory"
LAMF_URL = "http://127.0.0.1:8734"
DEFAULT_DATA_DIR = "~/LAMF"
DEFAULT_VAULT = "~/LAMF Vault"
DEFAULT_PROFILE = "controlled"
PROFILES = ("locked", "controlled", "trusted-local", "open-local")
HARNESSES = ("codex", "claude", "kimi", "gemini", "grok", "openclaw", "hermes", "generic")
OPTIMIZATION_PACK_VERSION = "1.0.0"
OPTIMIZATION_PACK_NAME = f"LAMF-Optimizations-{OPTIMIZATION_PACK_VERSION}.zip"
OPTIMIZATION_PACK_SHA256 = "f9ef9b1f199b7d995c9f2ab27da0214e865b680e64afadc66093057f55fcdebd"
OPTIMIZATION_PACK_URL = (
    "https://github.com/AI-LUCI/LAMF-Optimizations/releases/download/"
    f"v{OPTIMIZATION_PACK_VERSION}/{OPTIMIZATION_PACK_NAME}"
)


# ---------------------------------------------------------------------------
# Chatty, kind terminal UI
# ---------------------------------------------------------------------------
class UI:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._use_color = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

    def _c(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self._use_color else text

    def banner(self, text: str) -> None:
        line = "=" * 64
        print()
        print(self._c("1;36", line))
        print(self._c("1;36", f"  {text}"))
        print(self._c("1;36", line))

    def step(self, n: int, total: int, text: str) -> None:
        print()
        print(self._c("1;34", f"[Step {n}/{total}] {text}"))

    def ok(self, text: str) -> None:
        print(self._c("32", f"  [OK]   {text}"))

    def info(self, text: str) -> None:
        print(f"  [..]   {text}")

    def warn(self, text: str) -> None:
        print(self._c("33", f"  [WARN] {text}"))

    def fail(self, text: str, fix: str | None = None) -> None:
        print(self._c("31", f"  [FAIL] {text}"))
        if fix:
            print(self._c("31", f"         Fix: {fix}"))

    def detail(self, text: str) -> None:
        if self.verbose:
            print(f"         {text}")

    def run(self, argv: list[str], *, cwd: Path | None = None,
            what: str, check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess:
        """Run a subprocess, chatty. Returns the CompletedProcess."""
        self.detail(f"$ {' '.join(str(a) for a in argv)}" + (f"   (cwd={cwd})" if cwd else ""))
        try:
            proc = subprocess.run(
                [str(a) for a in argv],
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            self.fail(f"'{what}' took too long and was stopped.")
            return subprocess.CompletedProcess(argv, 124, "", "timeout")
        if self.verbose and proc.stdout.strip():
            for line in proc.stdout.rstrip().splitlines():
                self.detail(f"| {line}")
        if self.verbose and proc.stderr.strip():
            for line in proc.stderr.rstrip().splitlines():
                self.detail(f"! {line}")
        if check and proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            self.fail(f"'{what}' failed (exit {proc.returncode}).")
            for line in tail[-5:]:
                print(f"         {line}")
        return proc


# ---------------------------------------------------------------------------
# Paths and small helpers
# ---------------------------------------------------------------------------
def package_root() -> Path:
    """<pkg>/installer/install.py -> <pkg>"""
    return Path(__file__).resolve().parent.parent


def runtime_dir() -> Path:
    return package_root() / "runtime"


def venv_dir() -> Path:
    """Venv location. Default <pkg>/runtime/.venv; if the package lives on a
    filesystem that cannot host a venv (no symlinks: some NAS/sync/fuse mounts),
    the installer falls back to <data-dir>/.venv. LAMF_VENV overrides both."""
    override = os.environ.get("LAMF_VENV")
    if override:
        return Path(override).expanduser()
    primary = runtime_dir() / ".venv"
    if primary.exists():
        return primary
    alt = Path(os.environ.get("LAMF_DATA_DIR", DEFAULT_DATA_DIR)).expanduser() / ".venv"
    if alt.exists():
        return alt
    return primary


def venv_python() -> Path:
    if sys.platform == "win32":
        return venv_dir() / "Scripts" / "python.exe"
    return venv_dir() / "bin" / "python"


def expand(p: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(p))).resolve()


def git_checkout_root(path: Path) -> Path | None:
    """Nearest ancestor of `path` (inclusive) that is a Git checkout, else None.

    Deliberately does NOT shell out to `git`: the data/Git boundary must hold on
    machines where Git is not installed, which is exactly where a stray checkout
    is most likely to go unnoticed. A worktree or submodule uses a `.git` FILE
    rather than a directory, so both are accepted."""
    try:
        candidate = path.resolve()
    except OSError:
        candidate = path
    for parent in (candidate, *candidate.parents):
        if (parent / ".git").exists():
            return parent
    return None


def is_tty() -> bool:
    return sys.stdin.isatty()


def confirm(prompt: str, *, default: bool = False) -> bool:
    if not is_tty():
        return default
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        ans = input(prompt + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not ans:
        return default
    return ans in ("y", "yes")


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------
def step_environment(ui: UI) -> None:
    """(1) Report OS / python. Re-exec already handled old interpreters."""
    ui.info(f"OS: {platform.system()} {platform.release()} ({platform.machine()})")
    ui.info(f"Python: {sys.version.split()[0]} at {sys.executable}")
    ui.info(f"Package: {package_root()}")
    if not (runtime_dir() / "lamf").is_dir():
        ui.warn(
            "The LAMF runtime (runtime/lamf/) is not present in this package yet. "
            "I will set up everything I can, and the steps that need the runtime "
            "will tell you exactly what is missing."
        )


def step_venv(ui: UI, data_dir: Path) -> bool:
    """(2) Create the venv (package dir, with data-dir fallback) + install deps."""
    req = runtime_dir() / "requirements.txt"
    candidates = [runtime_dir() / ".venv", data_dir / ".venv"]
    py = venv_python()
    if py.is_file():
        ui.ok(f"Virtual environment already exists: {venv_dir()}")
    else:
        created = False
        for cand in candidates:
            ui.info(f"Creating virtual environment at {cand} ...")
            proc = ui.run([sys.executable, "-m", "venv", str(cand)],
                          what="python -m venv", check=False)
            ok = proc.returncode == 0 and (
                (cand / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")).is_file())
            if not ok and os.name != "nt":
                # Retry with --copies: some filesystems (fuse, network drives,
                # NAS/sync folders) do not support the symlinks venv creates.
                ui.info("Retrying with --copies (this filesystem does not support symlinks) ...")
                shutil.rmtree(cand, ignore_errors=True)
                proc = ui.run([sys.executable, "-m", "venv", "--copies", str(cand)],
                              what="python -m venv --copies", check=False)
                ok = proc.returncode == 0 and (
                    (cand / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")).is_file())
            if ok:
                os.environ["LAMF_VENV"] = str(cand)
                created = True
                break
            ui.info(f"That location did not work; trying the next one ...")
            shutil.rmtree(cand, ignore_errors=True)
        if not created:
            ui.fail(
                "Could not create the virtual environment.",
                fix=("on Debian/Ubuntu run: sudo apt install -y python3-venv  then re-run this installer. "
                     "On macOS: brew install python@3.12. On Windows: reinstall Python from python.org "
                     "with the 'py launcher' option."),
            )
            return False
        py = venv_python()
        ui.ok(f"Virtual environment created: {venv_dir()}")

    if not req.is_file():
        ui.fail(
            f"Dependency list not found: {req}",
            fix="make sure you have the complete LAMF package (the runtime/ folder must be next to installer/), then re-run this installer.",
        )
        return False

    ui.info("Installing dependencies (pyyaml + pynacl only) into the venv ...")
    proc = ui.run(
        [str(py), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(req)],
        what="pip install -r runtime/requirements.txt", check=False, timeout=900,
    )
    if proc.returncode != 0:
        ui.fail(
            "pip could not install the dependencies (usually a network problem).",
            fix=("check your internet connection and re-run this installer. "
                 "OFFLINE workaround: on a machine with internet run "
                 "'pip download pyyaml pynacl -d wheels', copy the wheels/ folder here, then run: "
                 f"{py} -m pip install --no-index --find-links wheels pyyaml pynacl"),
        )
        return False

    probe = ui.run([str(py), "-c", "import yaml, nacl; print('deps ok')"],
                   what="dependency import probe", check=False)
    if probe.returncode != 0:
        ui.fail("Dependencies installed but cannot be imported.",
                fix=f"re-run: {py} -m pip install --force-reinstall pyyaml pynacl")
        return False
    ui.ok("Dependencies installed and importable.")
    return True


def lamf_cli(ui: UI, *cli_args: str, what: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run `python -m lamf.cli ...` with the runtime dir as cwd."""
    return ui.run([str(venv_python()), "-m", "lamf.cli", *cli_args],
                  cwd=runtime_dir(), what=what, check=check)


def is_initialized(data_dir: Path) -> bool:
    # Marker follows the runtime's init layout (DECISIONS.md §W-02: init creates
    # state/, spool/, payload store, actors). The operator token is written by
    # the bootstrap pairing, so both together mean "initialized".
    return (data_dir / "state").is_dir() or (data_dir / "operator.token").is_file()


def step_init(ui: UI, data_dir: Path, profile: str, reset: bool) -> str:
    """(3) lamf init (idempotent; --reset re-initializes after confirmation).

    Returns "fresh" | "existing" | "failed".
    """
    if reset and data_dir.exists():
        if not confirm(f"  --reset will ERASE all LAMF data in {data_dir}. Continue?", default=False):
            ui.warn("Reset cancelled; keeping existing data.")
        else:
            shutil.rmtree(data_dir)
            ui.info(f"Erased {data_dir}")

    if is_initialized(data_dir):
        ui.ok(f"LAMF data directory already initialized: {data_dir} (skipping init)")
        return "existing"

    data_dir.mkdir(parents=True, exist_ok=True)
    proc = lamf_cli(ui, "init", "--profile", profile, "--data-dir", str(data_dir),
                    what="lamf init", check=False)
    if proc.returncode != 0:
        if not (runtime_dir() / "lamf").is_dir():
            ui.fail(
                "The LAMF runtime is not built into this package yet, so 'init' cannot run.",
                fix="re-run this installer once the runtime/ folder is complete — it will pick up right here.",
            )
        else:
            ui.fail(
                "'lamf init' failed.",
                fix=f"run it by hand to see the full error: cd {runtime_dir()} && {venv_python()} -m lamf.cli init --profile {profile} --data-dir \"{data_dir}\"",
            )
        return "failed"
    ui.ok(f"Initialized {data_dir} (profile={profile})")
    return "fresh"


def step_token(ui: UI, data_dir: Path, fresh: bool) -> str | None:
    """(4) Show the operator token ONCE (first init only) with a keep-it-safe note."""
    token_file = data_dir / "operator.token"
    if not token_file.is_file():
        ui.warn(f"Operator token not found at {token_file} (init may not have completed).")
        return None
    if not fresh:
        ui.ok(f"Operator token is in place: {token_file} (0600; not shown again)")
        return token_file.read_text(encoding="utf-8").strip()
    try:
        token_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass  # Windows ACLs differ; the runtime still guards the file.
    token = token_file.read_text(encoding="utf-8").strip()
    print()
    print("  +------------------------------------------------------------------+")
    print("  |  YOUR LAMF OPERATOR TOKEN (shown this one time — keep it safe)   |")
    print("  +------------------------------------------------------------------+")
    print(f"    {token}")
    print()
    print(f"  It also lives in {token_file} (permissions 0600).")
    print("  Anyone with this token can read your memory. Do not post it anywhere.")
    return token


def step_vault(ui: UI, vault: Path) -> bool:
    """(5) Create the Obsidian vault and run the first full projection."""
    vault.mkdir(parents=True, exist_ok=True)
    home_note = vault / "00 Home.md"
    if home_note.is_file():
        ui.ok(f"Vault already projected: {vault} (00 Home.md present)")
        return True
    proc = lamf_cli(ui, "project", "--vault", str(vault),
                    what="lamf project (first full projection)", check=False)
    if proc.returncode != 0:
        if not (runtime_dir() / "lamf").is_dir():
            ui.warn("Runtime not present yet — the first projection will run on the next installer re-run.")
        else:
            ui.fail("First projection failed.",
                    fix=f"cd {runtime_dir()} && {venv_python()} -m lamf.cli project --vault \"{vault}\"")
        return False
    ui.ok(f"Vault ready: {vault}")
    return True


START_SH = """#!/usr/bin/env bash
# start-lamf.sh — start the standalone LAMF workspace{projection_comment}.
# Generated by installer/install.py; safe to re-run (idempotent).
set -euo pipefail
RUNTIME={runtime!r}
VENV_PY={venv_py!r}
LOGS={logs!r}
RUN={run!r}
mkdir -p "$LOGS" "$RUN"
cd "$RUNTIME"
start_one() {{
  local name="$1"; shift
  local pidfile="$RUN/$name.pid"
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "lamf $name already running (pid $(cat "$pidfile"))"
    return 0
  fi
  nohup "$VENV_PY" -m lamf.cli "$@" >>"$LOGS/$name.log" 2>&1 &
  echo $! > "$pidfile"
  echo "lamf $name started (pid $(cat "$pidfile"), log: $LOGS/$name.log)"
}}
{start_commands}
echo "LAMF is running. Stop it with: {stop_sh_plain}"
"""

STOP_SH = """#!/usr/bin/env bash
# stop-lamf.sh — stop the LAMF server and vault watcher.
# Generated by installer/install.py.
set -uo pipefail
RUN={run!r}
stopped=0
for name in serve watch; do
  pidfile="$RUN/$name.pid"
  if [ -f "$pidfile" ]; then
    pid="$(cat "$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null && echo "stopped lamf $name (pid $pid)" && stopped=1
    fi
    rm -f "$pidfile"
  fi
done
[ "$stopped" = "1" ] || echo "LAMF was not running."
"""

START_PS1 = """# start-lamf.ps1 — start the standalone LAMF workspace{projection_comment}.
# Generated by installer/install.py; safe to re-run (idempotent).
$Runtime = {runtime_ps}
$VenvPy  = {venv_py_ps}
$Logs    = {logs_ps}
$Run     = {run_ps}
New-Item -ItemType Directory -Force $Logs, $Run | Out-Null
function Start-LamfOne($name, $lamfArgs) {{
  $pidfile = Join-Path $Run "$name.pid"
  if ((Test-Path $pidfile) -and (Get-Process -Id ([int](Get-Content $pidfile)) -ErrorAction SilentlyContinue)) {{
    Write-Host "lamf $name already running (pid $(Get-Content $pidfile))"
    return
  }}
  $log = Join-Path $Logs "$name.log"
  $p = Start-Process -FilePath $VenvPy -ArgumentList (@('-m','lamf.cli') + $lamfArgs) `
       -WorkingDirectory $Runtime -RedirectStandardOutput $log -RedirectStandardError "$log.err" `
       -WindowStyle Hidden -PassThru
  $p.Id | Out-File -Encoding ascii $pidfile
  Write-Host "lamf $name started (pid $($p.Id), log: $log)"
}}
{start_commands}
Write-Host "LAMF is running. Stop it with: {stop_ps1_plain}"
"""

STOP_PS1 = """# stop-lamf.ps1 — stop the LAMF server and vault watcher.
# Generated by installer/install.py.
$Run = {run_ps}
$stopped = $false
foreach ($name in 'serve','watch') {{
  $pidfile = Join-Path $Run "$name.pid"
  if (Test-Path $pidfile) {{
    $procId = [int](Get-Content $pidfile)
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($p) {{ Stop-Process -Id $procId -Force; Write-Host "stopped lamf $name (pid $procId)"; $stopped = $true }}
    Remove-Item $pidfile -Force
  }}
}}
if (-not $stopped) {{ Write-Host "LAMF was not running." }}
"""


def ps_quote(p: Path) -> str:
    """Single-quoted PowerShell string literal."""
    return "'" + str(p).replace("'", "''") + "'"


def write_helper_scripts(ui: UI, data_dir: Path, vault: Path | None) -> dict[str, Path]:
    """(6a) Write start-lamf / stop-lamf helpers (sh + ps1) into <data-dir>/bin."""
    bin_dir = data_dir / "bin"
    logs = data_dir / "logs"
    run = data_dir / "run"
    bin_dir.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    run.mkdir(parents=True, exist_ok=True)

    paths = {
        "start_sh": bin_dir / "start-lamf.sh",
        "stop_sh": bin_dir / "stop-lamf.sh",
        "start_ps1": bin_dir / "start-lamf.ps1",
        "stop_ps1": bin_dir / "stop-lamf.ps1",
    }
    if vault is not None:
        sh_commands = (f"start_one serve serve --data-dir {str(data_dir)!r} --vault {str(vault)!r}\n"
                       f"start_one watch watch --data-dir {str(data_dir)!r} --vault {str(vault)!r}")
        ps_commands = (f"Start-LamfOne 'serve' @('serve','--data-dir',{ps_quote(data_dir)},'--vault',{ps_quote(vault)})\n"
                       f"Start-LamfOne 'watch' @('watch','--data-dir',{ps_quote(data_dir)},'--vault',{ps_quote(vault)})")
        projection_comment = " and optional Obsidian projection"
    else:
        sh_commands = f"start_one serve serve --data-dir {str(data_dir)!r}"
        ps_commands = f"Start-LamfOne 'serve' @('serve','--data-dir',{ps_quote(data_dir)})"
        projection_comment = ""
    paths["start_sh"].write_text(START_SH.format(
        runtime=str(runtime_dir()), venv_py=str(venv_python()),
        logs=str(logs), run=str(run), stop_sh_plain=str(paths["stop_sh"]),
        projection_comment=projection_comment, start_commands=sh_commands,
    ), encoding="utf-8")
    paths["stop_sh"].write_text(STOP_SH.format(run=str(run)), encoding="utf-8")
    paths["start_ps1"].write_text(START_PS1.format(
        runtime_ps=ps_quote(runtime_dir()), venv_py_ps=ps_quote(venv_python()),
        logs_ps=ps_quote(logs), run_ps=ps_quote(run), stop_ps1_plain=str(paths["stop_ps1"]),
        projection_comment=projection_comment, start_commands=ps_commands,
    ), encoding="utf-8")
    paths["stop_ps1"].write_text(STOP_PS1.format(run_ps=ps_quote(run)), encoding="utf-8")
    for key in ("start_sh", "stop_sh"):
        paths[key].chmod(0o755)
    ui.ok(f"Helper scripts written to {bin_dir} (start-lamf / stop-lamf, sh + ps1)")
    return paths


def write_harness_registrations(ui: UI, data_dir: Path,
                                selected: tuple[str, ...]) -> Path:
    """Emit portable registrations for every supported client without applying
    or overwriting any host configuration."""
    sys.path.insert(0, str(runtime_dir()))
    from lamf.harness import HARNESSES as REGISTRY, render
    out = data_dir / "adapters"
    out.mkdir(parents=True, exist_ok=True)
    extensions = {hid: h.format for hid, h in REGISTRY.items()}
    for old in out.glob("*.toml"):
        old.unlink()
    for old in out.glob("*.json"):
        old.unlink()
    for old in out.glob("*.yaml"):
        old.unlink()
    for harness_id in selected:
        target = out / f"{harness_id}.{extensions[harness_id]}"
        target.write_text(render(harness_id, runtime_dir(), data_dir) + "\n",
                          encoding="utf-8")
    (out / "selection.json").write_text(
        json.dumps({"harnesses": list(selected), "shared_data_dir": str(data_dir)}, indent=2) + "\n",
        encoding="utf-8")
    if selected:
        ui.ok(f"Harness registrations written for {', '.join(selected)}: {out}")
    else:
        ui.ok("No agent harness selected. LAMF CLI and Obsidian remain fully available.")
    return out


# Harnesses the installer can merge directly into a host config file. OpenClaw
# is handled separately by step_openclaw (plugin + memory slot + MCP fallback +
# skill, DECISIONS.md §W-03); "generic" has no default config location and is
# emitted as a snippet only. Every merge backs up the target first and
# preserves unrelated settings (DECISIONS.md §W-07).
APPLYABLE_HARNESSES = ("codex", "claude", "kimi", "gemini", "grok", "hermes")


def apply_harness_registrations(ui: UI, data_dir: Path,
                                selected: tuple[str, ...]) -> dict:
    """Actually merge selected harnesses into their host configs (safe merge).

    Returns a {harness_id: "applied" | "skipped" | "failed"} map. Failures are
    reported with an exact fix and never abort the install — the emitted
    snippets under <data-dir>/adapters/ remain the portable fallback.
    """
    sys.path.insert(0, str(runtime_dir()))
    from lamf import harness as h
    results: dict[str, str] = {}
    for hid in selected:
        if hid in ("openclaw", "generic"):
            # openclaw: step_openclaw owns the full registration.
            # generic: no default config location; snippet is the deliverable.
            results[hid] = "skipped"
            continue
        target = h.default_config_path(hid)
        try:
            res = h.apply(hid, runtime_dir(), data_dir, target)
            if hid == "codex":
                install_codex_startup(ui)
                verify_codex_activation(runtime_dir(), data_dir)
            results[hid] = "applied"
            ui.ok(f"{hid}: merged into {res['config']}"
                  + (f" (backup: {res['backup']})" if res.get("backup") else ""))
        except Exception as exc:  # noqa: BLE001 — report and continue
            results[hid] = "failed"
            ui.warn(f"{hid}: could not update {target} ({exc}). "
                    f"The portable snippet is in {data_dir / 'adapters'}; "
                    f"or run: lamf harness apply {hid}")
    return results


def install_codex_startup(ui: UI, codex_home: Path | None = None) -> dict[str, Path]:
    """Install profile-level startup guidance independent of the signed-in account."""
    home = Path(codex_home or (Path.home() / ".codex"))
    source = package_root() / "05_INTEGRATIONS" / "codex"
    agents_source = (source / "AGENTS.md").read_text(encoding="utf-8").strip()
    skill_source = source / "skill" / "SKILL.md"
    begin, end = "<!-- BEGIN LAMF MANAGED -->", "<!-- END LAMF MANAGED -->"
    agents = home / "AGENTS.md"
    old = agents.read_text(encoding="utf-8") if agents.exists() else ""
    if old.count(begin) != old.count(end) or old.count(begin) > 1:
        raise ValueError(f"malformed LAMF managed guidance in {agents}")
    block = f"{begin}\n{agents_source}\n{end}"
    if begin in old:
        prefix, rest = old.split(begin, 1)
        _, suffix = rest.split(end, 1)
        updated = prefix.rstrip() + ("\n\n" if prefix.strip() else "") + block + suffix
    else:
        updated = old.rstrip() + ("\n\n" if old.strip() else "") + block + "\n"
    if agents.exists() and old != updated:
        backup_file(ui, agents)
    _atomic_text_write(agents, updated)
    skill = home / "skills" / "lamf-memory" / "SKILL.md"
    if skill.exists() and skill.read_bytes() != skill_source.read_bytes():
        backup_file(ui, skill)
    skill.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_source, skill)
    ui.ok(f"Codex startup guidance installed for this Windows profile: {agents}")
    return {"agents": agents, "skill": skill}


def _atomic_text_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def verify_codex_activation(runtime: Path, data_dir: Path) -> None:
    """Prove the installed registration works from an unrelated directory."""
    sys.path.insert(0, str(runtime))
    from lamf.harness import server_spec
    spec = server_spec(runtime, data_dir, "codex")
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "lamf-installer-verifier", "version": VERSION}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    env = os.environ.copy()
    env.update({str(k): str(v) for k, v in spec["env"].items()})
    proc = subprocess.run(
        [spec["command"], *spec["args"]],
        input=("\n".join(json.dumps(item) for item in requests) + "\n").encode("utf-8"),
        capture_output=True, env=env,
        cwd=spec["cwd"], timeout=30,
    )
    if proc.returncode != 0:
        error = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Codex MCP startup failed: {error[:400]}")
    output = proc.stdout.decode("utf-8", errors="replace")
    replies = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    tools = next((r for r in replies if r.get("id") == 2), {}).get("result", {}).get("tools", [])
    names = {item.get("name") for item in tools}
    required = {"memory_orientation", "memory_search", "memory_remember", "memory_status"}
    if not required <= names:
        raise RuntimeError(f"Codex MCP tool list incomplete: {sorted(names)}")


def install_optimization_pack(ui: UI, data_dir: Path) -> dict:
    """Install the pinned, checksum-verified optimization pack and enable it."""
    bundled = package_root() / "vendor" / OPTIMIZATION_PACK_NAME
    archive = bundled
    if not archive.is_file():
        cache = Path(data_dir) / "run" / OPTIMIZATION_PACK_NAME
        cache.parent.mkdir(parents=True, exist_ok=True)
        ui.info(f"Downloading LAMF Optimizations v{OPTIMIZATION_PACK_VERSION}...")
        urllib.request.urlretrieve(OPTIMIZATION_PACK_URL, cache)
        archive = cache
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != OPTIMIZATION_PACK_SHA256:
        raise RuntimeError("LAMF optimization pack checksum mismatch; refusing to install it")
    target = package_root() / "optimizations"
    with zipfile.ZipFile(archive) as zf:
        members = [m for m in zf.infolist()
                   if m.filename.startswith("optimizations/") and not m.is_dir()]
        if not members:
            raise RuntimeError("LAMF optimization pack contains no modules")
        for member in members:
            rel = Path(member.filename).relative_to("optimizations")
            destination = (target / rel).resolve()
            if target.resolve() not in destination.parents:
                raise RuntimeError(f"unsafe optimization archive member: {member.filename}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, destination.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    sys.path.insert(0, str(runtime_dir()))
    from lamf import optimizations
    optimizations.initialize(data_dir)
    status = optimizations.status(data_dir)
    valid = [m for m in status["modules"] if not m.get("error")]
    if not valid or not status["enabled"]:
        raise RuntimeError("LAMF optimizations installed but no valid enabled modules were found")
    ui.ok(f"Full optimization pack enabled: {len(valid)} modules")
    return status


def choose_harnesses(requested: list[str] | None, *, interactive: bool) -> tuple[str, ...]:
    """Resolve installer harness scope. Empty is a first-class supported mode."""
    if requested:
        values = [v.lower() for v in requested]
        if "none" in values:
            return ()
        if "all" in values:
            return HARNESSES
        return tuple(dict.fromkeys(v for v in values if v in HARNESSES))
    if not interactive:
        return ()
    print()
    print("  Which agent harnesses should use this memory?")
    print("  Enter names separated by commas, 'all', or press Enter for none.")
    print(f"  Choices: {', '.join(HARNESSES)}")
    answer = input("  Harnesses [none]: ").strip().lower()
    if not answer or answer == "none":
        return ()
    if answer == "all":
        return HARNESSES
    return tuple(dict.fromkeys(v.strip() for v in answer.split(",") if v.strip() in HARNESSES))


GITIGNORE = """# LAMF cloud-project Git scope
.obsidian/workspace*
.obsidian/cache/
06 Security/
07 Review Queue/
08 Drafts/
09 Operator Notes/
99 System/
*.lamf
*.token
*.key
"""


def setup_git_vault(ui: UI, vault: Path, mode: str) -> bool:
    """Optionally make the policy-filtered Obsidian projection a local Git repo.
    Never configures a remote and never includes the authority/data directory."""
    if mode == "none":
        ui.info("Git project sharing not selected; nothing to configure.")
        return True
    git = shutil.which("git")
    if not git:
        ui.warn("Git sharing selected, but Git is not installed. LAMF still works normally.")
        return False
    vault.mkdir(parents=True, exist_ok=True)
    (vault / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    (vault / "GIT_SCOPE.md").write_text(
        "# LAMF Git projection\n\nThis repository is a policy-filtered Obsidian projection. "
        "It is not the LAMF database. Do not add the LAMF data directory, keys, tokens, "
        "event spine, review queue, drafts, operator notes, or security reports.\n",
        encoding="utf-8")
    proc = ui.run([git, "init", str(vault)], what="git init Obsidian projection", check=False)
    if proc.returncode != 0:
        ui.warn("Could not initialize the optional Git projection; LAMF is unaffected.")
        return False
    ui.ok(f"Local Git projection ready: {vault} (no remote and nothing pushed)")
    return True


def _url_up(url: str) -> bool:
    """Any HTTP response (even 401) means the server is up."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3):
            return True
    except urllib.error.HTTPError:
        return True  # reached the server; auth/status detail does not matter here
    except Exception:
        return False


def server_up(timeout_s: float = 0.0) -> bool:
    return _url_up(LAMF_URL + "/v1/status")


def step_start(ui: UI, helpers: dict[str, Path], no_start: bool) -> bool:
    """(6b) Start serve + watch now, detached."""
    if no_start:
        ui.info("--no-start given; not starting the server now.")
        return True
    if server_up():
        ui.ok(f"LAMF server already responding at {LAMF_URL}")
        return True
    ui.info("Starting the LAMF server and vault watcher in the background ...")
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                 str(helpers["start_ps1"])],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,  # type: ignore[attr-defined]
            )
        else:
            subprocess.Popen(
                ["bash", str(helpers["start_sh"])],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except OSError as exc:
        ui.fail(f"Could not launch the start script: {exc}",
                fix=f"run it yourself: {helpers['start_sh']}")
        return False
    deadline = time.time() + 15
    while time.time() < deadline:
        if server_up():
            ui.ok(f"LAMF server is up at {LAMF_URL} (logs: see helper script folder)")
            return True
        time.sleep(1)
    logs_dir = helpers["start_sh"].parent.parent / "logs"
    ui.warn(
        "The server did not answer within 15 seconds. It may still be starting; "
        f"check the logs in {logs_dir} or run "
        f"{helpers['start_sh']} by hand. (If the runtime is not built yet, this is expected.)"
    )
    return False


# ---------------------------------------------------------------------------
# (7) OpenClaw registration (DECISIONS.md §W-03 verified contract, 2026-07-30)
# ---------------------------------------------------------------------------
def openclaw_config_path() -> Path:
    return Path.home() / ".openclaw" / "openclaw.json"


def backup_file(ui: UI, path: Path) -> Path | None:
    """Timestamped backup with 0600 perms before any edit (installer contract)."""
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = path.with_name(f"{path.name}.bak-{ts}")
    shutil.copy2(path, bak)
    try:
        bak.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    ui.detail(f"backup: {bak}")
    return bak


def step_openclaw(ui: UI, data_dir: Path, no_openclaw: bool, vault: Path | None = None) -> str:
    """Register the plugin + memory slot + MCP fallback + skill.

    Returns "registered" | "openclaw-missing" | "skipped" | "failed".
    """
    if no_openclaw:
        ui.info("--no-openclaw given; skipping OpenClaw registration.")
        return "skipped"
    if shutil.which("openclaw") is None:
        ui.info("OpenClaw is not installed on this computer — no problem.")
        print()
        print("    Install OpenClaw later, then re-run this installer — it will")
        print("    register LAMF with OpenClaw automatically. Install OpenClaw with:")
        if sys.platform == "win32":
            print("      iwr -useb https://openclaw.ai/install.ps1 | iex")
        else:
            print("      curl -fsSL https://openclaw.ai/install.sh | bash")
        print("      openclaw onboard --install-daemon")
        return "openclaw-missing"

    plugin_dir = package_root() / "05_INTEGRATIONS" / "openclaw-plugin"
    plugin_entry = plugin_dir / "index.ts"
    cfg_path = openclaw_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    config: dict = {}
    if cfg_path.exists():
        try:
            config = json.loads(cfg_path.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError("top level is not an object")
        except (json.JSONDecodeError, ValueError) as exc:
            backup_file(ui, cfg_path)
            ui.fail(
                f"Your OpenClaw config at {cfg_path} is not valid JSON ({exc}). "
                "I made a backup and did NOT touch it.",
                fix="fix the JSON (or restore the .bak file), then re-run this installer.",
            )
            return "failed"

    backup_file(ui, cfg_path)

    # --- merge, never overwrite unrelated config (installer contract) ------
    # Type-guarded setdefault: a valid-JSON but wrong-shape value (backup was
    # already made) is replaced with the correct container instead of crashing.
    def _obj(parent: dict, key: str) -> dict:
        v = parent.setdefault(key, {})
        if not isinstance(v, dict):
            v = parent[key] = {}
        return v

    plugins = _obj(config, "plugins")
    load = _obj(plugins, "load")
    paths = load.setdefault("paths", [])
    if not isinstance(paths, list):
        paths = load["paths"] = []
    entry_str = str(plugin_entry)
    if entry_str not in paths:
        paths.append(entry_str)

    entries = _obj(plugins, "entries")
    entry = _obj(entries, PLUGIN_ID)
    entry["enabled"] = True
    hooks = _obj(entry, "hooks")
    # Required so before_prompt_build / agent_end hooks fire for a
    # non-bundled plugin (verified contract).
    hooks["allowConversationAccess"] = True
    entry_config = _obj(entry, "config")
    entry_config.setdefault("lamfUrl", LAMF_URL)
    # Write tokenFile explicitly so a custom --data-dir is honored.
    entry_config["tokenFile"] = str(data_dir / "operator.token")
    # R4-16: record the vault so a bare installer re-run can adopt the
    # existing instance's paths instead of falling back to defaults.
    if vault is not None:
        entry_config["vault"] = str(vault)
    entry_config.setdefault("captureEnabled", True)
    entry_config.setdefault("injectContext", True)
    entry_config.setdefault("maxContextTokens", 2000)

    slots = _obj(plugins, "slots")
    slots["memory"] = PLUGIN_ID

    # --- MCP fallback (used if the plugin cannot load) ---------------------
    mcp = _obj(config, "mcp")
    servers = _obj(mcp, "servers")
    servers["lamf"] = {
        "command": str(venv_python()),
        # R4-15: launch through the CLI so the server attaches the real store,
        # policy, spine and ingester for THIS data dir (the bare
        # `lamf.mcp_server` module entrypoint serves tools with store=None).
        "args": ["-m", "lamf.cli", "mcp", "--data-dir", str(data_dir)],
        "env": {"LAMF_DATA_DIR": str(data_dir)},
        "transport": "stdio",
        "enabled": True,
        "cwd": str(runtime_dir()),
    }

    tmp = cfg_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    tmp.replace(cfg_path)  # atomic on same filesystem
    ui.ok(f"OpenClaw config merged (backup made, unrelated settings preserved): {cfg_path}")

    # --- skill -------------------------------------------------------------
    skill_src = plugin_dir / "skill" / "SKILL.md"
    skill_dir = Path.home() / ".openclaw" / "workspace" / "skills" / PLUGIN_ID
    skill_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_src, skill_dir / "SKILL.md")
    ui.ok(f"Agent skill installed: {skill_dir / 'SKILL.md'}")
    return "registered"


def unregister_openclaw(ui: UI) -> bool:
    """Remove LAMF-owned keys from openclaw.json (used by uninstall.py logic
    and kept here so both stay in sync). Returns True if anything changed."""
    cfg_path = openclaw_config_path()
    if not cfg_path.exists():
        return False
    try:
        config = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        ui.warn(f"{cfg_path} is not valid JSON; leaving it untouched.")
        return False
    changed = False
    plugins = config.get("plugins") or {}
    entry_str = str(package_root() / "05_INTEGRATIONS" / "openclaw-plugin" / "index.ts")
    paths = ((plugins.get("load") or {}).get("paths")) or []
    if entry_str in paths:
        paths.remove(entry_str)
        changed = True
    if (plugins.get("entries") or {}).pop(PLUGIN_ID, None) is not None:
        changed = True
    slots = plugins.get("slots") or {}
    if slots.get("memory") == PLUGIN_ID:
        del slots["memory"]
        changed = True
    servers = ((config.get("mcp") or {}).get("servers")) or {}
    if servers.pop("lamf", None) is not None:
        changed = True
    if changed:
        backup_file(ui, cfg_path)
        cfg_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    skill_dir = Path.home() / ".openclaw" / "workspace" / "skills" / PLUGIN_ID
    if skill_dir.is_dir():
        shutil.rmtree(skill_dir)
        changed = True
    return changed


# ---------------------------------------------------------------------------
# (8) Doctor — every ❌ prints its exact fix command
# ---------------------------------------------------------------------------
class Doctor:
    def __init__(self, ui: UI):
        self.ui = ui
        self.failures = 0
        self.warnings = 0

    def check(self, ok: bool, label: str, *, fix: str | None = None,
              warn_only: bool = False, detail: str | None = None) -> bool:
        if ok:
            self.ui.ok(label + (f" — {detail}" if detail else ""))
        elif warn_only:
            self.warnings += 1
            self.ui.warn(label + (f" — {detail}" if detail else ""))
            if fix:
                print(f"         Fix: {fix}")
        else:
            self.failures += 1
            self.ui.fail(label, fix=fix)
        return ok


def obsidian_found() -> bool:
    if sys.platform == "darwin":
        return Path("/Applications/Obsidian.app").exists()
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        return bool(local) and (Path(local) / "Obsidian" / "Obsidian.exe").exists()
    return (
        shutil.which("obsidian") is not None
        or any((Path.home() / ".local/share/applications").glob("obsidian*.desktop"))
        or Path("/var/lib/flatpak/app/md.obsidian.Obsidian").exists()
        or Path("/snap/bin/obsidian").exists()
    )


def on_windows_drive_mount(path: Path) -> bool:
    """True when `path` lives on a Windows drive mounted into WSL (drvfs/9p,
    e.g. /mnt/y/...). Such mounts do not persist Linux permission bits."""
    try:
        target = str(path.resolve())
        best, best_fs = "", ""
        with open("/proc/mounts", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 3 and target.startswith(parts[1]) and len(parts[1]) >= len(best):
                    best, best_fs = parts[1], parts[2]
        return best_fs in ("drvfs", "9p")
    except Exception:
        return False


def run_doctor(ui: UI, data_dir: Path, vault: Path | None,
               openclaw_state: str, server_expected: bool = True) -> Doctor:
    d = Doctor(ui)
    py = venv_python()

    d.check(sys.version_info[:2] >= MIN_PYTHON,
            f"Python {sys.version.split()[0]} (>= 3.10 required)",
            fix=_os_install_hints())

    deps_ok = py.is_file() and ui.run(
        [str(py), "-c", "import yaml, nacl"], what="doctor: deps", check=False).returncode == 0
    d.check(deps_ok, "Virtual environment + dependencies (pyyaml, pynacl)",
            fix=f"re-run this installer, or by hand: {sys.executable} -m venv {venv_dir()} && "
                f"{py} -m pip install -r {runtime_dir() / 'requirements.txt'}")

    d.check(is_initialized(data_dir), f"Data directory initialized: {data_dir}",
            fix=f"cd {runtime_dir()} && {py} -m lamf.cli init --profile {DEFAULT_PROFILE} --data-dir \"{data_dir}\"  (or re-run this installer)")

    token_file = data_dir / "operator.token"
    token_ok = token_file.is_file()
    if token_ok and sys.platform != "win32" and not on_windows_drive_mount(token_file):
        mode = stat.S_IMODE(token_file.stat().st_mode)
        if mode != 0o600:
            token_ok = False
            d.check(False, f"Operator token permissions are {oct(mode)}, want 0600",
                    fix=f"chmod 600 \"{token_file}\"")
    if not token_file.is_file():
        d.check(False, f"Operator token present: {token_file}",
                fix=f"re-run init: cd {runtime_dir()} && {py} -m lamf.cli init --data-dir \"{data_dir}\"")
    elif token_ok and on_windows_drive_mount(token_file):
        d.check(True, f"Operator token present: {token_file} "
                      "(on a Windows drive via WSL — Linux permission bits do not "
                      "apply there; Windows file permissions protect it)")
    elif token_ok:
        d.check(True, f"Operator token present with 0600 permissions: {token_file}")

    # A server that was intentionally not started (--no-start) is not a failure.
    # It still reports green if something else already had it running.
    start_fix = (f"start it: {data_dir / 'bin' / 'start-lamf.sh'}  (Windows: start-lamf.ps1) — "
                 f"logs are in {data_dir / 'logs'}")
    server_running = server_up()
    if server_expected or server_running:
        d.check(server_running, f"LAMF server reachable at {LAMF_URL}/v1/status",
                fix=start_fix)
    else:
        d.check(False, "LAMF server not started — --no-start was given, as requested",
                warn_only=True, fix=start_fix)

    ui_running = _url_up(LAMF_URL + "/")
    if server_expected or ui_running:
        d.check(ui_running,
                f"Built-in LAMF workspace reachable at {LAMF_URL}",
                fix=f"start it: {data_dir / 'bin' / 'start-lamf.ps1'}")
    else:
        d.check(False, "Built-in LAMF workspace not served — --no-start was given, as requested",
                warn_only=True, fix=f"start it: {data_dir / 'bin' / 'start-lamf.ps1'}")

    if vault is not None:
        d.check((vault / "00 Home.md").is_file(),
                f"Optional Obsidian projection ready: {vault}",
                fix=f"cd {runtime_dir()} && {py} -m lamf.cli project --vault \"{vault}\"")

    if openclaw_state == "registered":
        try:
            cfg = json.loads(openclaw_config_path().read_text(encoding="utf-8"))
            registered = (cfg.get("plugins", {}).get("entries", {}).get(PLUGIN_ID, {}).get("enabled")
                          and cfg.get("plugins", {}).get("slots", {}).get("memory") == PLUGIN_ID)
        except Exception:
            registered = False
        d.check(bool(registered), "OpenClaw registration (plugin entry + memory slot)",
                fix="re-run this installer — it merges the OpenClaw config idempotently")
    elif openclaw_state == "failed":
        d.check(False, "OpenClaw registration (config merge failed — see above)",
                fix=f"fix {openclaw_config_path()} (a .bak copy was made), then re-run this installer")
    elif openclaw_state == "skipped":
        d.check(False, "OpenClaw registration (skipped via --no-openclaw)",
                warn_only=True,
                fix="re-run this installer without --no-openclaw to register with OpenClaw")
    else:
        d.check(False, "OpenClaw registration (OpenClaw not installed)",
                warn_only=True,
                fix="install OpenClaw (curl -fsSL https://openclaw.ai/install.sh | bash), then re-run this installer")

    if vault is not None:
        d.check(obsidian_found(), "Obsidian app installed",
                warn_only=True,
                fix="download it from https://obsidian.md — the built-in LAMF UI already works without it")

    return d


# ---------------------------------------------------------------------------
# (9) Finish card
# ---------------------------------------------------------------------------
def finish_card(ui: UI, vault: Path | None, openclaw_state: str,
                doctor: Doctor, data_dir: Path, server_running: bool = True) -> None:
    if server_running:
        ui.banner("ALL DONE — your local memory is ready")
        print()
        print(f"  Open the built-in LAMF workspace:  {LAMF_URL}")
        print("  It runs locally and does not require Obsidian.")
    else:
        ui.banner("SETUP COMPLETE — nothing is running yet (--no-start)")
        print()
        print("  Your memory is initialized but the server was not started,")
        print("  exactly as you asked. Start it whenever you like:")
        script = data_dir / "bin" / ("start-lamf.ps1" if sys.platform == "win32" else "start-lamf.sh")
        print(f"       {script}")
        print(f"  Then open:  {LAMF_URL}")
    print()
    if vault is not None:
        print("  Optional Obsidian view (runs in parallel):")
        print(f"       {vault}")
        print("  Open that folder as an Obsidian vault whenever you want.")
        print()
    if openclaw_state == "registered":
        print("  Restart OpenClaw so it loads the LAMF memory plugin.")
    else:
        print("  Whenever you install OpenClaw, just re-run this installer —")
        print("     it will register LAMF automatically.")
    print()
    print(f"  Start/stop LAMF any time:  {data_dir / 'bin'}")
    print("  (start-lamf / stop-lamf — .sh on macOS/Linux, .ps1 on Windows)")
    print()
    if doctor.failures:
        print(f"  Note: {doctor.failures} doctor check(s) need attention — scroll up,")
        print("  each failed check has its exact fix command next to it.")
    if doctor.warnings:
        print(f"  ({doctor.warnings} optional component(s) missing — warnings only, nothing broke.)")
    print()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="install.py",
        description="LAMF noob-proof installer (idempotent; re-run to repair/upgrade).",
    )
    p.add_argument("--data-dir", default=None,
                   help=f"LAMF data directory (default: {DEFAULT_DATA_DIR}, or the "
                        "already-registered instance if one exists)")
    p.add_argument("--vault", default=None,
                   help="Obsidian vault path; specifying it enables the optional parallel projection")
    p.add_argument("--obsidian", choices=("none", "parallel"), default=None,
                   help="optional Obsidian mode (default: ask on a terminal, none otherwise)")
    p.add_argument("--profile", default=DEFAULT_PROFILE, choices=PROFILES,
                   help=f"security profile for first init (default: {DEFAULT_PROFILE})")
    p.add_argument("--no-openclaw", action="store_true",
                   help="skip OpenClaw registration even if OpenClaw is installed")
    p.add_argument("--harness", action="append", choices=(*HARNESSES, "all", "none"),
                   help="agent harness to configure; repeatable (default: ask on a terminal, none otherwise)")
    p.add_argument("--git", dest="git_mode", choices=("none", "vault"), default=None,
                   help="optionally initialize the Obsidian projection as a local Git repo")
    p.add_argument("--no-start", action="store_true",
                   help="do not start the LAMF server at the end")
    p.add_argument("--no-optimizations", action="store_true",
                   help="do not install the pinned LAMF optimization pack")
    p.add_argument("--allow-git-data-dir", action="store_true",
                   help="UNSAFE: permit a data directory inside a Git checkout "
                        "(refused by default so keys/tokens/events cannot be committed)")
    p.add_argument("--reset", action="store_true",
                   help="erase existing LAMF data and initialize fresh (asks first)")
    p.add_argument("--verbose", action="store_true", help="show every command and its output")
    return p.parse_args(argv)


def guard_data_dir_outside_git(ui: UI, data_dir: Path, allow: bool) -> bool:
    """Pre-mutation boundary check (INSTALL.md: never use a Git checkout as the
    data directory). The authority holds the instance key, operator token, event
    spine, and database; inside a checkout those are one `git add -A` away from
    being published. Returns False when the installer must abort BEFORE creating
    anything. The optional Obsidian projection is unaffected — it is a derived
    view and is allowed to be its own repository (see setup_git_vault)."""
    root = git_checkout_root(data_dir)
    if root is None:
        return True
    if allow:
        ui.warn(f"Data directory is inside the Git checkout at {root}.")
        print("         --allow-git-data-dir was given, so continuing anyway.")
        print("         Keep the instance key, operator token, database, and")
        print("         events out of every commit — they are secrets.")
        return True
    ui.fail(
        f"Refusing to create LAMF data inside a Git checkout ({root}).",
        fix=f"choose a data directory outside it, e.g. "
            f"--data-dir \"{expand(DEFAULT_DATA_DIR)}\"",
    )
    print()
    print(f"  Requested data directory: {data_dir}")
    print(f"  Git checkout detected at: {root}")
    print()
    print("  That directory would hold your instance key, operator token,")
    print("  event spine, and database. Inside a repository those are one")
    print("  commit away from being published, so nothing has been created.")
    print()
    print("  If you really intend this (for example repairing an instance that")
    print("  already lives there), re-run with --allow-git-data-dir.")
    print()
    return False


def registered_paths() -> tuple[Path | None, Path | None]:
    """R4-16: read the EXISTING OpenClaw registration (if any) and return
    (data_dir, vault) it points at. Prevents a bare re-run (e.g. an agent
    'helpfully' executing the installer with no flags) from silently creating
    a second instance at the default location and re-pointing the config."""
    cfg_path = openclaw_config_path()
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        entry = cfg["plugins"]["entries"][PLUGIN_ID]["config"]
        data = Path(entry["tokenFile"]).parent if entry.get("tokenFile") else None
        vault = Path(entry["vault"]) if entry.get("vault") else None
        return data, vault
    except Exception:
        return None, None


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    ui = UI(verbose=args.verbose)
    harnesses = choose_harnesses(args.harness, interactive=sys.stdin.isatty())
    obsidian_mode = args.obsidian
    if args.vault:
        obsidian_mode = "parallel"
    elif obsidian_mode is None and sys.stdin.isatty():
        answer = input("Enable the optional parallel Obsidian projection? [y/N]: ").strip().lower()
        obsidian_mode = "parallel" if answer in ("y", "yes") else "none"
    else:
        obsidian_mode = obsidian_mode or "none"

    if args.git_mode is None and sys.stdin.isatty() and obsidian_mode == "parallel":
        answer = input("Set up the Obsidian projection as a local Git project? [y/N]: ").strip().lower()
        git_mode = "vault" if answer in ("y", "yes") else "none"
    else:
        git_mode = args.git_mode or "none"
    if git_mode == "vault" and obsidian_mode != "parallel":
        ui.warn("Git projection requested without Obsidian; enabling the parallel projection.")
        obsidian_mode = "parallel"
    reg_data, reg_vault = registered_paths()
    if args.data_dir is None:
        data_dir = reg_data or expand(DEFAULT_DATA_DIR)
        if reg_data:
            ui.info(f"Found your existing LAMF instance at {reg_data} — "
                    "re-running against IT (no new instance will be created).")
    else:
        data_dir = expand(args.data_dir)
        if reg_data and reg_data != data_dir:
            ui.warn(f"Your OpenClaw registration currently points at {reg_data}, "
                    f"but you asked for {data_dir}. I will re-register to the new "
                    "location (the old data is NOT deleted).")
    if obsidian_mode == "parallel":
        vault = expand(args.vault) if args.vault else (reg_vault or expand(DEFAULT_VAULT))
    else:
        vault = None
    # Boundary check BEFORE anything is created on disk.
    if not guard_data_dir_outside_git(ui, data_dir, args.allow_git_data_dir):
        return 2
    # Make the resolved data dir visible to path helpers (venv fallback, doctor)
    os.environ["LAMF_DATA_DIR"] = str(data_dir)

    ui.banner(f"LAMF installer v{VERSION} — Local Agent Memory Fabric")
    print()
    print("  This will set up your private, local agent memory. Nothing leaves")
    print("  this computer. You can re-run this installer any time — it only")
    print("  fixes what is missing; it never deletes your memories.")

    total = 9
    ui.step(1, total, "Checking this computer")
    step_environment(ui)

    ui.step(2, total, "Python environment + dependencies")
    venv_ok = step_venv(ui, data_dir)

    ui.step(3, total, f"Initializing LAMF data at {data_dir}")
    init_state = step_init(ui, data_dir, args.profile, args.reset) if venv_ok else "failed"
    init_ok = init_state != "failed"
    if not venv_ok:
        ui.warn("Skipping init until the environment is ready (re-run me).")

    ui.step(4, total, "Your operator token")
    if init_ok:
        step_token(ui, data_dir, fresh=(init_state == "fresh"))
    else:
        ui.info("No token to show yet — it appears after a successful init.")

    ui.step(5, total, "Optional Obsidian projection")
    if vault is None:
        ui.ok("Standalone mode selected; built-in LAMF UI remains fully available.")
    elif init_ok:
        step_vault(ui, vault)
    else:
        vault.mkdir(parents=True, exist_ok=True)
        ui.info("Vault folder created; the first projection happens after init succeeds.")

    ui.step(6, total, "Agent optimization pack")
    optimization_ok = True
    if args.no_optimizations:
        ui.info("--no-optimizations given; using core LAMF without optional modules.")
    elif init_ok:
        try:
            install_optimization_pack(ui, data_dir)
        except Exception as exc:
            optimization_ok = False
            ui.fail(f"Could not install the optimization pack: {exc}",
                    fix="check internet access and re-run this installer")

    ui.step(7, total, "Start/stop helper scripts + starting the server")
    helpers = write_helper_scripts(ui, data_dir, vault)
    write_harness_registrations(ui, data_dir, harnesses)
    harness_results = apply_harness_registrations(ui, data_dir, harnesses)
    if vault is not None:
        setup_git_vault(ui, vault, git_mode)
    if init_ok:
        step_start(ui, helpers, args.no_start)
    else:
        ui.info("Server start deferred until init succeeds (re-run me).")

    ui.step(8, total, "Selected harness registration")
    use_openclaw = "openclaw" in harnesses and not args.no_openclaw
    openclaw_state = step_openclaw(ui, data_dir, not use_openclaw, vault=vault)

    ui.step(9, total, "Doctor — checking that everything is healthy")
    doctor = run_doctor(ui, data_dir, vault, openclaw_state,
                        server_expected=not args.no_start)
    doctor.check(all(state != "failed" for state in harness_results.values()),
                 "Selected agent registrations start successfully",
                 fix="close the affected agent, then re-run this installer")
    doctor.check(optimization_ok, "Optimization pack installed and enabled",
                 fix="check internet access and re-run this installer",
                 warn_only=args.no_optimizations)

    finish_card(ui, vault, openclaw_state, doctor, data_dir,
                server_running=server_up())
    return 0 if doctor.failures == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print("\n\n  Cancelled. Nothing was half-finished that a re-run won't fix —")
        print("  just run the installer again whenever you like.")
        sys.exit(130)
