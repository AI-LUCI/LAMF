# Installing LAMF

This guide installs LAMF from a clean source checkout while keeping the running authority and its private data outside Git.

## 1. Prerequisites

Confirm Python 3.10 or newer is available:

```text
python --version
```

On Windows, the `py` launcher is also supported. OpenClaw users additionally need Node.js 24 or newer.

## 2. Choose a private data location

The installer defaults to a LAMF directory in the current user's home folder. To make the boundary explicit, pass a location that is not inside this repository.

Windows example:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\Install-LAMF.ps1 --data-dir "E:\LAMF-Data"
```

macOS or Linux example:

```bash
bash ./installer/install.sh --data-dir "$HOME/LAMF"
```

Never choose the Git checkout as the data directory.

## 3. Choose a security profile

The default is `controlled`. Available fixed profiles are:

- `locked` — strongest approval and disclosure controls
- `controlled` — guarded general-purpose default
- `trusted-local` — fewer prompts inside a trusted local boundary
- `open-local` — lowest-friction local operation; still not anonymous or network-exposed

Example:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\Install-LAMF.ps1 --data-dir "E:\LAMF-Data" --profile controlled
```

## 4. Connect agent harnesses

Use one or more repeatable `--harness` options. Supported values are `codex`, `claude`, `kimi`, `grok`, `openclaw`, `hermes`, `all`, and `none`.

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\Install-LAMF.ps1 --data-dir "E:\LAMF-Data" --harness codex --harness claude
```

Choosing `none` installs a standalone LAMF authority with its CLI, HTTP API, MCP launcher, and local web workspace still available.

## 5. Optional Obsidian projection

Obsidian is an optional, rebuildable view—not the authority. Keep it outside this source repository too.

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\Install-LAMF.ps1 --data-dir "E:\LAMF-Data" --obsidian parallel --vault "E:\LAMF-Vault"
```

## 6. Verify the installation

The installer runs health checks automatically. To run the CLI doctor manually on Windows:

```powershell
.\runtime\.venv\Scripts\python.exe -m lamf.cli doctor --data-dir "E:\LAMF-Data"
```

On macOS or Linux:

```bash
./runtime/.venv/bin/python -m lamf.cli doctor --data-dir "$HOME/LAMF"
```

The local web workspace is served at `http://127.0.0.1:8734` when the service is running. Use the operator access token created during setup; do not confuse it with the protected instance identity key, and do not commit or print either credential.

## Installer options

Run the following for the current option list:

```text
python installer/install.py --help
```

The installer is idempotent and can be rerun to repair or update an installation. The `--reset` option erases the selected LAMF data directory and therefore requires explicit confirmation.

