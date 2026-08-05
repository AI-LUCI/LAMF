# LAMF Evaluation & Reconditioning Report

**Package:** LAMF (Local Agent Memory Fabric) v2.0.0
**Method:** three full adversarial rounds — attack (independent verifiers) →
rulings (DECISIONS.md amendments) → fix (parallel implementers) → machine gate
(`tools/validate_package.py`) — plus a fourth build round (§5a) that added the
Obsidian operator workspace, a working reference runtime, the real OpenClaw plugin,
and a noob-first installer, proven by a 13-stage executable smoke suite.
**Date:** 2026-07-30; runtime/competitor addendum 2026-08-01
**Verdict: SHIP.** All P0/P1 defects found across three rounds are fixed and the
8-check machine gate passes. Residual risks are enumerated in §6 and are
documented in the package, not hidden.

---

## 1. What was evaluated, and how

The input was a v1 architecture package for a local, offline-first, cryptographically
verifiable memory system for AI agents (Witness Spine + revisioned records +
disposable search index). The evaluation brief, in priority order:

1. **Completely stable upon first use** — a coding AI following only the package's
   docs must never stall (highest priority).
2. **Meets all memory-system objectives** — five setup choices, 15 non-negotiable
   rules, P0/P1/P2 acceptance tests, offline-first, portability, OpenClaw integration.
3. **Beats Obsidian Vault and akitaonrails/ai-memory in all measurable aspects**
   (lowest priority; reported honestly in §7 — including where it does not).

The 2026-08-01 addendum supersedes stale competitor characterizations. The current
ai-memory v1.20.2 is not “plain Markdown plus grep”: it ships sanitization, FTS5,
entity/graph retrieval, optional embeddings, lifecycle hooks, project isolation,
and a web UI. See `08_BUILD_PLAN/AI_MEMORY_COMPARISON.md` for the pinned-source
matrix and the permitted comparison claim.

Each round used fresh adversarial verifiers (build simulation, security re-attack,
traceability/consistency audit), an orchestrator rulings file (DECISIONS.md is the
binding authority; §U = Round-2 amendments, §V = Round-3 amendments), parallel fix
implementers, and a machine gate that must pass before the round closes. Every defect
has a ledger entry with a disposition (`DEFECT_LEDGER.md`).

## 2. Defect totals

| Round | Found | P0 | P1 | P2/P3 | Fixed | Waived/accepted |
|---|---|---|---|---|---|---|
| 1 (A1/A2/A3/L1) | 66 | 12 | 31 | 23 | 65 | 1 (unsigned manifest = drift-only, inherent) |
| 2 (V1/V2/V3) | 63 | 5 | 27 | 31 | 61 | 2 (pre-erasure exports R-16; key rotation R-15 → phase-8 work) |
| 3 (R3) | 31 | 1 | 8 | 22 | 31 | 0 |
| **Total** | **160** | **18** | **66** | **76** | **157** | **3** |

The single Round-3 P0 (R3-01, manifest drift after a late ledger edit) is a process
defect, closed by the freeze rule: MANIFEST.sha256 is regenerated as the final step
and the gate re-run afterward.

## 3. Round 1 — the missing-contract round

**Attack:** three verifiers (build simulation, security architecture, traceability).

**Headline findings:** the package's entry prompt stalled on its second sentence —
the five setup choices had no policy file format, no floor definition, no CLI surface,
no MCP tool contracts; the "non-negotiable rules" were prose with no machine
enforcement; v1 docs contradicted each other on export flags, rebuild procedures, and
profile naming.

**Fixes (66):** authored the entire missing contract layer — `DECISIONS.md` (binding
authority, sections A–T), 4 profile YAMLs + `security-policy.schema.json` with a
machine-checked invariant floor F1–F12, `CLI_REFERENCE.md` (15 pinned commands),
`mcp-tools.yaml` (9 tools), `openapi.yaml` (REST twin), canonical-hashing spec with
golden vectors, `SCHEMA.sql`, state machines, wire protocol, spool format, council
rules, threat model, secret patterns, build plan (48-task WBD, roadmap, 53 acceptance
tests, benchmarks, risk register), setup + portability docs, OpenClaw integration +
plugin scaffold, blueprints. Built `tools/validate_package.py` (checks 1–7).

## 4. Round 2 — the hardening round

**Attack:** three fresh verifiers against the reconditioned package, including a
validator-evasion brief (construct defects that slip through the checker).

**Headline findings:** crypto-shredding was architecturally false for records/FTS
copies (V2-01 → U-08 erasure architecture: `body_enc`, sensitive→payload_ref CHECK,
FTS purge, per-item quarantine keys); taint laundering via `memory_remember` (V2-03 →
U-09 provenance inheritance); the invariant floor was guttable through the policy
schema (V2-04 → U-10 schema hardening: 16-pattern baseline `contains`, rate ≤ 240,
ttl ∈ [4,168], cooldown ≥ 24, council seat cap); FTS5 rebuild documented a form that
errors on contentless tables (V1-01 → U-02 delete-all); 24 cited test IDs didn't
exist (V1-08 → U-03 registry + 37 new tests = 90); council rounds not constructible
(V1-09 → U-16 event types); pairing/step-up ceremonies unspecified at wire level
(V2-15/16 → U-14).

**Fixes (63):** 18 rulings (DECISIONS §U-01..U-18) + propagation across 30+ files;
validator hardened (reference basename-index, pinned SQLite columns + functional FTS
probes, required-vector floor, test-ID registry check, enum-parity check). Gate:
PASSED (7 checks).

## 5. Round 3 — the residual sweep + competitive audit

**Attack:** two fresh verifiers: (a) full residual sweep assuming defects remained;
(b) evidence-based competitive audit with web-verified competitor facts.

**Headline findings:** restore flow had no bootstrap for instance key / operator
credential (R3-02 → V-01); import-only-tightens was structurally vacuous on clean
machines (R3-03 → V-02); actor key custody contradicted deferred-spool signing
(R3-04 → V-03); docs referenced a nonexistent `lamf config` (R3-05 → V-04); handoff
cancel/renew transitions had no triggering surface (R3-06 → V-05); REST twin drift on
the context budget (R3-07 → V-06); payload-store key model not representable
(R3-08 → V-07); policy lattice couldn't order `approval` (R3-09 → V-08); plus 22
P2/P3 propagation/consistency defects (V-09) and 8 systemic overclaims (V-10).

**Fixes (31):** 10 rulings (DECISIONS §V-01..V-10) + propagation; validator gained
check 8 (Round-3 regression guards: `$id` base, F8 bound parity, nonexistent-command
grep, REST/MCP max_tokens parity, lattice totality, handoff enum, two_thirds
definition, truncation marker). Gate: PASSED (8 checks).

## 5a. Round 4 — the build round (Obsidian UI + reference runtime + OpenClaw plug-and-play)

**Driver:** the operator-UI analysis (Obsidian as the primary human workspace, LAMF
as the memory authority — projection, never database) plus the requirement that a
non-expert can install and use the system with OpenClaw on their own machine.

**Built (DECISIONS §W):**
- `runtime/` — a Python reference implementation of the contracts: LAMF-CANON-1
  hashing (byte-exact against all six golden vectors), Ed25519 spine with
  checkpoints, fail-closed sanitization (32/8/64 KiB bounds, `[TRUNCATED]`,
  secret-pattern blocking), deferred spool + ingester, SQLite store executing
  `04_STORAGE/SCHEMA.sql` as-is (31 tables, U-08b CHECK enforced), supersession with
  history, FTS5 search, HTTP loopback API (bearer + Host allowlist), stdio MCP
  server exposing all nine §D tools, export/import with MAC-verified bundles.
- `09_OBSIDIAN/` + projection/watcher — the Obsidian vault: eleven pinned areas,
  governed vs operator-editable folders, flat-Properties frontmatter with typed
  quoted wikilinks, native `base`/`query`/Mermaid dashboard (no community plugins),
  a watcher that restores tampered governed files in ~1 s and preserves the edit in
  `07 Review Queue/`, and profile-gated projection (locked = metadata-only stubs).
- `05_INTEGRATIONS/openclaw-plugin/` — the real plugin (TODO-BIND scaffold replaced):
  `definePluginEntry` kind "memory", `before_prompt_build` → taint-bannered context
  injection, `agent_end` → bounded capture, tool wrappers, graceful degradation.
  Bound only to the research-verified OpenClaw surface (2026-07-30); the installer
  registers it (memory slot + conversation-access hooks) and installs the agent
  skill + MCP fallback.
- `installer/` — cross-platform noob-first install: one command per OS, idempotent
  re-runs, venv with `--copies` and data-dir fallback for symlink-less filesystems,
  order-free `--data-dir`, init idempotency, doctor with per-item fix commands,
  OpenClaw auto-registration, uninstall with purge double-confirm.

**Executable proof:** `runtime/tests/smoke_test.py` — 13 stages (golden-vector
parity → init → capture (incl. blocked secret) → drain → search → correct v1→v2 with
409 on stale → projection format → watcher restore → export/import/verify_deep →
MCP handshake → U-08b CHECK): **13/13 green**, plus a full clean-HOME installer run
(doctor green), a live capture→search→vault exercise, a tamper→restore exercise, an
idempotent re-run, and a mock-OpenClaw registration merge (user settings preserved).

**Deviations documented (W-06):** Argon2id p=1 (libsodium constraint; m/t exact) and
XChaCha20-Poly1305 in place of AES-256-GCM for record bodies (algorithm recorded per
row; erasure semantics identical). Spec values remain the production target.

## 6. Residual risks and open items (accepted, documented)

| ID | Item | Status |
|---|---|---|
| R-15 | Instance-key rotation ceremony | OPEN — phase-8 work; pinned in RISK_REGISTER.md |
| R-16 | Erasure cannot reach exports/backups issued before the erasure | ACCEPTED — physically inherent; F7 honesty clause + THREAT_MODEL document it |
| — | MANIFEST.sha256 is unsigned | ACCEPTED — tamper-evidence for drift only; stated in README + validator docstring |
| — | Blueprint `.dot` files not render-verified | OPEN — graphviz unavailable in the fix environment; labels verified textually against the SVGs |
| — | Reference runtime is reference quality | ACCEPTED — correct + smoke-tested, not production-hardened (no soak tests, no multi-writer hardening, JSON-backed handoffs/approvals); stated in README + runtime/README.md |
| — | OpenClaw plugin bound to research-verified surface only | OPEN — four TODO-BIND items (memory-host-sdk surface, full manifest schema, `plugins install` flags, registerTool factory shape); marked in code, covered by the MCP fallback |
| — | Obsidian governance is watcher-based, not plugin-enforced | ACCEPTED — true read-only needs an optional Obsidian community plugin later (09_OBSIDIAN §8) |

## 7. Competitive evaluation (evidence-based; competitor facts verified 2026-07-30)

LAMF is a **specification package**, and this section is written to that reality:
LAMF cells marked *spec* are contract obligations (gated by the 90 acceptance tests
in `08_BUILD_PLAN/ACCEPTANCE_TESTS.md`), not measured properties of running software.

### 7.1 Verified competitor facts

**akitaonrails/ai-memory** (https://github.com/akitaonrails/ai-memory, accessed 2026-07-30):
Rust, MIT, created 2026-05-21; **1,318★ / 143 forks**; v1.20.1 released the audit day
(prebuilt Linux/macOS/Windows binaries, Docker, AUR). Shipped: single-use handoffs
with auto-expiry and atomic watermark+accept; a 4-rung identity ladder + optional
OIDC; bounded capture (16 KiB prompts / 2 KiB excerpts / 16 KiB backstop); SQLite +
git-versioned Markdown wiki ("openable in Obsidian"); FTS5 + graph/vector RRF search;
15+ agent harnesses; built-in web UI; CI + evals. No cryptographic provenance chain
(git history + audit table only); no policy engine; single-tenant by design.

**Obsidian** (https://obsidian.md/, https://obsidian.md/blog/future-of-plugins/,
accessed 2026-07-30): proprietary freeware, shipping since 2020; vault = plain folder
of Markdown (zero lock-in, readable by any tool incl. agents); offline-first;
4,000+ plugins/themes created, 120M+ plugin downloads (2,700+ community plugins in the
July-2026 directory); no native auditability, provenance, event log, or
machine-readable access policy.

### 7.2 Where LAMF wins (spec-level, gated by acceptance tests)

| Axis | LAMF (contract citation) | ai-memory | Obsidian |
|---|---|---|---|
| Cryptographic provenance / tamper-evident spine | Hash-chained Ed25519-signed JSONL + sealed checkpoints; golden vectors machine-verified today (`03_CONTRACTS/canonical-hashing.md`, validator check 4) | git history + audit table | none |
| Machine-readable security policy + invariant floor | F1–F12 floor, schema-enforced; 4 profiles validated by check 2 (`02_SECURITY/`) | none (no per-page RBAC by design) | none |
| Erasure | Per-record crypto-shredding F7 (`01_ARCHITECTURE/SYSTEM_OVERVIEW.md`) | purge exists; git history retains | file delete; sync retains |
| Self-validation of the artifact | 8-check gate executes schemas, vectors, manifest, registries | CI + workspace tests + evals | n/a |
| License | MIT | MIT | proprietary freeware |

Handoff semantics, auth ladder, capture bounds, and search are **parity** axes:
ai-memory ships them today; LAMF specifies equal-or-richer semantics (lease TTL +
fencing tokens, transport-level ladder, three-surface consistency) that become real
only at M1+. Runtime superiority over ai-memory is unverified and is no longer
claimed anywhere in the package (V-10).

### 7.3 Concessions (where LAMF loses, stated honestly)

**Time-to-first-use — still conceded to Obsidian; revised after Round 4.** Obsidian's
start is a plain folder of Markdown files: zero install, zero configuration
(https://obsidian.md/). As of Round 4, LAMF's reference runtime installs with ONE
command (`bash installer/install.sh` / the .ps1 on Windows) in roughly five minutes
on a normal machine — venv, init, token, vault, background server, and automatic
OpenClaw registration included — comparable to ai-memory's three-command ~15-minute
quickstart (https://github.com/akitaonrails/ai-memory#quick-start), though LAMF
requires Python 3.10+ where ai-memory ships static binaries. Obsidian's zero-install
plain folder remains unbeatable on this axis; the concession to Obsidian stands,
the "hours-to-days builder metric" is retired.

**Maturity — conceded to both competitors; unchanged.** Obsidian has shipped since
2020 with millions of users and 120M+ plugin downloads
(https://obsidian.md/blog/future-of-plugins/). ai-memory, though only created
2026-05-21, is a running system at v1.20.1 with 1,318★, 143 forks, and releases as
recent as the audit date (https://github.com/akitaonrails/ai-memory/releases). LAMF
has zero production deployments. The reference runtime's executed proofs are the
13-stage smoke suite and the 8-check package validator; the 90 registered acceptance
tests remain the gate for any production-hardened implementation. Maturity cannot be
declared; it can only be accrued.

**Runnable artifact — concession RETIRED after Round 4.** LAMF now ships a runnable
reference runtime + one-command installer (smoke-proven). ai-memory still ships
static binaries/Docker where LAMF requires Python 3.10+; noted as a residual gap,
not a concession cell.

**Extension ecosystem — conceded.** LAMF's extension surface is contractual only:
9 pinned MCP tools (`03_CONTRACTS/mcp-tools.yaml`) + `03_CONTRACTS/openapi.yaml`.
Ecosystem count: Obsidian ~2,700+ community plugins (directory, July 2026); ai-memory:
MCP tools + community UI/companion crates; LAMF: 0.

**Harness coverage — still conceded overall, but narrowed.** LAMF now ships and
tests shared-instance registrations for Codex, Claude, Kimi, Grok, OpenClaw,
Hermes, and generic MCP. ai-memory v1.20.2 still has broader first-party lifecycle
coverage. LAMF's Hermes integration is first-party while ai-memory labels Hermes
community-maintained.

**UI — concession RETIRED after Round 4.** LAMF's human UI is the Obsidian vault
(dashboard, graph, search, review queue — generated, profile-gated, watcher-protected;
`09_OBSIDIAN/OBSIDIAN_INTEGRATION.md`). ai-memory ships a built-in web UI; LAMF
deliberately rides Obsidian's mature UI instead of building one.

**Latency — LAMF measured; no cross-product winner yet.** On 2026-08-01 LAMF passed
all seven targets on the normative 100,000-record fixture, including 1.846 ms warm
FTS p95 and 10.2437 ms capsule p95. The full baseline and raw result are in
`benchmark-results/lamf-100k-windows-2026-08-01.json`. ai-memory was not run through
the identical fixture, so these numbers prove LAMF's gates, not superiority.

### 7.4 Overclaim policy (enforced in Round 3)

Every "Proven by T-…" sentence in the package is now "Acceptance gate
(unexecuted): T-…" with a header note (`02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`);
capability sentences in README/OVERVIEW are spec-obligation language; benchmark
numbers require a preserved result artifact; "matches/beats ai-memory" is reduced
to axis-specific, evidence-backed findings (V-10). If a future measurement changes
any cell of §7, this report must be updated in the same change.

## 8. Gate record

`python3 tools/validate_package.py` at freeze (8 checks):
1. reference integrity (~960 references, basename-indexed, placeholder-allowlisted)
2. policy conformance (4 profiles + negative controls vs the floor)
3. SQLite schema executes + functional FTS MATCH + delete-all rebuild + U-08b CHECK probe
4. golden hash vectors via an independent LAMF-CANON-1 re-implementation
5. MANIFEST.sha256 (regenerated last, at freeze)
6. test-ID registry (90 IDs, orphans/duplicates rejected)
7. cross-file consistency (banned spellings; 30-type enum parity ×3 surfaces)
8. Round-3 regression guards (§V: $id base, F8 bounds, command surface, twin parity,
   lattice totality, handoff actions, quorum definition, truncation marker)

**Result: VALIDATION PASSED** (see freeze log; re-run any time with the same command).

*Report compiled from DEFECT_LEDGER.md dispositions, DECISIONS.md §U/§V rulings, and
the Round-3 competitive audit (URLs cited inline, accessed 2026-07-30).*
