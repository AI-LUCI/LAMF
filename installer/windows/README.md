# LAMF Windows Installer Build

This directory builds the single-file Windows installer
``LAMF-Setup-x64.exe`` for the Local Agent Memory Fabric (LAMF).

## Requirements

- Windows 11 x64 build host (the final installer also targets Windows 11 x64)
- Python 3.10 or newer
- Rust toolchain **1.95.0** (`rustc --version` must match)
- Inno Setup 6.7.3 compiler (`iscc.exe`) — optional for `--skip-iscc` builds
- Git — to verify the optimization pack commit pin
- Network access — to download pinned build inputs on first build

No system-wide Python, Git, or elevation is required on the target machine;
the installer bundles its own embedded CPython runtime.

## One-command build

```powershell
python installer/windows/build_installer.py
```

The unsigned development installer is written to:

```text
dist/LAMF-Setup-x64.exe
```

The payload directory is left at:

```text
dist/lamf-windows-payload/
```

### Optimization pack source

The build copies the pinned optimization pack from a local checkout. The source
is resolved in this order:

1. `--optimization-pack-source <path>` on the command line.
2. The `LAMF_OPTIMIZATION_PACK_SOURCE` environment variable.
3. A sibling directory named `LAMF-Optimizations` next to the project root.

If none of these are available, the build fails with a clear message.

Examples:

```powershell
# Explicit path
python installer/windows/build_installer.py --optimization-pack-source C:\src\LAMF-Optimizations

# Environment variable
$env:LAMF_OPTIMIZATION_PACK_SOURCE = "C:\src\LAMF-Optimizations"
python installer/windows/build_installer.py
```

## Build stages

`build_installer.py` runs these stages in order:

1. **Acquire** — download/verify cached pinned inputs:
   - CPython 3.11.9 Windows embeddable x64 zip
   - PyYAML 6.0.2 cp311-cp311-win_amd64 wheel
   - PyNaCl 1.5.0 cp36-abi3-win_amd64 wheel
   - Inno Setup 6.7.3 installer EXE
2. **Launchers** — compile `launcher.rs` into `lamf.exe` and `lamf-control.exe`
3. **Payload** — assemble `dist/lamf-windows-payload/` with embedded Python,
   runtime, optimization pack, licenses, version metadata, and helper scripts
4. **Manifest** — generate `manifest.sha256`
5. **ISS compile** — run `iscc.exe setup.iss` to produce the final EXE

## Offline / CI build without Inno Setup

If `iscc.exe` is not installed, build everything except the final EXE:

```powershell
python installer/windows/build_installer.py --skip-iscc
```

This is useful in CI for payload/manifest validation.

## Development vs. signed mode

- Local/CI builds produce an **unsigned** executable.  The file metadata and
  UI identify it as a development artifact.
- Production releases must be Authenticode-signed with a stable publisher
  identity and timestamp.  Code signing credentials are a release input; the
  build scripts never fabricate, store, or embed certificates or tokens.

## Input cache

Downloaded inputs live in:

```text
installer/windows/build/cache/
```

If a cached file exists and its SHA-256 matches the pin, it is not
re-downloaded.  The cache also contains ``provenance.json`` with URLs, hashes,
and timestamps.

## Tests

Run the installer test suite:

```powershell
python -m pytest installer/windows/tests
```

Tests use temporary directories and synthetic fixtures; they never touch real
harness configuration, real user data, or the network.

## Remaining release gates

Before calling a release ready, verify:

- Clean Windows 11 VM install with no system Python/Git and no elevation
- Default and custom paths, including spaces and non-ASCII characters
- Install path distinct from data path
- Existing-data attach/upgrade without authority or credential loss
- Offline install from the single executable
- Payload SHA-256 verification
- Every optimization module independently switchable and fail-open
- Every harness: absent, connect, reconnect, verify, disconnect, malformed
  config, concurrent edit, rollback, spaces/non-ASCII path, unrelated-key
  preservation
- Selected-harness isolation
- MCP handshake and `memory_status` using the selected data directory
- Uninstall preserving data and unrelated harness settings
- Keyboard access, visible focus, screen-reader labels, announced status
- No tokens, keys, private data, build-machine paths, or mutable URLs in the
  executable, logs, manifest, or test artifacts
- Authenticode signature for production builds

Do not commit, push, tag, release, or connect accounts without separate
operator authorization.
