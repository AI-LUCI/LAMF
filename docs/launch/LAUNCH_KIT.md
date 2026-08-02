# LAMF public launch kit

Status: draft for maintainer approval. Nothing in this file authorizes publication.

## Messaging

**One sentence:** LAMF gives Codex, Claude, Kimi, OpenClaw, and other MCP-compatible agents one durable, governed memory, stored locally on hardware you control.

**50 words:** LAMF is an open-source, local-first memory authority for AI agents. Compatible agents share revisioned facts through MCP while LAMF applies scopes, provenance, secret exclusion, and an append-only integrity spine. Core storage works alone; an optional, separately installed optimization pack changes agent behavior without owning or modifying durable memory.

**150 words:** LAMF—Ledgered Agent Memory Fabric—gives compatible AI agents a shared memory authority that runs locally. Instead of leaving each assistant with a disconnected memory file, LAMF stores revisioned records, tracks provenance, filters retrieval by scope, excludes likely secrets, and maintains an append-only integrity spine. Codex, Claude, Kimi, OpenClaw, and other MCP-compatible clients can connect to the same installation, subject to their actual harness capabilities. The public repository contains only clean runtime code, installers, documentation, and synthetic tests; live databases, tokens, keys, logs, vaults, exports, and personal data stay outside Git. LAMF is a reference implementation for evaluation and development, not a claim of production hardening or protection from a compromised host. Core LAMF is complete on its own. LAMF Optimizations is a separate, optional download containing independently switchable behavioral guidance. It does not read, write, migrate, index, or own durable memory.

## Detailed technical explanation

Clients connect through MCP or generated harness registrations to one local authority. Incoming writes pass through sanitization, fixed security-profile rules, scope handling, and approval controls. Records are revisioned rather than silently overwritten; source events and provenance remain inspectable. An append-only integrity spine provides tamper-evident event history while the local store supports bounded retrieval. Rebuildable views and integrations remain downstream. Security depends on the selected profile, host integrity, filesystem permissions, careful backup handling, and keeping the private data directory outside every Git checkout. See `docs/ARCHITECTURE.md` and `docs/THREAT_BOUNDARIES.md`.

## Why LAMF exists

Agent memory is usually fragmented by product, project, and chat. A useful fact saved in one tool may disappear in the next, while a plain shared file offers weak provenance and governance. LAMF makes the operator—not a model vendor—the authority. It aims to make memory portable across compatible clients, explicit about scope and history, and inspectable without sending the authority to a hosted service. The goal is not maximal recall; it is useful recall with boundaries.

## Comparison

| Approach | Authority location | Cross-agent use | Governance/provenance | Best fit |
|---|---|---|---|---|
| Built-in model memory | Product-managed | Usually product-specific | Product-defined | Convenience inside one product |
| Cloud memory service | Provider-managed | Varies by API | Service-defined | Managed availability |
| RAG system | Chosen index/corpus | Possible with integration | Usually retrieval-focused | Searching documents and corpora |
| Ordinary memory files | Local filesystem | Manual or convention-based | Minimal unless added | Simple, transparent notes |
| LAMF | Operator-controlled local authority | MCP/harness dependent | Revision, scope, provenance, policy, integrity spine | Governed memory shared by compatible agents |

These categories overlap. LAMF can complement RAG; it is not evidence that every hosted or built-in memory behaves the same.

## What LAMF is not

- Not a model, chatbot, autonomous agent, vector database product, or replacement for backups.
- Not a promise of perfect recall, factual truth, production hardening, or defense against a compromised host.
- Not a cloud synchronization service by default.
- Not permission to store credentials or unrestricted sensitive data.
- Not bundled with LAMF Optimizations; that pack is optional and separate.

## FAQ

**Does data leave the machine?** The reference authority operates locally and defaults to localhost/stdio. Third-party agents and integrations have their own behavior; review them separately.

**Can I use core without optimizations?** Yes. This is a first-class tested mode.

**Do optimizations change memory?** The pack is designed as agent-behavior guidance and does not own the memory path. Disable it globally or per module.

**Which agents work?** The repository contains registrations for several named harnesses plus generic MCP. Compatibility claims must be limited to the checked version and capability level.

**Is it production-ready?** It is presented as a reference implementation for evaluation and development, not production-hardened software.

**How are sources credited?** `Credit.md` is a living ledger with source, license status, incorporation type, affected surfaces, and maintenance history.

**Where do security reports go?** Use GitHub private vulnerability reporting and never attach live memory state.

## Contributor onboarding

Read the architecture and boundaries, install into a disposable directory, run the demo, then run the test commands in `CONTRIBUTING.md`. Choose a `good first issue`, use synthetic fixtures, keep the change focused, and update `Credit.md` for any external influence.

## Starter issue candidates

1. Verify the quick start on a clean Windows VM and document only reproducible friction.
2. Verify the quick start on current macOS with both Intel and Apple Silicon observations clearly separated.
3. Verify Ubuntu installation with and without `python3-venv` preinstalled.
4. Add a synthetic end-to-end generic MCP demo fixture.
5. Improve installer diagnostics when a selected data directory is inside a Git checkout.
6. Add accessibility review and keyboard-only checks for the local web workspace.
7. Add a documented checksum-verification example for PowerShell and POSIX shells.
8. Build a sanitized issue-reproduction helper that never collects live memory content.

## Evaluator questionnaire

Record OS, Python version, installation path type (not its private value), core-only or optimized mode, harness and version, time to first successful write/recall, failures and exact sanitized reproduction, whether boundaries were understandable, whether scope/provenance were useful, repeated use after 24 hours, highest-value improvement, and permission to quote feedback. Never request a database, token, key, log, vault, export, or personal fact.

## Screenshot plan

Use only a disposable profile and synthetic facts. Capture: repository landing page; successful installer summary with paths generalized; agent A saving the demo preference; agent B recalling its record/version/scope; local files shown only at directory-name level; optimization status on, off, and per-module. Crop usernames, machine names, tokens, absolute personal paths, unrelated apps, notifications, and browser account chrome.

Captions: “One local authority, multiple compatible agents”; “Revision, scope, and provenance travel with the memory”; “Core recall remains available when the separate optimization layer is disabled.”

## Social preview specification

1280×640 PNG; dark neutral background; LAMF wordmark; subtitle “One governed memory for every agent”; simple agent → policy → local ledger motif; small “Open source • Local-first • MCP” line. No vendor logos without permission, unverifiable badges, UI screenshots, security shields, user counts, or performance claims. Maintain high contrast and safe margins; provide alt text.

## Video storyboard (75 seconds)

- 0–8s: fragmented agent windows. Narration: “Useful context is often trapped in one agent or one chat.”
- 8–18s: architecture view. “LAMF gives compatible agents one local, governed memory authority.”
- 18–34s: agent A saves the synthetic formatting preference; show scope and record ID.
- 34–49s: new task in agent B recalls it; show provenance and version.
- 49–59s: point to the disposable local data directory and disconnect network. “The authority remains on hardware you control.”
- 59–69s: install separate optimizations, toggle off, recall again. “Optimizations are optional and never own memory.”
- 69–75s: repository and limitation card. “Evaluate the open-source reference implementation; review its threat boundaries before important use.”

## Release contents

Proposed core release: `v2.0.0`, source archives plus separately generated SHA-256 checksum file, release notes, installation/demo links, known limitations, license and attribution links. Proposed optimization release: its own `v1.0.0` tag, source archives/checksums, module inventory, install/disable instructions, provenance link, and explicit statement that it contains no memory authority. Generate artifacts from clean committed trees only; do not publish locally generated runtime state.
