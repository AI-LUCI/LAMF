# LAMF — Local Agent Memory Fabric

LAMF is a local-first, event-sourced memory system for AI agents: a durable, governed,
searchable memory designed so that no model output can silently rewrite it
(floor F5/F9). LAMF includes its own local human workspace; Obsidian is an optional
projection. Codex, Claude, Kimi, Grok, OpenClaw, Hermes and other AI systems are
interchangeable clients of the same installation.

## One memory, many agents

LAMF is harness-agnostic. Install the authority once, then connect any number of
agent harnesses through the universal MCP launcher at `runtime/lamf_mcp.py`. Every
client uses the same policy, records, integrity spine and optional projections—there
is never a separate memory database per harness.

```text
Codex ─┐                                      ┌─ built-in local LAMF UI
Claude ├─ MCP / optional native hooks ─ LAMF authority
Kimi ──┤                                      └─ optional Obsidian projection
Grok ──┤
OpenClaw ┤
Hermes ┘
```

Use `lamf harness list`, `lamf harness emit <name>`, and `lamf harness doctor`.
The normative boundary is `05_INTEGRATIONS/HARNESS_ADAPTER_CONTRACT.md`.

Registration is harness-specific. Claude Code's CLI/user MCP registration does
not configure Claude Desktop Home chats; Desktop uses `dist/lamf.mcpb`, installed
from **Settings → Extensions → Advanced settings**. Windows does not need a file
association for `.mcpb` packages.

Default search, orientation, and context retrieval is ordinary-only. Sensitive
or restricted details require an explicit per-call elevation after the user asks
for the protected information.

Optional agent-behavior modules are distributed separately in
[LAMF-Optimizations](https://github.com/AI-LUCI/LAMF-Optimizations). The core
repository contains the fail-open loader and controls, but emits no optimization
instructions unless that separate pack is installed.

Each connected MCP process registers a unique local presence. The existing
`memory_handoff` tool also provides a durable inbox (`presence`, `message`, `inbox`,
and `list`) so simultaneous agents can discover one another, announce file ownership,
and exchange coordination notes before using the fenced handoff lifecycle. This is a
durable coordination channel, not an unsafe transcript mirror.

During setup, choose no harness, one, several, or all. Choosing none is supported:
`lamf search`, `lamf remember`, `lamf context`, the HTTP API and built-in UI continue
to work without any external agent harness. Automated installs use repeatable
`--harness <name>` flags or `--harness none`.

Setup can also initialize the policy-filtered Obsidian projection as a local Git
repository with `--git vault`. This makes the visual/project layer easy to attach to
Git-aware cloud projects without ever placing the authoritative data directory,
keys, tokens, spine, review queue or operator notes in Git. No remote is created and
nothing is pushed automatically.

## Quickstart — running memory in ~5 minutes

On Windows, selecting Codex in the GUI performs and verifies the entire
activation path—MCP registration, permanent working directory, profile startup
guidance, skill installation, and the full released optimization pack. A clean
Codex Desktop installation needs one full restart after setup.

You need: Python 3.10+ (`python3 --version`). Everything else is automatic.

```bash
# macOS / Linux
bash installer/install.sh

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File installer/Install-LAMF.ps1
```

### Optional Windows GUI installer (beta)

Windows users may instead download and double-click
[`dist/LAMF-beta.exe`](dist/LAMF-beta.exe). This **beta** installer provides a
graphical setup flow with independent selections for Codex, Claude, Kimi,
Gemini, Grok, OpenClaw, Hermes, and Generic MCP. It still requires Python 3.10+
and uses the same tested `installer/install.py` core as the PowerShell method.

The beta executable is currently unsigned, so Windows SmartScreen or enterprise
policy may warn or block it. Verify the download against
[`dist/LAMF-beta.exe.sha256`](dist/LAMF-beta.exe.sha256). A matching checksum
confirms file integrity, but is not publisher authentication or code signing.
The implementation, limitations, and reproducible build command are documented
in [docs/WINDOWS_INSTALLER.md](docs/WINDOWS_INSTALLER.md).

The installer is safe to re-run. It builds the Python environment, initializes the
private authority at `~/LAMF`, shows the operator token once, starts the built-in
LAMF workspace, and configures selected harnesses. Obsidian is an explicit optional
choice: select `--obsidian parallel` (or provide `--vault PATH`) to run its projection
and watcher alongside the built-in UI. Non-interactive setup defaults to standalone.

### Standalone human workspace

After starting LAMF, open **http://127.0.0.1:8734** and paste the operator token
shown during setup. The built-in workspace lets a person browse, search, read,
remember, and review memory without installing Obsidian. Obsidian remains an
optional, rebuildable projection for people who prefer it; it is not required.

Useful commands afterwards: `~/LAMF/bin/start-lamf.sh` / `stop-lamf.sh`
(.ps1 on Windows), and `cd runtime && <venv>/bin/python -m lamf.cli doctor`.
If anything fails, every error message prints its own fix command, and re-running
the installer repairs almost everything.

**Status: reference implementation.** The runtime (`runtime/`) implements the
architecture contracts and passes a 14-stage end-to-end smoke suite
(`runtime/tests/smoke_test.py`) plus the 8-check package validator
(`tools/validate_package.py`). It is reference quality — correct and tested, not
production-hardened. "Validated" still means exactly one thing: those two suites pass.

## The three layers

1. **Witness Spine** — append-only, hash-chained, Ed25519-signed JSONL event history
   with sealed checkpoints. What actually happened, attributed to authenticated actors.
   The contracts make events tamper-evident and append-only by construction (F9;
   `03_CONTRACTS/canonical-hashing.md`); enforcement is an obligation on the
   implementation, verified by T-canonical-hash-parity.
2. **Revisioned Memory Records** — evidence compiled into usable memory: facts,
   preferences, decisions, tasks, procedures, failures, relationships, episodes,
   handoffs, council records. Updates supersede earlier versions; history is kept.
3. **Associative Index** — disposable, rebuildable retrieval layer: SQLite FTS5,
   exact ID/hash indexes, relationship graphs, hotsets, precompiled orientation
   capsules, optional local vectors, Reciprocal Rank Fusion with authority-aware
   reranking. The index is a candidate generator; the spine and records are authority.

## The five setup choices (security profiles)

| profile | summary |
|---|---|
| **Locked** | Every meaningful disclosure and durable promotion is gated; ordinary capture is quarantined. |
| **Controlled** | Recommended default. Ordinary same-scope recall is automatic; sensitive and cross-scope access stays gated. |
| **Trusted Local** | Registered local agents share ordinary memory broadly; sensitive categories remain protected. |
| **Open Local** | No per-access approval inside the registered local trust boundary. Not anonymous, not networked, not secret-capturing. |
| **AI-Custom** | Operator completes `06_SETUP/AI_CUSTOM_QUESTIONNAIRE.md`; an AI generates a policy validated against `03_CONTRACTS/schemas/security-policy.schema.json` and the invariant floor. |

All profiles are constrained by the unweakenable invariant floor F1–F12
(`02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`).

## Package inventory

The authoritative inventory of this package is `MANIFEST.sha256` (sha256 of every file
except itself). Honesty note: the manifest is **unsigned** — it detects accidental
drift (corruption, partial copies, stray edits), not malice; a determined attacker
can regenerate it. Prose never restates a file count; verify the tree with:

```text
python3 tools/validate_package.py
```

## Quick links

- `installer/install.py` — the noob-first setup (this is what the wrappers call).
- `09_OBSIDIAN/OBSIDIAN_INTEGRATION.md` — how the Obsidian vault works (governed
  areas, review queue, watcher, security profiles in the vault).
- `runtime/README.md` — the reference runtime: module contract, CLI, API, MCP.
- `05_INTEGRATIONS/HARNESS_ADAPTER_CONTRACT.md` — the universal adapter boundary.
- `05_INTEGRATIONS/OPENCLAW_INTEGRATION.md` + `05_INTEGRATIONS/openclaw-plugin/` —
  an optional enhanced OpenClaw adapter, not a separate memory implementation.
- `START_HERE.md` — 5-minute orientation, reading order, first milestone.
- `00_EXECUTIVE/OVERVIEW.md` — the vision, with claims corrected to reality.
- `01_ARCHITECTURE/SYSTEM_OVERVIEW.md` — normative architecture.
- `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md` — invariant floor F1–F12 and profiles.
- `03_CONTRACTS/CLI_REFERENCE.md` — the exact `lamf` CLI surface.
- `08_BUILD_PLAN/IMPLEMENTATION_ROADMAP.md` — twelve phases (0–11).
- `PROMPT_FOR_CODING_AI.md` — the prompt to hand a coding AI.
- `BUILD_WITH_AI.md` — master build instruction.
- `DECISIONS.md` — binding design decisions for this reconditioned package.

## License

MIT — see `LICENSE`.
