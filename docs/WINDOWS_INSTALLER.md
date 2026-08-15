# Windows GUI installer and `LAMF.exe`

The Windows front door for LAMF is a single windowed executable that drives the
existing installer core. It owns presentation and packaging only; every
installation decision still belongs to `installer/install.py`.

| File | Role |
| --- | --- |
| `installer/windows_gui.py` | tkinter UI, payload staging, background job, verification |
| `installer/LAMF.spec` | PyInstaller one-file, windowed build |
| `installer/Build-LAMF-Exe.ps1` | isolated build venv, tests, build, PE subsystem check |
| `runtime/tests/installer_gui_test.py` | packaging contract + end-to-end path guarantees |

## Building

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\Build-LAMF-Exe.ps1 -Clean
```

The script finds a Python 3.10+ interpreter, refuses one without `tkinter`
(a frozen GUI needs it), runs the installer GUI and scope tests, creates
`build\.pyinstaller-venv` so PyInstaller is never installed into your own Python
or into `runtime\.venv`, builds `dist\LAMF.exe`, and prints its size and SHA-256.

It then reads the PE optional header and fails the build unless the subsystem is
`2` (`WINDOWS_GUI`). A windowed EXE cannot tell you it opened a console, so the
check is made against the binary itself.

Useful switches: `-SkipTests`, `-Python <path>`, `-BuildVenv <dir>`,
`-OutputDir <dir>`.

## The one guarantee that matters: no `_MEIPASS` in anything permanent

A one-file PyInstaller build unpacks itself into a throwaway `_MEIxxxxxx` folder
that disappears when the process exits. `install.py` derives every durable path
from its own location — `runtime/`, `runtime/.venv`,
`05_INTEGRATIONS/openclaw-plugin` — and bakes those paths into the start/stop
launchers and into every harness MCP registration. Running `install.py` straight
out of `_MEIPASS` would therefore write launchers and agent configs pointing at a
directory that no longer exists.

So the GUI, in order:

1. **stages** the bundled payload (`installer/`, `runtime/`, `05_INTEGRATIONS/`,
   docs) out of `_MEIPASS` into the chosen permanent program-files directory,
   skipping `.venv`, `__pycache__`, `.git` and `*.pyc`, and refusing to continue
   if the staged tree is incomplete;
2. **runs the staged `install.py`** with a real system interpreter, so
   `package_root()` resolves to that permanent directory;
3. **verifies** afterwards that no launcher, adapter snippet or host harness
   config contains a `_MEI` path (in raw, backslash-escaped and forward-slash
   spellings), and that the launchers and registrations name the install
   directory. A leak turns a successful install into a reported failure.

Staging is idempotent: re-running over an existing installation overwrites files
in place and leaves an already-built `runtime/.venv` at the destination alone,
so an upgrade does not force a full dependency reinstall.

## Design notes

- **The installer core is the single source of truth.** The harness list, the
  profile list and the path defaults are read from `install.HARNESSES`,
  `install.PROFILES` and the runtime `lamf.harness` registry at runtime. Adding a
  harness to either registry makes it appear in the GUI with no edit here; the
  test asserts the three stay in sync.
- **Choices become an explicit command line.** `build_install_argv()` passes every
  decision as a flag and the child's stdin is closed, so `install.py` never
  prompts. Harnesses are independent: none, any subset, or all.
- **No console, ever.** The spec sets `console=False`, and every child process the
  GUI spawns (interpreter probe, `install.py`, `taskkill`) uses
  `CREATE_NO_WINDOW`.
- **Safe background execution.** Staging, the install subprocess and its output
  pump run on a worker thread; the thread only puts `(kind, payload)` events on a
  queue, and Tk is touched exclusively from the main thread draining it. Cancel
  kills the whole child tree, since `install.py` spawns `pip`.
- **Frozen EXEs cannot build venvs.** The bundled interpreter is not a usable
  Python for `install.py`, so the GUI probes for a real 3.10+ interpreter (`py -3`
  first, then `python3.x` on PATH, skipping the zero-byte Windows Store aliases)
  and shows a copyable `winget` line with a "Check again" button when none
  exists.
- **The install is recorded.** `lamf-install.json` in the program-files directory
  pre-fills the next run's choices.

## Tests

```powershell
py -3 .\runtime\tests\installer_gui_test.py
```

Ten checks, headless (no Tk main loop): frozen and source resource discovery,
installer-core reuse, the payload contract shared with `LAMF.spec` and the build
script, staging exclusions and idempotence, option mapping accepted by
`install.py`'s own `parse_args`, interpreter discovery, the temp-path scanner,
the install record, path helpers — and an end-to-end run that stages out of a
simulated `_MEI778899` directory, generates real launchers and harness
registrations, and asserts they are anchored to the permanent install and free of
temp paths (including a poisoned-file regression check that the scanner fires).
