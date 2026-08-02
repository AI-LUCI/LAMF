# LAMF 2.0.0 — proposed release notes

This is the first proposed stable public release of **LAMF — Ledgered Agent Memory Fabric**, a governed, local-first memory authority for compatible AI agents.

Highlights:

- Revisioned memory records with scope and provenance
- Append-only integrity spine and deep verification
- Secret exclusion and fixed security profiles
- MCP/harness registrations for Codex, Claude, Kimi, Grok, OpenClaw, Hermes, and generic MCP, subject to documented capability levels
- Cross-platform installer paths for Windows, macOS, and Linux
- Core-only operation with no behavior-optimization dependency
- Synthetic final, smoke, harness, installer-boundary, and recovery tests

Important limitations: this is a reference implementation for evaluation and development, not a production-hardening claim. It assumes a trusted host, defaults to localhost/stdio, and does not protect against an attacker with equivalent local access. Keep live data, keys, tokens, logs, vaults, configuration, and exports outside the Git checkout.

LAMF Optimizations is a separate optional product and release. It is not included in core and does not own durable memory.

Verification: download the approved release assets (`LAMF-2.0.0.zip` and `SHA256SUMS.txt`) and compare SHA-256 values against `SHA256SUMS.txt`. Worked examples for PowerShell and POSIX shells are in [INSTALL.md](../../INSTALL.md#7-verify-a-github-release-download). Checksums confirm file integrity against the published hash list; they are not code signing. Checksums must be generated only from the final clean tagged trees.
