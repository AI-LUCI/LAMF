# LAMF Windows 11 Installer Architecture

Status: implementation contract
Target artifact: `LAMF-Setup-x64.exe`
Target systems: Windows 11 x64, clean per-user installation, no preinstalled Python required

## 1. Product outcome

A person downloads one executable, opens it, chooses where the application and
private memory live, selects optional optimization modules and agent harnesses,
and finishes with one initialized, locally running LAMF authority. The installer
must not require Git, Python, PowerShell policy changes, a terminal, administrator
rights, or knowledge of MCP configuration.

The default paths are:

- application: `%LOCALAPPDATA%\LAMF`
- private memory: `%LOCALAPPDATA%\LAMF\data`

The application and data paths are separate choices. Existing initialized data is
detected and preserved. A data path inside a Git worktree is rejected. Uninstalling
the application preserves private memory unless the operator explicitly selects a
separate, clearly warned data-removal action.

## 2. Distribution architecture

The public release is one signed installer executable containing:

1. the complete LAMF core runtime and documentation required at runtime;
2. a private embedded CPython runtime and all locked Python dependencies;
3. the separately governed LAMF Optimizations payload and its license/provenance;
4. the native installer UI and transactional harness configurator;
5. offline tests, notices, version metadata, and payload hashes.

The build may download pinned build inputs, but installation is offline-capable. It
must never download mutable `latest` content. Every downloaded build input is pinned
by version and SHA-256. The final executable has a reproducible payload manifest.

Use Inno Setup for the outer single-file Windows installer. Use a bundled embedded
Python distribution for LAMF rather than PyInstaller `--onefile`: LAMF needs a stable
runtime path for stdio MCP registrations, while a PyInstaller one-file program
extracts to an ephemeral directory on each launch. The embedded runtime remains an
implementation detail beneath the chosen application directory.

Production releases must be Authenticode-signed with a stable publisher identity and
timestamped. An unsigned local build is explicitly labeled a development artifact.
Microsoft Store packaging is a later distribution channel, not a prerequisite for
the GitHub release.

## 3. Installed layout

```text
<install-dir>/
  lamf.exe                 stable no-console launcher
  lamf-control.exe         control center / repair launcher
  python/                  private embedded runtime
  app/                     LAMF runtime and required package data
  optimizations/           optional pack payload, manifests, credits, licenses
  licenses/
  manifest.sha256
  version.json
  uninstall.exe

<data-dir>/
  ... existing authoritative LAMF data layout ...
  install-state.json       non-secret paths, version, selected modules/harnesses
  adapters/                transaction receipts and generated snippets
  backups/                 bounded harness-config backups
```

Machine-local identity keys and operator tokens are generated on the target machine
and never embedded in the executable, installer log, command line, or UI URL.

## 4. Setup UX

The wizard uses plain language and keyboard-accessible controls:

1. **Welcome** — explains local-first memory and the offline install.
2. **Choose folders** — application folder and private memory folder, each with a
   Browse action, free-space check, and an explanation of what is stored there.
3. **Protect memory** — choose the existing LAMF security profile; default remains
   the current safe core default. Advanced details are collapsed.
4. **Agent optimizations** — master switch plus individually selectable modules.
   Each module shows a one-sentence effect. All choices are reversible after setup.
5. **Connect your agents** — detected harnesses first, available/not-installed status,
   and an independent checkbox for Codex, Claude Code/Desktop, Kimi Code CLI, Gemini
   CLI, Grok Build CLI, OpenClaw, Hermes, and Generic MCP. Nothing is preselected
   merely because it was detected. Generic MCP produces a copyable snippet unless
   the user explicitly selects a target configuration file.
6. **Review** — exact folders, selected modules, selected harness config targets,
   restart requirements, and preservation/rollback promises.
7. **Install and verify** — progress is task-oriented: files, initialize, configure,
   verify. Per-harness failures roll back that harness and do not corrupt the LAMF
   installation or other harnesses.
8. **Ready** — shows LAMF health, each selected harness result, restart-needed badges,
   and buttons for Open Control Center, Copy diagnostics, and Finish.

The operator token may be copied through an explicit button after initialization but
is never printed or left visible by default. The UI explains that the protected
instance identity key is different from the operator access token.

Silent install has CLI parity and requires explicit arguments for harness mutations:

```text
LAMF-Setup-x64.exe /VERYSILENT /INSTALLDIR="..." /DATADIR="..." \
  /PROFILE=controlled /OPTIMIZATIONS=minimal-solution,verified-execution \
  /HARNESSES=codex,kimi,gemini
```

## 5. Runtime and control center

`lamf.exe` is a stable launcher that supplies the selected data directory without
placing secrets on the command line. It exposes the existing CLI. The MCP command is
`lamf.exe mcp --harness <id>` (or an equivalent stable argument form implemented by
the runtime), so registrations do not point into Python or source paths.

`lamf-control.exe` opens the loopback-only authenticated control center. It supports:

- health and version status;
- changing the application data directory only through an explicit migrate/attach
  operation, never by silently splitting authority;
- global and per-module optimization switches at any time;
- Connected, Not connected, and conditional Needs attention harness groups;
- connect, verify, repair, and disconnect actions for every adapter;
- bounded, redacted diagnostics and transaction history;
- copy operator token through an OS clipboard action without rendering it in HTML.

The control center binds only to loopback, requires the operator token, has CSRF
protection, and does not store secrets in URLs, browser storage, logs, or HTML.

## 6. Harness transaction contract

Harness configuration is a separate transaction per target:

1. detect executable and candidate user-level config targets;
2. parse and validate the existing configuration;
3. show or record the exact owned key and target;
4. hash the inspected input and reject stale writes;
5. create a timestamped backup;
6. write a sibling temporary file, flush it, and atomically replace the target;
7. start the exact configured command and perform MCP `initialize`, `tools/list`, and
   `memory_status` against the chosen authoritative data directory;
8. commit a redacted receipt, or restore the backup automatically on failure.

Disconnect removes only the LAMF-owned server entry. Repeated connect, verify,
repair, and disconnect operations are idempotent. Malformed or ambiguous files are
reported as Needs attention rather than overwritten.

Current user-level targets must be verified against upstream documentation and live
CLI discovery before release. Known formats include Codex TOML
`[mcp_servers.lamf-memory]`, Kimi/Gemini JSON `mcpServers`, and harness-specific
Claude, Grok, OpenClaw, and Hermes forms. Prefer a harness's supported CLI registration
command when it is transactional and can be verified; otherwise use the structured
writer contract above.

## 7. Optimization boundary

Core continues to work without the optimization pack. Packaging both projects into
one executable does not merge their source governance or authority:

- copy the pack from a pinned released commit during the build;
- retain both projects' licenses, credits, provenance, and versions;
- install modules beneath `<install-dir>/optimizations`;
- validate every manifest and instruction hash before activation;
- store only enablement state in the private data directory;
- fail open (optimizations off) if the pack or configuration is invalid;
- allow individual and global changes after installation without reinstalling.

## 8. Build and release gates

The branch must provide one documented build command and automated tests for:

- clean Windows 11 install with no system Python/Git and no elevation;
- default and custom paths, including spaces and non-ASCII characters;
- install path distinct from data path;
- existing-data attach/upgrade without authority or credential loss;
- offline install from the single executable;
- payload SHA-256 verification and dependency/license inventory;
- every optimization independently switchable and fail-open behavior;
- every harness: absent, clean connect, reconnect, verify, disconnect, malformed
  config, concurrent edit, rollback, spaces/non-ASCII path, and unrelated-key
  preservation;
- selected-harness isolation (no unselected config is touched);
- MCP handshake and `memory_status` using the selected data directory;
- uninstall preserving data and unrelated harness settings;
- installer/control-center keyboard access, visible focus, screen-reader labels,
  announced status, and no color-only state;
- no tokens, keys, private data, build-machine paths, or mutable download URLs in the
  executable, logs, manifest, or test artifacts;
- Authenticode verification for production builds, with an explicit unsigned-dev
  mode for local CI.

A smoke test in a fresh Windows Sandbox or equivalent clean VM is required before a
release is called zero-pain. Code signing and publisher identity are release inputs;
the build must support them but must not fabricate or store credentials.

## 9. Implementation order

1. Add requirement IDs, payload manifest, pinned dependency acquisition, and tests.
2. Add stable launchers and offline embedded-runtime layout.
3. Add install/upgrade/uninstall orchestration with selectable paths.
4. Generalize harness drivers and implement Gemini alongside existing adapters.
5. Add transactional connect/verify/repair/disconnect plus fixtures.
6. Add setup wizard pages and post-install control center.
7. Build unsigned development EXE, run clean-machine tests, then prepare the signing
   and release workflow without publishing it.

No commit, push, tag, release, account connection, or real harness configuration is
performed without separate operator authorization.
