# Installing LAMF

This guide installs LAMF from a clean source checkout while keeping the running authority and its private data outside Git.

## Windows: the one-click installer (`LAMF.exe`)

If you have `LAMF.exe`, double-click it and skip the rest of this guide. It is a
single windowed executable — no console, no unpacking, nothing to install first
except Python 3.10+ (the installer detects it and shows you the one command that
installs it if it is missing).

The window asks for four things, then does the work and shows the live output:

- **Your memories** — the permanent data folder holding the database, instance
  key and operator token. It must sit outside any Git checkout; the installer
  refuses otherwise, exactly like the command-line path.
- **Program files** — where LAMF itself lives permanently. Launchers and agent
  configs point here, so it must be a folder that stays put. It must be separate
  from the data folder, so upgrading can never touch your memories.
- **Security profile** — the same four fixed profiles described in §3.
- **Your agents** — every supported harness as an independent checkbox; pick any
  number, all of them, or none.

The EXE carries the whole package as a payload and **stages it to the program
files folder before running the installer**, so no launcher and no harness
registration ever points into PyInstaller's temporary unpack directory. The
installer verifies this afterwards and fails loudly if a generated file still
references a temp path. Building the EXE is documented in
[docs/WINDOWS_INSTALLER.md](docs/WINDOWS_INSTALLER.md).

Everything below is the command-line path, which the GUI simply drives.

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

Never choose the Git checkout as the data directory. The installer enforces this:
if the requested data directory sits inside a Git checkout it refuses and exits
before creating anything, so the instance key, operator token, database, and event
spine can never land in a repository. If you genuinely need it — for example to
repair an instance that already lives there — pass `--allow-git-data-dir`, and keep
those files out of every commit. The optional Obsidian projection is unaffected and
may be its own repository.

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

Use one or more repeatable `--harness` options. Supported values are `codex`, `claude`, `kimi`, `gemini`, `grok`, `openclaw`, `hermes`, `generic`, `all`, and `none`.

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

## 7. Verify a GitHub Release download

Release archives are published with a companion `SHA256SUMS.txt`. Comparing hashes confirms the ZIP you downloaded matches the published bytes (integrity / accidental corruption). It does **not** prove publisher authenticity the way code signing or a signature over the checksum file would; treat checksum verification and code signing as separate controls.

Published core assets for `v2.0.0` use these names (adjust the version when a newer release is current):

- `LAMF-2.0.0.zip`
- `SHA256SUMS.txt`

Optional optimizations are listed in the same sums file as `LAMF-Optimizations-1.0.0.zip` and ship from the separate [LAMF-Optimizations](https://github.com/AI-LUCI/LAMF-Optimizations) repository.

Download both the ZIP and `SHA256SUMS.txt` from the [GitHub Releases](https://github.com/AI-LUCI/LAMF/releases) page into the same directory, then verify with the built-in tools below (no third-party checksum utilities required).

### PowerShell

```powershell
# In the directory that contains LAMF-2.0.0.zip and SHA256SUMS.txt
Get-FileHash .\LAMF-2.0.0.zip -Algorithm SHA256
Get-Content .\SHA256SUMS.txt
```

Confirm the hex digest from `Get-FileHash` matches the line for `LAMF-2.0.0.zip` in `SHA256SUMS.txt` (comparison is case-insensitive). To automate the check:

```powershell
$expected = (Get-Content .\SHA256SUMS.txt |
  Where-Object { $_ -match '\sLAMF-2\.0\.0\.zip$' } |
  ForEach-Object { ($_ -split '\s+', 2)[0] }).ToLowerInvariant()
$actual = (Get-FileHash .\LAMF-2.0.0.zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw "Checksum mismatch for LAMF-2.0.0.zip" }
"OK: LAMF-2.0.0.zip matches SHA256SUMS.txt"
```

### POSIX (macOS / Linux)

GNU `sha256sum` can check the sums file directly when the ZIP sits beside it:

```bash
# In the directory that contains LAMF-2.0.0.zip and SHA256SUMS.txt
sha256sum -c --ignore-missing SHA256SUMS.txt
```

`--ignore-missing` skips other names listed in the file (for example `LAMF-Optimizations-1.0.0.zip`) when those archives are not present. On macOS without GNU coreutils, compare manually with `shasum`:

```bash
grep ' LAMF-2.0.0.zip$' SHA256SUMS.txt
shasum -a 256 LAMF-2.0.0.zip
```

The two digests must match. A matching checksum only means the file contents match the published hash list; it is not a substitute for verifying a release signature or publisher identity.

## 8. Optional agent optimizations

The core installation is complete without optimization modules. To add the
independently switchable behavior pack, download
[LAMF Optimizations](https://github.com/AI-LUCI/LAMF-Optimizations) and run its
installer against this source checkout.

Windows example:

```powershell
powershell -ExecutionPolicy Bypass -File "E:\LAMF-Optimizations\Install-LAMF-Optimizations.ps1" -LamfRoot "E:\LAMF"
```

macOS or Linux example:

```bash
bash /path/to/LAMF-Optimizations/install-lamf-optimizations.sh /path/to/LAMF
```

The pack changes no durable memory. Its modules can be controlled with
`lamf optimizations status`, `lamf optimizations on`, `lamf optimizations off`,
and the per-module `enable` or `disable` commands.

## Installer options

Run the following for the current option list:

```text
python installer/install.py --help
```

The installer is idempotent and can be rerun to repair or update an installation. The `--reset` option erases the selected LAMF data directory and therefore requires explicit confirmation.
