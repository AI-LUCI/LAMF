# LAMF — Executive Overview

Local Agent Memory Fabric (LAMF) is a standalone, local-first memory architecture for
AI agents. This document is the vision statement, with every claim corrected to what
this package actually contains. It is a **build-ready architecture and implementation
package, not a compiled installer** — a coding operator (Claude, Codex, Kimi, or
another coding AI) can implement it without redesigning the system. In this package,
"validated" means `tools/validate_package.py` passes.

LAMF is not tied to the Council, LUCI, Obsidian, GitHub, or OpenClaw. It can operate
as:

- a private memory for one locally running AI;
- shared memory for several cooperating agents;
- a multi-channel memory that recognizes the same user across approved channels;
- a Council memory with seats, rounds, claims, objections, decisions, and handoffs;
- a portable memory appliance moved between computers;
- an optional local or remotely synchronized Git-backed system.

OpenClaw is the reference integration because its plugin SDK offers an exclusive
memory capability, native tool registration, lifecycle hooks, and multi-agent routing.
Each OpenClaw agent keeps its own workspace, state, and sessions, while LAMF supplies
the governed shared-memory layer underneath (`05_INTEGRATIONS/OPENCLAW_INTEGRATION.md`).

## The five setup choices

Each choice is a security profile over the same invariant floor F1–F12
(`02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`). The floor cannot be weakened by any
profile.

1. **Locked** — every meaningful memory disclosure and durable promotion is gated.
   Ordinary capture is quarantined, automatic context injection is disabled, and
   cross-agent access requires approval. Best for employee information, legal or
   medical memory, shared computers, and highly sensitive business systems.
2. **Controlled** — the recommended default. Ordinary same-user and same-project
   memory operates automatically; sensitive information, protected changes, and
   cross-scope access remain gated.
3. **Trusted Local** — all registered local agents receive broad access to shared
   ordinary memory; sensitive categories remain protected. The practical setting for
   a trusted multi-agent OpenClaw system.
4. **Open Local** — all registered local agents and linked channels share memory
   without per-access approval. "Open" applies inside the registered local trust
   boundary; it does not mean anonymous access, internet exposure, unidentified
   actors, secret capture, or automatic cloud transmission. Secret exclusion,
   integrity logging, authenticated actors, loopback-only defaults, and encrypted,
   verified exports remain mandatory.
5. **AI-Custom** — the operator completes `06_SETUP/AI_CUSTOM_QUESTIONNAIRE.md` and
   hands it, with `06_SETUP/AI_CUSTOM_PROFILE_GENERATOR.md`, to a preferred AI. The
   AI produces a security-policy YAML. LAMF then validates it against
   `03_CONTRACTS/schemas/security-policy.schema.json`, checks it against the
   invariant floor, displays the effective behavior and risks, requires operator
   confirmation, and records the policy as a versioned event.

## How the architecture works — three layers

**Witness Spine.** An append-only, hash-chained, per-actor-signed JSONL event history
records what actually happened: messages, agent responses, tool activity, session
boundaries, explicit memory requests, handoffs, policy changes, corrections, failures
and recoveries. Sealed checkpoints (every 1,000 events or 24 h) let routine startup
verify only a bounded tail instead of scanning all history. The contracts make events
tamper-evident and append-only by construction (F9;
`03_CONTRACTS/canonical-hashing.md`); enforcement is an obligation on the
implementation, verified by T-canonical-hash-parity.

**Revisioned Memory Records.** Evidence compiled into usable memory: facts and
observations, preferences, identity and relationships, decisions and rules, tasks and
commitments, procedures, failures and lessons, session episodes, handoffs, and council
claims, evidence, objections, and votes. Updates supersede earlier versions rather
than overwriting history.

**Associative Search Index.** The fast retrieval layer: SQLite FTS5 keyword search,
exact ID and content-hash indexes, explicit relationship graphs, hot-memory caches,
precompiled orientation capsules, optional locally generated vectors, Reciprocal Rank
Fusion, and authority-aware reranking. This layer is disposable and rebuildable; a
vector result or generated summary never becomes authoritative merely because it
matched well. The spine and records are the authority.

The design adopts the operational patterns shipped by
akitaonrails/ai-memory: one local server, raw session records, Markdown memory pages,
SQLite FTS5, optional embeddings, lifecycle capture, handoffs, and cross-agent
continuity — and specifies hardening (actor pairing, an invariant security floor,
and event-sourced integrity) on top.

## Search-speed upgrades

- Incremental indexing instead of scanning all memory at startup.
- Content-hash manifests; unchanged records are not rechunked or re-embedded.
- Local embedding cache keyed by model and canonical content hash.
- SQLite WAL with one serialized writer and a concurrent read pool.
- Precompiled task and orientation capsules; active-session and active-project hotsets.
- FTS and graph retrieval before optional vector retrieval.
- Scope and security filtering before semantic search.
- Reciprocal Rank Fusion rather than letting vectors dominate.
- Authority, freshness, confidence, and scope as separate ranking signals.
- Bounded raw-event fallback only when memory records do not answer the query.
- Explicit token budgets and reported omissions.

## Performance targets (unmeasured — targets with a defined harness, not results)

- Capture acknowledgement p95 <= 200 ms.
- Exact lookup p95 <= 50 ms.
- Warm FTS search p95 <= 300 ms at 100,000 chunks.
- Deterministic context compilation p95 <= 2 s.
- No full-memory scan during routine startup (checkpoint + bounded tail).

Targets and harness: `08_BUILD_PLAN/BENCHMARKS.md`.

## OpenClaw reference integration

The package defines a native OpenClaw plugin scaffold with `kind: "memory"`, memory
capability registration, memory search/get/remember/context/orientation/handoff/status
tools, typed hooks for messages, prompt construction, tool activity, and agent
completion, lifecycle hooks for sessions, resets, compaction, startup, and shutdown,
per-agent identities and private/shared scopes, channel and thread identity metadata,
nonblocking capture, an idempotent installer/uninstaller, and OpenClaw Doctor
integration. The scaffold deliberately binds to the installed public OpenClaw SDK at
build time (`TODO-BIND:` markers), never to private internals. See
`05_INTEGRATIONS/OPENCLAW_INTEGRATION.md` and
`05_INTEGRATIONS/openclaw-plugin/openclaw.plugin.json`.

## New-computer portability

Computer A runs `lamf export` producing an **encrypted and MACed `.lamf` bundle —
passphrase mandatory (floor F3)**: XChaCha20-Poly1305 with an Argon2id-derived key.
On Computer B: install OpenClaw and LAMF, `lamf import --staged`, rebind local
secrets, `lamf verify --deep`, `lamf activate`, install the adapter, and resume with
the same memory. The export contains the policy, identities and scopes, the signed
event-chain head checkpoint, raw evidence segments, revisioned records, open tasks and
handoffs, adapter configuration, checksums, and schema versions. Secret values,
quarantine contents, vector caches, and indexes are never exported; indexes are always
rebuilt from the spine. Full spec: `07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`.

## Git is optional

Three modes — `off`, `local`, `remote` — all `off` by default in every profile. The
entire core acceptance suite must pass with Git unavailable; capture, retrieval,
security, handoffs, backups, and portability never depend on Git. Sensitive and
restricted memory classes are excluded from Git in all modes (floor F12). See
`07_PORTABILITY/OPTIONAL_GIT.md`.

## Builder handoff — what this package contains

- Four fixed policy YAMLs plus the AI-Custom questionnaire and generator contract
  (`02_SECURITY/profiles/`, `06_SETUP/`).
- The invariant floor F1–F12 and threat model (`02_SECURITY/`).
- MCP tool contracts (nine pinned tools), OpenAPI contract, wire protocol, canonical
  hashing spec with golden vectors, spool format, CLI reference, state machines
  (seven: the six §J machines plus the import machine; council transitions are
  specified in the council spec), council spec, and JSON Schemas (`03_CONTRACTS/`).
- A complete SQLite schema and indexing/search spec (`04_STORAGE/`).
- OpenClaw integration spec and plugin scaffold (`05_INTEGRATIONS/`).
- Portability, optional-Git, and new-computer guides (`07_PORTABILITY/`).
- **Twelve implementation phases (0–11)**, P0/P1/P2 acceptance tests with stable IDs,
  work breakdown, benchmarks, and risk register (`08_BUILD_PLAN/`).
- **Three architecture blueprints with editable `.dot` sources** (`blueprints/`).
- The validation harness `tools/validate_package.py` and the authoritative inventory
  `MANIFEST.sha256`.

Start with `PROMPT_FOR_CODING_AI.md` and `BUILD_WITH_AI.md`. Milestones M1–M5 are
defined in `PROMPT_FOR_CODING_AI.md`; the twelve-phase plan is
`08_BUILD_PLAN/IMPLEMENTATION_ROADMAP.md`.
