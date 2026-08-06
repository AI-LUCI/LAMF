# Installing LAMF

This guide installs LAMF from a clean source checkout while keeping the running authority and its private data outside Git.

## 1. Prerequisites

Confirm Python 3.10 or newer is available:

```text
python --version
```

On Windows, the `py` launcher is also supported. OpenClaw users additionally need Node.js 24 or newer.

## 1.1 Optional graphical Windows 11 installer

For Windows 11 x64, a self-contained installer is built at
[`dist/LAMF-Setup-x64.exe`](dist/LAMF-Setup-x64.exe). It does not require a
separate Python installation.

```powershell
.\dist\LAMF-Setup-x64.exe
```

Silent install with all choices on the command line:

```powershell
.\dist\LAMF-Setup-x64.exe /SILENT /INSTALLDIR="C:\Program Files\LAMF" /DATADIR="C:\Users\Me\LAMF-Data" /PROFILE=controlled /HARNESSES=kimi,codex /MODULES=minimal-solution,verified-execution /OPTIMIZATIONS_ENABLED=1
```

`/MODULES` is optional; omit it to install without optimization modules, or list
any subset of `minimal-solution`, `verified-execution`, `selective-workflows`,
`stale-context-guards`, and `surgical-changes`. Modules can be toggled later with
`lamf optimizations`.

What the installer includes and exposes:

- Embedded Python runtime, LAMF application package, native launchers, and the
  optimization instruction pack.
- Selectable **application directory** and **private data directory**.
- **Security profiles**: `locked`, `controlled` (default), `trusted-local`,
  `open-local`.
- **Harness integrations**: Codex, Claude, Kimi, Gemini, Grok, OpenClaw,
  Hermes, and a generic MCP-client snippet.
- **Optimization module selection** during setup; toggle later with
  `lamf optimizations status|on|off` and per-module `enable|disable`.
- **Preserved data on uninstall**: the private data directory is left intact
  unless explicitly removed.

Verified:

- 14/14 smoke tests pass (`runtime/tests/smoke_test.py`).
- 141 installer/launcher tests pass (`installer/windows/tests/`).
- Live Kimi MCP acceptance handshake verified.

**SmartScreen notice:** the current artifact is **unsigned**. Windows may show a
SmartScreen or AppLocker warning. Use the companion
[`dist/LAMF-Setup-x64.exe.sha256`](dist/LAMF-Setup-x64.exe.sha256) file to verify
integrity; the hash confirms the file bytes match but is not a substitute for
publisher authentication.

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
