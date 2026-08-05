# Implementation Roadmap

Twelve phases (0–11). Exit criteria reference the acceptance tests of
`08_BUILD_PLAN/ACCEPTANCE_TESTS.md` by stable ID. Milestones M1–M5 are defined in
`PROMPT_FOR_CODING_AI.md`.

## Phase 0 — Contract freeze

Schemas, canonical hashes, state machines, invariant security floor, profile matrix,
threat model, data layout. **Exit: contracts frozen == this package; the builder runs
`tools/validate_package.py` (exit 0) and opens OPEN_DECISIONS.md (from
`08_BUILD_PLAN/OPEN_DECISIONS.template.md`) for ambiguities only.** Any contract gap
is recorded as an open decision, never resolved by invention.

## Phase 1 — Core event and storage engine

Rust service, single-writer SQLite (WAL + read pool), append-only JSONL segments,
payload store, bounded local spool, fail-closed sanitizer, sealed checkpoints,
idempotent replay. Exit: crash tests show no lost or duplicated canonical event
(T-crash-replay-idempotent, T-events-append-only, T-canonical-hash-parity,
T-secret-fixtures, T-startup-scan-budget, T-chain-splice-rejected,
T-duplicate-key-rejected, T-registered-secret-value). **Milestone M1 lands here.**

## Phase 2 — Policy engine and five setup choices

Fixed profiles, custom schema validation, approval queue with TTL/deny-on-timeout,
receipts, effective-policy diff, local actor authentication via pairing. Exit:
exhaustive action/profile matrix passes, including floor-rejection cases
(T-five-profiles-shown, T-profile-locked, T-profile-controlled,
T-profile-trusted-local, T-profile-open-local, T-profile-ai-custom,
T-floor-enforced, T-policy-diff-versioned, T-approval-ttl-deny,
T-identity-fail-closed, T-prompt-cannot-escalate, T-receipts-minimum,
T-model-self-approval-rejected, T-approval-receipts, T-approval-rate-limit,
T-step-up-receipt, T-pairing-ceremony-lockout, T-dns-rebinding-rejected).
**Milestone M2 lands here.**

## Phase 3 — Memory record lifecycle

Facts, preferences, decisions, tasks, procedures, failures, relationships, episodes,
supersession, contradiction, expiry, tombstones; per-record data keys and
crypto-shredding erasure. Exit: evidence remains reconstructable after revisions, and
deletion/crypto-shredding is gated on (T-supersession-authority,
T-deletion-crypto-shredding, T-quarantine-lifecycle, T-no-rechunk,
T-record-lifecycle, T-expiry-keeps-evidence, T-erasure-checklist,
T-fts-purge-on-tombstone, T-sensitivity-payload-ref, T-taint-inheritance,
T-remember-laundering-blocked, T-quarantine-search-exclusion,
T-quarantine-key-shredded) passing.

## Phase 4 — Fast deterministic retrieval

FTS5, exact/hash lookup, graph expansion, RRF, authority/scope reranking, hotset
cache, context capsules with policy-version keys. Exit: search correctness and
performance targets without embeddings (T-exact-id-first, T-authority-ranking,
T-scope-before-vector, T-fts-p95, T-capsule-p95, T-exact-lookup-p95,
T-vectors-optional, T-capsule-policy-tighten, T-index-rebuild,
T-capsule-stale-never-served, T-capsule-omission-reported,
T-capsule-restricted-excluded). **Milestone M3 lands
here.**

## Phase 5 — Interfaces

MCP stdio/HTTP, REST hooks/admin, CLI, status, health, approvals. Exit: a **generic
MCP client** (not OpenClaw) performs capture, search, context, remember, handoff, and
operator export round-trip (T-generic-mcp-client, T-capture-ack-p95,
T-provider-failure). **Milestone M4 lands here.**

## Phase 6 — OpenClaw adapter

Native memory plugin, typed hooks per the normative hook table, hook pack,
setup/uninstall, timestamped 0600 config backups, Doctor diagnostics, single-agent
integration; all SDK binding through `TODO-BIND:` markers resolved against the
installed public SDK. Exit: a fresh OpenClaw install resumes memory across sessions
offline (T-openclaw-fresh-install, T-orientation-first-session,
T-checkpoints-nonblocking, T-uninstall-preserves-data, T-doctor-diagnostics).

## Phase 7 — Multi-agent / multi-channel / council

Actor scopes, channel identities, confirmed-only identity merges with unmerge
receipts, handoff leases with fencing, council records and quorum ratification. Exit:
A->B->A handoff and two-channel identity tests pass **without scope leakage**
(T-handoff-accept-once-fencing, T-handoff-lease-expiry, T-scope-leakage,
T-agent-scope-mapping, T-channel-identity, T-wrong-merge-unmerge,
T-council-recorder-cannot-ratify, T-handoff-sibling-auto-expiry,
T-handoff-stale-fencing-rejected, T-auto-merge-forbidden,
T-merge-requires-confirmation, T-group-channel-scope,
T-council-quorum-signatures, T-council-seat-not-model,
T-council-handoff-roundtrip).

## Phase 8 — Portability and recovery

Export/import with mandatory-passphrase encryption, staged import, only-tightens
policy check, clean-machine migration, index rebuild, secret rebinding. Exit: a new
computer recovers the same current memory and policy (T-export-import-clean-machine,
T-import-path-traversal, T-import-only-tightens, T-needs-rebind,
T-export-mac-verified, T-export-tamper-rejected, T-export-wrong-passphrase,
T-export-secret-rescan, T-quarantine-export-exclusion,
T-import-never-auto-activates, T-archive-extraction-limits,
T-instance-key-anchored). **Milestone M5
lands here.**

## Phase 9 — Optional Git adapter

off/local/remote modes, asynchronous commits, spine-authoritative conflict handling,
optional sync, sensitive/restricted exclusion in all modes. Exit: core suite passes
with Git off; local-history and remote-explicit tests pass independently
(T-git-off-core-passes, T-git-local-commits, T-git-failure-nonblocking,
T-git-remote-explicit).

## Phase 10 — Optional local AI enrichment

Local embeddings, entity extraction, consolidation proposals, contradiction
suggestions, UI/Obsidian view. Exit: deterministic fallback remains fully functional
and enrichment cannot promote protected memory without policy (the
vectors-optional and prompt-cannot-escalate gates scheduled in phases 2 and 4
are re-run with enrichment active; no new test IDs are scheduled here).

## Phase 11 — Hardening and release

Fuzzing, load tests, packaging, installers, signed releases, upgrade/rollback, backup
drills, documentation. Exit: **package validation (`tools/validate_package.py` exit
0) re-run against the shipped docs, all P0/P1 tests pass, and the release benchmarks
gate of `08_BUILD_PLAN/BENCHMARKS.md` is met.**
