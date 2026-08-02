# LAMF — Ledgered Agent Memory Fabric

**A governed, local-first memory authority for AI agents.**

*One governed memory for every agent.*

LAMF gives compatible AI agents a shared, durable memory on hardware you control. It combines revisioned memory records, an append-only integrity spine, security profiles, secret exclusion, scoped retrieval, and MCP integrations without making any single model vendor the authority.

This repository is a clean deployment distribution. It intentionally contains no live memory database, operator token, vault, credentials, logs, or configuration from the system used to develop LAMF.

## Status

LAMF 2.0.0 is a reference implementation intended for evaluation and development. It has automated validation and smoke tests, but it is not yet presented as production-hardened software. Review the selected security profile and deployment boundary before storing important information.

## Requirements

- Python 3.10 or newer
- Windows, macOS, or Linux
- Node.js 24 or newer only when using the native OpenClaw integration

## Quick start

Clone or download this repository, then run the installer from the repository root.

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\Install-LAMF.ps1
```

### macOS or Linux

```bash
bash ./installer/install.sh
```

The interactive installer creates the private LAMF authority outside this Git checkout, initializes the selected security profile, optionally configures agent harnesses, and can start the local service. Non-interactive installation defaults to the `controlled` profile, no Obsidian projection, and no agent harness.

For repeatable deployment examples and verification commands, see [INSTALL.md](INSTALL.md).

## What is included

- `installer/` — cross-platform installer and uninstall helpers
- `runtime/` — local authority, CLI, MCP server, web workspace, and tests
- `02_SECURITY/profiles/` — fixed security profiles
- `03_CONTRACTS/golden-vectors.json` — canonical-hashing validation fixture
- `04_STORAGE/SCHEMA.sql` — authoritative SQLite schema
- `05_INTEGRATIONS/` — OpenClaw and optional optimization modules
- `Credit.md` — living external-attribution and provenance ledger

## Security boundary

Keep the Git checkout separate from every live LAMF data directory. LAMF authority data, tokens, keys, spool files, databases, vaults, logs, and exports must never be committed. The included `.gitignore` is defense in depth, not a substitute for reviewing staged files before every push.

LAMF listens on localhost by default. Do not expose its service port to a network without an explicit security review and an appropriate authentication boundary.

## License and attribution

LAMF is released under the [MIT License](LICENSE). External influences and license-review status are recorded in [Credit.md](Credit.md). Re-check upstream licenses before redistributing modified integrations or optimization modules.
