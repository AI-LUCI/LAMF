# LAMF Defect Ledger — Adversarial Reconditioning

Every defect found across the attack rounds, with its disposition.
Severity: **P0** first-use blocker / secret-or-integrity risk · **P1** objective
violation · **P2** hardening/polish.
Status: FIXED-R1 · FIXED-R2 · FIXED-R3 · OPEN · WAIVED (with rationale).

Round 1: three independent attackers (A1 first-use builder, A2 security red-team,
A3 consistency+competitive) produced 103 defects. Round-1 fixes are implemented
in this tree; see DECISIONS.md for the binding design resolutions.

## Round 1 — A1: first-use stability (60 defects)

| ID | Sev | Defect (short) | Disposition |
|---|---|---|---|
| A1-01 | P0 | `BUILD_WITH_AI.md` filename mismatch (`(1)` suffix) | FIXED-R1 — clean tree §A |
| A1-02 | P0 | `08_BUILD_PLAN/WORK_BREAKDOWN.yaml` absent | FIXED-R1 — authored (12 phases, 47 tasks) |
| A1-03 | P0 | `START_HERE.md` absent | FIXED-R1 — authored |
| A1-04 | P0 | package-level `README.md` absent | FIXED-R1 — authored |
| A1-05 | P0 | `00_EXECUTIVE/` absent | FIXED-R1 — `00_EXECUTIVE/OVERVIEW.md` |
| A1-06 | P0 | architecture system-overview doc absent | FIXED-R1 — `01_ARCHITECTURE/SYSTEM_OVERVIEW.md` |
| A1-07 | P0 | `02_SECURITY/` absent | FIXED-R1 — full security pack |
| A1-08 | P0 | invariant-floor doc (v1 name 00_SECURITY_PROFILE_OVERVIEW) absent | FIXED-R1 — `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md` (F1–F12) |
| A1-09 | P0 | `mcp-tools.yaml` absent | FIXED-R1 — 9 tools, locked names |
| A1-10 | P0 | `wire-protocol.md` absent | FIXED-R1 — auth ladder L0–L2 |
| A1-11 | P0 | `security-policy.schema.json` absent | FIXED-R1 — schema w/ floor consts, machine-verified |
| A1-12 | P0 | `04_STORAGE/SCHEMA.sql` absent | FIXED-R1 — 27 tables + FTS5, executes clean |
| A1-13 | P0 | flat files vs referenced directory tree | FIXED-R1 — tree §A restored |
| A1-14 | P0 | four fixed policy YAMLs absent | FIXED-R1 — `02_SECURITY/profiles/*.yaml`, schema-validated |
| A1-15 | P0 | OpenClaw plugin scaffold absent | FIXED-R1 — manifest/package/tsconfig/index.ts w/ TODO-BIND |
| A1-16 | P0 | Phase 0 "contract freeze" unexecutable | FIXED-R1 — contracts shipped; Phase 0 exit reworded |
| A1-17 | P0 | "113 validated files" false (19 present) | FIXED-R1 — claim replaced by MANIFEST.sha256 + validator |
| A1-18 | P1 | "eight editable blueprints" false (3 SVG, no sources) | FIXED-R1 — 3 SVG + 3 `.dot` sources + provenance note; claim corrected |
| A1-19 | P1 | benchmarks absent | FIXED-R1 — `08_BUILD_PLAN/BENCHMARKS.md` (5 targets + harness) |
| A1-20 | P1 | risk register absent | FIXED-R1 — `08_BUILD_PLAN/RISK_REGISTER.md` (14 risks) |
| A1-21 | P1 | SHA-256 package manifest absent | FIXED-R1 — `MANIFEST.sha256` + validator check 5 |
| A1-22 | P0 | OpenAPI contract absent | FIXED-R1 — `03_CONTRACTS/openapi.yaml` |
| A1-23 | P0 | JSON Schemas absent | FIXED-R1 — 4 schemas in `03_CONTRACTS/schemas/` |
| A1-24 | P2 | "eleven phases" (actually twelve) | FIXED-R1 — all docs say twelve |
| A1-25 | P1 | MCP tool contracts claimed but absent | FIXED-R1 (dup of A1-09) |
| A1-26..30 | P0 | first-hour stalls #1–#5 | FIXED-R1 — all referenced files now exist; validator check 1 proves it |
| A1-31 | P1 | milestone/phase ordering contradiction | FIXED-R1 — milestones M1–M5 (DECISIONS §O) |
| A1-32 | P1 | adapter-install flags diverge (`--profile` vs `--apply`) | FIXED-R1 — §C canonical + precedence rule |
| A1-33 | P1 | `lamf init` flag divergence | FIXED-R1 — §C canonical |
| A1-34 | P1 | restore step-order divergence | FIXED-R1 — canonical order (§C/§M) |
| A1-35 | P1 | missing activation step | FIXED-R1 — `lamf activate` |
| A1-36 | P1 | three undefined "deep verification" commands | FIXED-R1 — `verify` vs `doctor` defined in CLI_REFERENCE |
| A1-37 | P1 | unstable tool naming | FIXED-R1 — §D pins 9 names |
| A1-38 | P2 | git enum `local` vs `local-only` | FIXED-R1 — `off\|local\|remote` everywhere |
| A1-39 | P2 | export encryption unspecified | FIXED-R1 — §M crypto spec |
| A1-40 | P2 | export contents ambiguity (head vs full history) | FIXED-R1 — §M manifest: full segments + checkpoint |
| A1-41 | P1 | rule 3 unenforceable (OpenClaw SDK absent) | FIXED-R1 — TODO-BIND scaffold; no invented APIs |
| A1-42 | P1 | rule 4 no identity contract | FIXED-R1 — wire-protocol.md + actor model |
| A1-43 | P1 | rule 5 no event schema/supersession machine | FIXED-R1 — event.schema.json + state-machines.md |
| A1-44 | P1 | rule 7 policy semantics undefined | FIXED-R1 — policy schema + floor + mcp-tools policy points |
| A1-45 | P1 | rule 9 no sanitizer contract/secret fixtures | FIXED-R1 — SECRET_PATTERNS.md (7 fixture classes) |
| A1-46 | P1 | rule 10 canonical hashing under-specified | FIXED-R1 — LAMF-CANON-1 + 6 golden vectors, dual-implementation verified |
| A1-47 | P1 | rule 11 spool bounds unspecified | FIXED-R1 — spool-format.md (§F bounds) |
| A1-48 | P2 | rule 13 rebuild procedure unspecified | FIXED-R1 — SCHEMA.sql rebuildability markers + INDEXING §N |
| A1-49 | P2 | rule 15 "materially similar" undefined | OPEN-R2 — needs operational definition |
| A1-50 | P2 | number collisions (05/07 reused) | FIXED-R1 — tree renumbered |
| A1-51 | P2 | gapped numbering | FIXED-R1 — tree §A |
| A1-52 | P2 | "(1)" suffix pollution | FIXED-R1 |
| A1-53 | P2 | duplicate PROMPT files | FIXED-R1 — single copy |
| A1-54 | P2 | docx ≡ txt duplicate manifesto | FIXED-R1 — single `00_EXECUTIVE/OVERVIEW.md` |
| A1-55 | P2 | orphan README describing missing folder | FIXED-R1 |
| A1-56 | P1 | no installation docs (circular) | FIXED-R1 — runbook notes install docs ship with releases; roadmap Phase 11 |
| A1-57 | P2 | Phase 0 "independent review" for solo builder | FIXED-R1 — roadmap reworded to validator + OPEN_DECISIONS |
| A1-58 | P2 | `OPEN_DECISIONS.md` no template | FIXED-R1 — template authored |
| A1-59 | P2 | matrix omits fifth profile | FIXED-R1 — FEATURE_MATRIX has 5 columns |
| A1-60 | P2 | no version/changelog/license | FIXED-R1 — VERSION 2.0.0, CHANGELOG, MIT LICENSE |

## Round 1 — A2: security red-team (23 defects)

| ID | Sev | Defect (short) | Disposition |
|---|---|---|---|
| A2-01 | P0 | loopback actor auth unspecified | FIXED-R1 — §E pairing-only + tokens + SO_PEERCRED + anti-rebinding |
| A2-02 | P0 | sanitize stage absent from pipeline; value-blind exclusion | FIXED-R1 — §F fail-closed pre-spool sanitize + value detectors + export re-scan |
| A2-03 | P0 | memory-borne prompt injection, no taint/promotion gating | FIXED-R1 — §K taint classes + F5 + capsule envelope warning |
| A2-04 | P0 | export no trust anchor | FIXED-R1 — §M MACed manifest + signed checkpoint + out-of-band head confirm |
| A2-05 | P0 | encryption contradictions (export plaintext, no decrypt step) | FIXED-R1 — F3 export encryption mandatory; §M import decrypt step 0 |
| A2-06 | P1 | erasure impossible (append-only vs tombstones) | FIXED-R1 — §L crypto-shredding + redaction-aware fallback |
| A2-07 | P1 | "Strong-ID automatic" merge undefined/irreversible | FIXED-R1 — F6 confirmed merges + unmerge; auto-merge forbidden |
| A2-08 | P1 | import: zip-slip, foreign index trust, policy downgrade, key order | FIXED-R1 — §M/F4 allowlist + always-rebuild + only-tightens + rebind-first |
| A2-09 | P1 | AI-Custom questionnaire meta-leak; floor absent | FIXED-R1 — privacy notice + local-model guidance + floor shipped |
| A2-10 | P1 | approval queue: no rate limit/TTL/step-up | FIXED-R1 — F8 + policy keys |
| A2-11 | P1 | hash chain: no ordering/signer/checkpoints | FIXED-R1 — §G seq authority + Ed25519 sigs + §H checkpoints |
| A2-12 | P1 | quarantine lifecycle black hole | FIXED-R1 — §J machine + TTL + export exclusion |
| A2-13 | P1 | Git bypasses encryption/erasure; remote = egress | FIXED-R1 — F12 + OPTIONAL_GIT patched |
| A2-14 | P1 | matrix holes: undefined terms, missing column, receipt floor | FIXED-R1 — glossary + 5 columns + F10 |
| A2-15 | P2 | at-rest encryption scope undefined (spool) | FIXED-R1 — F-floor scope enumerated in SECURITY_PROFILE_OVERVIEW |
| A2-16 | P2 | llm_input/llm_output mirroring | FIXED-R1 — OFF const in all profiles |
| A2-17 | P2 | vector cache export/inversion | FIXED-R1 — excluded from export; RISK_REGISTER notes inversion |
| A2-18 | P2 | `needs_rebind` references leak metadata | FIXED-R1 — §M.7 salted hashes |
| A2-19 | P2 | no MCP capability scoping | FIXED-R1 — §D agent vs operator classes |
| A2-20 | P2 | canonical JSON adversarial parsing | FIXED-R1 — duplicate-key rejection + vectors |
| A2-21 | P2 | spool backpressure mode unspecified | FIXED-R1 — §F.4 drop-oldest + gap event |
| A2-22 | P2 | import onto non-empty instance undefined | FIXED-R1 — import-into-empty default; merge deferred → RISK_REGISTER |
| A2-23 | P2 | installer backups/uninstall retention | FIXED-R1 — 0600 backups, uninstall keeps data (OPENCLAW_INTEGRATION) |

## Round 1 — A3: consistency + competitive (20 defects)

| ID | Sev | Defect (short) | Disposition |
|---|---|---|---|
| A3-01 | P0 | claimed package contents absent | FIXED-R1 — contracts shipped (see A1 ledger) |
| A3-02 | P0 | capsules leak after policy tighten | FIXED-R1 — §J capsule key includes policy_version; test T-capsule-policy-tighten |
| A3-03 | P0 | startup verify infeasible vs no-full-scan | FIXED-R1 — §H sealed checkpoints + tail-only startup |
| A3-04 | P0 | quarantine lifecycle unspecified | FIXED-R1 — §J + T-quarantine-lifecycle |
| A3-05 | P0 | approval semantics undefined | FIXED-R1 — §J + TTL deny-on-timeout |
| A3-06 | P1 | handoff lifecycle loses to ai-memory | FIXED-R1 — §J fencing/lease/auto-expiry ≥ ai-memory semantics |
| A3-07 | P1 | record lifecycle states unspecified | FIXED-R1 — §J + contradiction default pinned |
| A3-08 | P1 | 3 perf targets untested; ack budget lacks bounds | FIXED-R1 — §F bounds + T-capture-ack-p95 / T-exact-lookup-p95 / T-startup-scan-budget |
| A3-09 | P1 | install contract contradictions | FIXED-R1 — §C canonical CLI |
| A3-10 | P1 | actor auth mechanism unspecified | FIXED-R1 — §E ladder (parity w/ ai-memory rungs) |
| A3-11 | P1 | council ratification test orphaned | FIXED-R1 — council.md (quorum; recorder never ratifies) |
| A3-12 | P1 | invariant floor referenced but absent | FIXED-R1 — F1–F12 shipped + schema-enforced |
| A3-13 | P2 | export unverified/unencrypted spec | FIXED-R1 — §M |
| A3-14 | P2 | at-rest encryption zero mechanism | FIXED-R1 — §L envelope keys; matrix row defined |
| A3-15 | P2 | auto-merge risk | FIXED-R1 — F6 + T-wrong-merge-unmerge |
| A3-16 | P2 | read receipts no contract | FIXED-R1 — F10 + receipts table in SCHEMA.sql |
| A3-17 | P2 | Git conflicts/sync classes unspecified | FIXED-R1 — OPTIONAL_GIT: spine is authority; F12 exclusions |
| A3-18 | P2 | hotset staleness after supersession | FIXED-R1 — §N invalidation keys |
| A3-19 | P2 | Python hash parity orphaned | FIXED-R1 — validate_package.py check 4 IS the Python leg |
| A3-20 | P2 | phase-exit coverage holes | FIXED-R1 — roadmap exits aligned to T-ids |

## Lead-discovered during R1 fix integration

| ID | Sev | Defect | Disposition |
|---|---|---|---|
| L1-01 | P1 | DECISIONS §C `--include-indexes` vs §M.3 removal (self-contradiction) | FIXED-R1 — flag removed everywhere |
| L1-02 | P2 | test-ID casing `T-approval-TTL-deny` | FIXED-R1 — normalized to `T-approval-ttl-deny` |
| L1-03 | P1 | actor pair/revoke not spine-audited | FIXED-R1 — event types `actor_pair`/`actor_revoke` added (enum 28) |
| L1-04 | P2 | package.json references absent tsconfig.json | FIXED-R1 — tsconfig.json added to tree |
| L1-05 | P2 | spool can't carry chain fields (seq/prev_hash unknowable at append) | FIXED-R1 — deferred spool form endorsed (DECISIONS §F.5) |
| L1-06 | P2 | payload_sha256 of null payload undefined | FIXED-R1 — pinned = sha256(canonical `null`) |

## Open items carried into Round 2

- A1-49: rule 15 "materially similar failed attempts" needs an operational definition.
- .dot blueprints not render-verified (graphviz unavailable in the fix environment).
- Full cross-doc consistency sweep of the NEW files by fresh attackers (R2).

---

## Round 2 — V1: build simulation (23 defects)

All FIXED-R2 unless noted. Validator hardening (checks 1/3/4/6/7) now mechanically
covers the V1-02..V1-05 and V1-08 classes.

| ID | Sev | Defect (short) | Disposition |
|---|---|---|---|
| V1-01 | P0 | events_fts referenced nonexistent column; documented rebuild errors | FIXED-R2 — contentless FTS + trigger sync + delete-all rebuild; validator executes MATCH + rebuild |
| V1-02 | P1 | EVALUATION_REPORT referenced but absent; check-1 blind spot | FIXED-R2 — placeholder exists; check 1 scans fenced blocks |
| V1-03 | P1 | reference-checker bypass class | FIXED-R2 — all SCAN_EXT files scanned, basename index, placeholder allowlist, fenced-block scan |
| V1-04 | P1 | check 3 name-shallow | FIXED-R2 — pinned columns + functional FTS + U-08b CHECK probe |
| V1-05 | P1 | check 4 no vector floor | FIXED-R2 — REQUIRED_VECTORS pinned |
| V1-06 | P1 | include_indexes zombie | FIXED-R2 — removed from mcp-tools + openapi (U-01) |
| V1-07 | P1 | index rebuild ordering contradiction | FIXED-R2 — staging-before-activation everywhere |
| V1-08 | P1 | 24 undefined test IDs cited | FIXED-R2 — U-03 registry + renames + 37 new tests; validator check 6 |
| V1-09 | P1 | council rounds not constructible | FIXED-R2 — council_round_open/close events + seat/quorum payload (U-16) |
| V1-10 | P1 | identity re-proposal impossible | FIXED-R2 — partial unique index (U-06) |
| V1-11 | P1 | payload spill stage/medium unpinned | FIXED-R2 — U-04 spill-before-append, SQLite medium, bundle = serialization |
| V1-12 | P1 | autonomous-event signing gap | FIXED-R2 — lamf-system actor (U-07) |
| V1-13 | P1 | capture_sig placement + spool form conflict | FIXED-R2 — deferred-only + top-level field (U-04) |
| V1-14 | P1 | null-payload storage divergence | FIXED-R2 — text-'null' convention (U-05) |
| V1-15 | P2 | CLI example nonexistent hooks | FIXED-R2 — normative names |
| V1-16 | P2 | profile-name casing split | FIXED-R2 — hyphenated everywhere (U-11) |
| V1-17 | P2 | REST/MCP twin drift | FIXED-R2 — record_types/score/too_large/426 reconciled |
| V1-18 | P2 | cross-machine invariant overclaim | FIXED-R2 — carve-out for derived/pre-spine transitions |
| V1-19 | P2 | capsule invalidation not expressible | FIXED-R2 — watermark-comparison mechanism (U-12) |
| V1-20 | P2 | 4 KiB bound unenforced; KiB units | FIXED-R2 — bytes pinned; enforcement at capture path |
| V1-21 | P2 | unmeasurable/mis-cited acceptance clauses | FIXED-R2 — T-floor-enforced reworded; citations fixed |
| V1-22 | P2 | receipt referential integrity | FIXED-R2 — REFERENCES receipts(receipt_id) |
| V1-23 | P2 | ingester watermark home unpinned | FIXED-R2 — ingester_state table |
| V1-note | — | unsigned manifest = drift detection only | WAIVED — documented in README + validator docstring (inherent) |

## Round 2 — V2: security re-attack (25 defects)

| ID | Sev | Defect (short) | Disposition |
|---|---|---|---|
| V2-01 | P0 | crypto-shredding false for records/FTS/events copies | FIXED-R2 — U-08 erasure architecture (body_enc, FTS purge, sensitive→payload_ref CHECK, embedding purge, capsule sweep, quarantine keys) |
| V2-02 | P0 | erasure vs issued exports/backups | FIXED-R2 — F7 honesty clause + THREAT_MODEL (U-08h); accepted residual R-16 |
| V2-03 | P0 | taint/sensitivity laundering via memory_remember | FIXED-R2 — U-09 inheritance + agent-external never auto-promote + handoff capsule re-check |
| V2-04 | P0 | excluded_sources baseline guttable | FIXED-R2 — schema allOf+contains 16-pattern baseline |
| V2-05 | P1 | rate_limit no maximum | FIXED-R2 — ≤240 |
| V2-06 | P1 | no tighten lattice | FIXED-R2 — normative lattice (U-10g) |
| V2-07 | P1 | manifest MAC unspecified/unplaceable | FIXED-R2 — HMAC-HKDF construction + mac field (U-13b) |
| V2-08 | P1 | export-side key logistics undefined | FIXED-R2 — key hierarchy pinned (U-13a) |
| V2-09 | P1 | instance identity key a ghost | FIXED-R2 — instance_identity table + manifest fingerprint + TOFU confirm; rotation ceremony OPEN (RISK R-15, phase 8) |
| V2-10 | P1 | council Sybil seats | FIXED-R2 — council policy keys, max_seats const 1 (U-10e) |
| V2-11 | P1 | compaction breaks --deep verify | FIXED-R2 — compaction_checkpoint payload + verify rule (U-08i) |
| V2-12 | P1 | no capsule sensitivity ceiling | FIXED-R2 — F12: automatic capsules exclude restricted (U-12) |
| V2-13 | P1 | paste-laundering as user_direct | FIXED-R2 — U-09c + THREAT_MODEL A8 |
| V2-14 | P1 | device names + archive format | FIXED-R2 — tar/ustar + caps + denylist outside regex (U-13c) |
| V2-15 | P1 | pairing ceremony gaps | FIXED-R2 — token after confirm, 128-bit, lockout, Windows SID (U-14) |
| V2-16 | P1 | step-up undefined at wire level | FIXED-R2 — ≤5-min assertion + step_up kind (U-14) |
| V2-17 | P1 | secrets_registry incoherent | FIXED-R2 — value_enc/salt/value_len + in-memory matching (U-15) |
| V2-18 | P1 | receipt privacy/ACL | FIXED-R2 — ids+hashes, operator-only, export-excluded (U-08f) |
| V2-19 | P2 | profile-name enum split | FIXED-R2 — U-11 |
| V2-20 | P2 | include_indexes contradicted | FIXED-R2 — U-01 |
| V2-21 | P2 | policy_version storage + WAL race | FIXED-R2 — policy_state table + serve-time re-check (U-12) |
| V2-22 | P2 | floor minimums lack teeth | FIXED-R2 — ttl ≥4, cooldown ≥24 |
| V2-23 | P2 | sanitizer_note field missing; split secrets | FIXED-R2 — field added; THREAT_MODEL residuals |
| V2-24 | P2 | no socket_only bind value | FIXED-R2 — enum + locked default (U-10d) |
| V2-25 | P2 | quarantine purge key/blob | FIXED-R2 — per-item keys shredded on purge (U-08g) |

## Round 2 — V3: traceability audit (15 defects)

| ID | Sev | Defect (short) | Disposition |
|---|---|---|---|
| V3-01 | P1 | DECISIONS self-contradiction on export flag | FIXED-R2 — U-01 final ruling; ledger L1-01 corrected |
| V3-02 | P1 | spool-format re-opened deferred/pre-signed | FIXED-R2 — deferred-only (U-04) |
| V3-03 | P1 | 24 dangling test IDs | FIXED-R2 — U-03 + check 6 |
| V3-04 | P1 | batched-fsync phantom policy key | FIXED-R2 — deployment config (U-17) |
| V3-05 | P2 | machine count mismatch | FIXED-R2 — header + CHANGELOG corrected |
| V3-06 | P2 | profile-name representation | FIXED-R2 — U-11 |
| V3-07 | P2 | batch vs body limit conflict | FIXED-R2 — 64 events AND 1 MiB (U-17) |
| V3-08 | P2 | error enum drift | FIXED-R2 — too_large union |
| V3-09 | P2 | F12 clause set divergence | FIXED-R2 — DECISIONS F12 amended |
| V3-10 | P2 | "Proven by" wrong/unnamed IDs | FIXED-R2 — registry-only citations |
| V3-11 | P2 | 4 weak test citations | FIXED-R2 — re-cited + channel object + provider clause |
| V3-12 | P2 | schema $id/version split | FIXED-R2 — lamf.dev + 2.0.0 unified |
| V3-13 | P2 | entropy budget dangling | FIXED-R2 — BENCHMARKS ≤0.1% FP budget |
| V3-14 | P2 | capture_sig two placements | FIXED-R2 — top-level (U-04) |
| V3-15 | P2 | max_tokens clamp mismatch | FIXED-R2 — ≤4000 clamped to policy |

## Lead actions in Round 2 (beyond coder work)

- Validator v2: checks 1/3/4/6/7 hardened per V1 findings; meta-file and
  rename-documentation self-traps resolved; basename-index + placeholder allowlist.
- 37th test ID T-sensitivity-payload-ref added (U-08b coverage).
- Gate: VALIDATION PASSED (7 checks, 960 references, 90-test registry,
  30-type enum consistency, functional FTS + rebuild + U-08b CHECK probe).

## Open items carried into Round 3

- R-15 instance-key rotation ceremony (phase-8 work, documented).
- R-16 pre-erasure export/backup residual (accepted + documented).
- .dot blueprints not render-verified (graphviz unavailable in fix environment).
- Final competitive measurable matrix (Round 3).

---

## Round 3 — residual sweep + competitive audit (31 defects)

All FIXED-R3. Rulings in DECISIONS.md §V; validator gained check 8 (Round-3
regression guards) covering the evasion classes this round exposed.

| ID | Sev | Defect (short) | Disposition |
|---|---|---|---|
| R3-01 | P0 | Manifest drift after late ledger edit → package fails its own Step-0 gate | FIXED-R3 — freeze rule: MANIFEST.sha256 regenerated LAST; gate re-run after |
| R3-02 | P1 | Restore flow has no bootstrap for instance key / operator credential | FIXED-R3 — V-01 (import creates identity+lamf-system; bootstrap pairing; re-pair after activate) |
| R3-03 | P1 | Import only-tightens structurally vacuous on clean machines | FIXED-R3 — V-02 (floor baseline; re-import leg with operator confirm); T-import-only-tightens reworded |
| R3-04 | P1 | Actor key custody contradicts deferred-spool signing | FIXED-R3 — V-03 (server-side keypairs at pairing; instance holds signing keys) |
| R3-05 | P1 | Docs referenced nonexistent `lamf config` | FIXED-R3 — V-04 (`config/server.json` `durability.fsync`); validator check 8c |
| R3-06 | P1 | Handoff cancel/renew had no triggering surface | FIXED-R3 — V-05 (memory_handoff enum + cancel/renew); check 8f |
| R3-07 | P1 | REST /v1/context max_tokens 32768 vs MCP 4000 | FIXED-R3 — V-06 (4000 + clamp); check 8d |
| R3-08 | P1 | Payload-store key model not representable (no key owner/nonce) | FIXED-R3 — V-07 (record_keys keyed by events.id too; nonce column pinned) |
| R3-09 | P1 | capture.ordinary `approval` outside the tighten lattice | FIXED-R3 — V-08 (approval > quarantine > automatic); check 8e |
| R3-10 | P2 | U-10c bounds not propagated (DECISIONS F8, state-machines, THREAT_MODEL) | FIXED-R3 — [4,168] / ≥ 24 everywhere; check 8b |
| R3-11 | P2 | V3-09 incomplete: F12 lacked llm_transcript const | FIXED-R3 — F12 amended |
| R3-12 | P2 | U-10e incomplete: council keys missing from §I key tree | FIXED-R3 — §I amended |
| R3-13 | P2 | memory-record schema $id base fork (lamf.local) | FIXED-R3 — lamf.dev unified; check 8a |
| R3-14 | P2 | U-02 authority text pinned non-portable DELETE FROM rebuild | FIXED-R3 — delete-all form pinned in DECISIONS too |
| R3-15 | P2 | Pairing-code example violated ≥128-bit rule | FIXED-R3 — grouped 32-hex example |
| R3-16 | P2 | Truncation marker fork (plugin vs SECRET_PATTERNS) | FIXED-R3 — `[TRUNCATED]` everywhere; check 8h |
| R3-17 | P2 | Roadmap phase exits omitted 38/90 registered tests | FIXED-R3 — all 90 scheduled exactly once by component phase |
| R3-18 | P2 | Handoff offer TTL never pinned | FIXED-R3 — 24 h (V-05) |
| R3-19 | P2 | Entropy threshold unreachable for hex fixtures | FIXED-R3 — per-encoding thresholds (base64url ≥4.5; hex ≥3.9) |
| R3-20 | P3 | State-machine count tri-divergence | FIXED-R3 — seven (six §J + import) everywhere |
| R3-21 | P3 | FEATURE_MATRIX cited minItems 1 (actual 16) | FIXED-R3 |
| R3-22 | P3 | DECISIONS §S "5 targets" (actual 6) | FIXED-R3 |
| R3-23 | P3 | DECISIONS §P described 5 validator checks | FIXED-R3 — §P lists all 8 |
| R3-24 | P3 | Generator never emits socket_only for AI-Custom | FIXED-R3 — generator guidance amended |
| R3-25 | P3 | wire-protocol actor tuple omitted `system` | FIXED-R3 — kind ∈ {human, agent, operator, system} |
| R3-26 | P3 | two_thirds quorum undefined numerically | FIXED-R3 — ceil(2n/3); check 8g |
| R3-27 | P3 | council payload minimum omitted `ratified` | FIXED-R3 — added to pinned minimum |
| R3-28 | P3 | REST twin gaps (include_history, /v1/orientation, info text) | FIXED-R3 — V-06 |
| R3-29 | P3 | Validator rebuild SQL missed coalesce(session,'') | FIXED-R3 — matches pinned form |
| R3-30 | P3 | EVALUATION_REPORT was a stub | FIXED-R3 — full report written (this round) |
| R3-31 | P3 | "32 KiB" labels on 32768-char maxLength (bytes vs chars) | FIXED-R3 — labels reworded; byte bound at capture path |

## Round 3 — competitive audit outcomes

Competitor facts verified against live sources (2026-07-30): ai-memory 1,318★,
v1.20.1 released the audit day, shipped handoffs/auth ladder/bounded capture;
Obsidian plain-folder vault, 2,700+ community plugins, 120M+ plugin downloads.
Prior characterizations CONFIRMED. Four additional losing cells found (runnable
artifact, extension ecosystem, harness coverage, UI) and conceded alongside
time-to-first-use and maturity in EVALUATION_REPORT.md §7.3. Eight systemic
overclaims downgraded to spec-obligation language (V-10). LAMF spec-level wins
(provenance spine, machine-readable policy floor, erasure, self-validation)
retained with acceptance-gate framing.

## Final tally

- Round 1: 66 defects → 65 fixed, 1 waived (inherent).
- Round 2: 63 defects → 61 fixed, 2 accepted/open (R-15, R-16; documented).
- Round 3: 31 defects → 31 fixed.
- **Total: 160 defects found, 157 fixed, 3 waived/accepted with documentation.**
- Freeze gate: VALIDATION PASSED — 8 checks, including the Round-3 regression
  guards added from this round's validator-evasion findings.

---

## Round 4 — the build round (12 defects found during implementation/debug)

Rulings in DECISIONS.md §W. Proof: runtime/tests/smoke_test.py 13/13 green,
full clean-HOME installer run green, live capture/search/vault/tamper exercises,
idempotent re-run, mock-OpenClaw registration merge.

| ID | Sev | Defect (short) | Disposition |
|---|---|---|---|
| R4-01 | P0 | `lamf serve` ran no ingester — spooled events never became records/notes | FIXED-R4 — serve runs drain thread + throttled projection callback + startup catch-up |
| R4-02 | P1 | venv creation failed on symlink-less filesystems (fuse/NAS/sync dirs) | FIXED-R4 — `--copies` retry + data-dir venv fallback + LAMF_VENV override |
| R4-03 | P1 | `--data-dir` only global → installer/noob invocation `init --data-dir X` rejected | FIXED-R4 — order-free: every subcommand accepts it (parent parser) |
| R4-04 | P1 | `lamf init` refused data dirs containing only installer artifacts (.venv/bin/logs) | FIXED-R4 — refuses only real prior-instance artifacts |
| R4-05 | P1 | start/stop helpers relied on implicit HOME/default paths | FIXED-R4 — helpers pass `--data-dir`/`--vault` explicitly |
| R4-06 | P2 | `store.get_record` lineage walk could spin forever on a supersedes cycle | FIXED-R4 — visited-set guard |
| R4-07 | P2 | SQLite connection thread-affinity broke HTTP handler threads | FIXED-R4 — check_same_thread=False + single-writer discipline |
| R4-08 | P2 | export rebuilt events from SQLite, dropping hash-covered `"session":null` | FIXED-R4 — export serializes spine segment lines verbatim |
| R4-09 | P2 | export/import dir mismatch (`spine/` vs `events/`) | FIXED-R4 — unified on the §C `events/` layout |
| R4-10 | P2 | validator check 8h + 7 docs referenced the deleted plugin scaffold paths | FIXED-R4 — repointed to `05_INTEGRATIONS/openclaw-plugin/index.ts`; §A tree gains runtime/installer/09_OBSIDIAN |
| R4-11 | P2 | Argon2id p=4 and AES-256-GCM unimplementable with pinned deps (pynacl) | ACCEPTED-DOCUMENTED — W-06: p=1 (m/t exact), XChaCha20-Poly1305 with per-row alg recording; spec values remain production target |
| R4-12 | P3 | OpenClaw plugin API unknowable from package alone (original TODO-BIND scaffold) | FIXED-R4 — bound to the research-verified surface (2026-07-30); 4 residual TODO-BIND items marked + MCP fallback |

| R4-13 | P1 | `PRAGMA journal_mode = DELETE` on every `Store.open` fails `database is locked` when any other connection holds the db open (journal-mode changes ignore busy_timeout) — broke concurrent MCP/HTTP attach and regressed smoke stage 12 | FIXED-R4 — set once at db creation (persists in the db header); later opens retry best-effort and tolerate SQLITE_BUSY |
| R4-14 | P2 | WSL/drvfs mounts (e.g. `/mnt/y`) don't persist chmod → doctor's 0600 token check would hard-fail a correct Windows-drive install | FIXED-R4 — `on_windows_drive_mount()` (proc/mounts fstype drvfs/9p) makes doctor explain + rely on Windows ACLs instead |

| R4-15 | P0 | MCP fallback registered as bare `python -m lamf.mcp_server`: its `__main__` built ctx with `store=None` and defaulted the data dir to `~/LAMF`, so every host-spawned tool call failed `store not attached to server context` (found in the field on the first real OpenClaw attach) | FIXED-R4 — installer now registers `-m lamf.cli mcp --data-dir <dir>` (full ctx via `_open_ctx`) + `env LAMF_DATA_DIR`; bare `__main__` now also attaches the store when the instance exists |

| R4-16 | P0 | Bare installer re-run (e.g. an agent "helpfully" running it with no flags) silently created a SECOND instance at the default `~/LAMF` and re-pointed the OpenClaw registration away from the operator's chosen data dir — found in the field when an agent did exactly this and split the memory across two instances | FIXED-R4 — installer is sticky: existing registration (tokenFile/vault recorded in the plugin entry) is adopted when no flags are given; explicit flags re-register with a loud warning |
| R4-17 | P1 | Agent skill gave no infrastructure boundaries, so the agent tried to repair LAMF itself: re-ran the installer, ran `init --reset`, edited host config, killed servers | FIXED-R4 — SKILL.md gains a "NEVER do these" section: no installer runs, no init/reset, no config edits, no process kills; report to the operator and continue with workspace files |

| R4-18 | P2 | Direct record writes (CLI `remember`, HTTP/MCP `memory_remember` + `correct`) never triggered projection — the Obsidian vault stayed stale until the next spool capture or a manual `lamf project` (found in the field: record searchable but `01 Memory/` empty) | FIXED-R4 — `api.maybe_project(ctx)` (throttled 1/s) after remember+correct; `lamf serve` pins `ctx.vault`; CLI remember auto-discovers the vault (LAMF_VAULT → sibling `vault/` → `LAMF Vault/`, `00 Home.md` marker) |

## Updated final tally

- Round 1: 66 defects → 65 fixed, 1 waived (inherent).
- Round 2: 63 defects → 61 fixed, 2 accepted/open (R-15, R-16; documented).
- Round 3: 31 defects → 31 fixed.
- Round 4: 18 defects → 17 fixed, 1 accepted-documented (W-06).
- **Total: 178 defects found, 174 fixed, 4 waived/accepted with documentation.**
- Gates: package validator 8/8 checks PASS; runtime smoke suite 13/13 PASS;
  installer clean-HOME run + idempotent re-run + live exercises PASS.
