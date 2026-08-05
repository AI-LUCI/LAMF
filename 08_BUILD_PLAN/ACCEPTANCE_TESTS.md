# Acceptance Tests

Every test has a stable ID (`T-<kebab>`), a name, the spec that defines it (a path
that exists in the package tree, `DECISIONS.md` section A), and a pass criterion.
Priorities: **P0** = integrity/privacy/profiles (block any release), **P1** =
retrieval, interfaces, continuity, portability, **P2** = optional Git.

## P0 — integrity and privacy

- **T-canonical-hash-parity — cross-language canonical hash parity**
  (spec: `03_CONTRACTS/canonical-hashing.md`, `03_CONTRACTS/golden-vectors.json`).
  Rust, TypeScript, and Python implementations of LAMF-CANON-1 reproduce every hash
  in `03_CONTRACTS/golden-vectors.json`. The Python leg IS `tools/validate_package.py`
  check 4.
- **T-crash-replay-idempotent — crash replay idempotence**
  (spec: `01_ARCHITECTURE/SYSTEM_OVERVIEW.md`, `03_CONTRACTS/spool-format.md`).
  Crash after spool write, after event commit, after record update, and after index
  update; restart replays to the same state with no lost or duplicated canonical
  event (verified by `seq` continuity and chain hashes).
- **T-identity-fail-closed — missing/invalid identity fails closed**
  (spec: `03_CONTRACTS/wire-protocol.md`, `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`).
  Requests with missing, expired, revoked, or mismatched actor credentials are
  denied; no event, record, or disclosure is produced; denial is logged.
- **T-prompt-cannot-escalate — prompt text cannot change authority**
  (spec: `02_SECURITY/THREAT_MODEL.md`, `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`).
  Adversarial prompt/memory text requesting role, scope, seat, or policy changes has
  zero effect on actor identity, authority, or policy (floor F5).
- **T-secret-fixtures — secret fixtures never leak**
  (spec: `02_SECURITY/SECRET_PATTERNS.md`, `01_ARCHITECTURE/SYSTEM_OVERVIEW.md`).
  Fixture secrets matching every class in `02_SECURITY/SECRET_PATTERNS.md` never reach spool,
  transport, logs, JSONL, SQLite, records, vectors, Git, or exports; sanitizer
  failure drops the event with a `capture_dropped` gap event (fail-closed).
- **T-events-append-only — raw events immutable**
  (spec: `04_STORAGE/SCHEMA.sql`, `01_ARCHITECTURE/SYSTEM_OVERVIEW.md`).
  No API can edit or delete a spine event; attempted UPDATE/DELETE on the events
  table is rejected (no such code path exists) and the chain still verifies
  (`lamf verify --deep` exit 0) afterwards.
- **T-supersession-authority — superseded records are not authority**
  (spec: `03_CONTRACTS/state-machines.md`, `03_CONTRACTS/schemas/memory-record.schema.json`).
  Superseded records remain retrievable as history but are never served as current
  authority; read-time re-check holds even with a stale index entry.
- **T-index-rebuild — index rebuild preserves answers**
  (spec: `04_STORAGE/INDEXING_AND_SEARCH.md`, `01_ARCHITECTURE/SYSTEM_OVERVIEW.md`).
  Delete `state/index.sqlite` and all caches; rebuild from spine + records; the
  standard query corpus returns identical answers and citations.
- **T-startup-scan-budget — no full scan at startup**
  (spec: `01_ARCHITECTURE/SYSTEM_OVERVIEW.md`, `08_BUILD_PLAN/BENCHMARKS.md`).
  Routine startup verifies the latest sealed checkpoint plus <= 1,000 tail events;
  measured startup verification work is independent of total chain length.

- **T-chain-splice-rejected — chain splice/reorder detected**
  (spec: `01_ARCHITECTURE/SYSTEM_OVERVIEW.md`, `03_CONTRACTS/canonical-hashing.md`).
  Delete, reorder, or substitute events anywhere in a segment (including between
  two sealed checkpoints); `lamf verify --deep` exits 5 and names the first `seq`
  whose `prev_hash` link or signature breaks.
- **T-duplicate-key-rejected — duplicate JSON keys rejected at parse**
  (spec: `03_CONTRACTS/canonical-hashing.md`). A canonical payload containing a
  duplicate object key is rejected at parse time on every ingestion surface
  (spool replay, REST `/v1/events`, MCP, import); no event is committed and no
  hash is computed over the ambiguous document.
- **T-sensitivity-payload-ref — non-ordinary events must use payload_ref**
  (spec: `04_STORAGE/SCHEMA.sql`, `DECISIONS.md` §U-08b).
  Inserting an event with `sensitivity='sensitive'` or `'restricted'` and an
  inline `payload_json` (no `payload_ref`) is rejected by the `events` CHECK
  constraint; the same event with `payload_ref` is accepted; `ordinary` events
  are accepted in either form.
- **T-quarantine-key-shredded — quarantine purge destroys the item key**
  (spec: `03_CONTRACTS/state-machines.md`, `04_STORAGE/SCHEMA.sql`).
  Purging (or TTL-expiry auto-purging) a quarantined item deletes its per-item
  data-key row in `record_keys` and its encrypted blob; post-purge the ciphertext
  is unrecoverable and a `quarantine` (state=purged) spine event exists.
- **T-fts-purge-on-tombstone — tombstone purges FTS rows**
  (spec: `04_STORAGE/SCHEMA.sql`, `04_STORAGE/INDEXING_AND_SEARCH.md`).
  When a record is tombstoned, triggers delete its `records_fts` rows in the same
  transaction; a post-tombstone MATCH on unique tokens from the record body
  returns zero rows, while the `record_tombstoned` event remains on the spine.
- **T-erasure-checklist — full erasure closes every residual copy**
  (spec: `01_ARCHITECTURE/SYSTEM_OVERVIEW.md`, `04_STORAGE/SCHEMA.sql`).
  After erasing a record: its `body_enc` is unreadable (data key destroyed), its
  `record_keys` row is gone, its FTS and `embedding_cache` rows are deleted,
  stale capsule rows are hard-deleted and the capsule watermark is bumped,
  receipts reference it by id+hash only (never title/body), and
  `lamf verify --deep` accepts the `record_tombstoned` event + destroyed key as
  proof-of-erasure without rehashing the shredded payload.
- **T-taint-inheritance — derived content inherits strictest taint**
  (spec: `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`, `03_CONTRACTS/state-machines.md`).
  A record/capsule derived from `source_events` computes effective taint as the
  strictest source taint and effective sensitivity as the MAX of its sources;
  caller-supplied values that would lower either are ignored (write-time server
  computation), and values that raise them are honored.
- **T-remember-laundering-blocked — tainted recall cannot launder into durable memory**
  (spec: `03_CONTRACTS/mcp-tools.yaml`, `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`).
  `memory_remember` by an agent actor whose `source_events` include `tool_output`
  or `external_content` never auto-promotes in any of the five setup choices;
  the item lands in `draft`/review (or is denied per policy) with the taint
  label preserved.
- **T-registered-secret-value — operator-registered values are blocked**
  (spec: `02_SECURITY/SECRET_PATTERNS.md`). A value registered via the secrets
  registry is detected by exact-substring match at capture (event dropped,
  `capture_dropped` emitted) and by the export re-scan; the plaintext value
  appears in no log, spool, SQLite table, or bundle — only its salted hash.
- **T-export-secret-rescan — export re-scan blocks late-registered secrets**
  (spec: `02_SECURITY/SECRET_PATTERNS.md`, `07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`).
  A secret captured before its detector/registration existed passes capture;
  `lamf export` then re-scans with the CURRENT detector set and refuses to build
  the bundle, producing an itemized, receipted report naming the matching records.
- **T-export-mac-verified — manifest MAC is verified at import**
  (spec: `07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`, `03_CONTRACTS/schemas/export-manifest.schema.json`).
  Import recomputes `HMAC-SHA-256(key=HKDF-SHA-256(export_key,
  info="lamf-manifest-mac"), msg=canon(manifest_without_mac) || canon(checksums))`;
  flipping one byte in the manifest or any checksum entry fails MAC verification
  and refuses the import (exit 5) before staging.
- **T-export-tamper-rejected — tampered bundle is refused**
  (spec: `07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`).
  Modify any bundle file, remove a file, or alter the bundle's checksums file
  after export; import detects the mismatch (MAC/checksum/chain verification)
  and refuses with exit 5, leaving the data directory untouched.
- **T-export-wrong-passphrase — wrong passphrase fails closed**
  (spec: `07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`). Import with an incorrect
  passphrase fails Argon2id/XChaCha20-Poly1305 authentication, extracts zero
  files, stages nothing, and exits 5; no plaintext byte of the bundle is written.
- **T-dns-rebinding-rejected — L1 Host/Origin checks fail closed**
  (spec: `03_CONTRACTS/wire-protocol.md`). On L1 loopback, requests whose `Host`
  is outside `ALLOWED_HOSTS` or whose `Origin` does not match the allowlist are
  rejected with 403; a browser cross-origin POST from an attacker page never
  reaches the API.
- **T-pairing-ceremony-lockout — pairing code brute force locks out**
  (spec: `03_CONTRACTS/wire-protocol.md`). Five failed pairing-code attempts
  trigger lockout with exponential backoff; codes are single-use, expire in
  <= 10 minutes, carry >= 128-bit entropy, and are issued only after out-of-band
  operator confirmation; comparisons are constant-time.
- **T-instance-key-anchored — import anchors on the instance key (TOFU)**
  (spec: `07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`).
  Import verifies the bundled checkpoint against the instance public key pinned
  in the manifest and requires operator out-of-band confirmation of the displayed
  fingerprint; a bundle whose checkpoint is signed by a different key, or an
  unconfirmed fingerprint, refuses the import (exit 5).

## P0 — security profiles

- **T-five-profiles-shown — setup shows exactly five choices**
  (spec: `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`, `03_CONTRACTS/CLI_REFERENCE.md`).
  `lamf init` displays exactly the four fixed profiles (`locked`, `controlled`,
  `trusted-local`, `open-local`) plus the AI-Custom path, which is completed by
  generating a policy and applying it via `lamf security apply`; no fifth fixed
  profile and no other choice is offered.
- **T-profile-locked — Locked gates everything meaningful**
  (spec: `02_SECURITY/profiles/locked.yaml`, `02_SECURITY/FEATURE_MATRIX.md`).
  Every configured disclosure and durable promotion is approval-gated; ordinary
  capture lands in quarantine; automatic context injection is off.
- **T-profile-controlled — Controlled default semantics**
  (spec: `02_SECURITY/profiles/controlled.yaml`, `02_SECURITY/FEATURE_MATRIX.md`).
  Same-scope ordinary recall is automatic; sensitive and cross-scope recall and
  protected changes are gated.
- **T-profile-trusted-local — Trusted Local semantics**
  (spec: `02_SECURITY/profiles/trusted-local.yaml`, `02_SECURITY/FEATURE_MATRIX.md`).
  Registered local actors share ordinary memory automatically; restricted scopes
  remain protected; sensitive capture is protected_automatic.
- **T-profile-open-local — Open Local semantics**
  (spec: `02_SECURITY/profiles/open-local.yaml`, `02_SECURITY/FEATURE_MATRIX.md`).
  No per-access approval among registered local actors; anonymous and network actors
  are rejected; sensitive capture is sanitized_automatic.
- **T-profile-ai-custom — AI-Custom generation path**
  (spec: `06_SETUP/AI_CUSTOM_QUESTIONNAIRE.md`, `06_SETUP/AI_CUSTOM_PROFILE_GENERATOR.md`).
  A generated policy validates against the schema, preserves the floor (restated
  clause by clause), displays an explanation, and applies only after confirmation.
- **T-floor-enforced — schema rejects floor violations**
  (spec: `03_CONTRACTS/schemas/security-policy.schema.json`, `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`).
  Negative-control corpus: `lamf security validate` rejects each of the following
  with the named clause — `model_self_approval: true` (F12 const false);
  `network.lan.enabled: true` without TLS and required auth (F12); any disabled
  secret exclusion, by value or by source (F11); a `secrets.excluded_sources`
  list missing any of the 16 baseline patterns (schema `allOf`+`contains`);
  plaintext or unauthenticated export settings (F3 consts); automatic channel
  merges (F6 enum floor); `council.max_seats_per_actor > 1` (schema const 1).
  On roles: the policy contains no role-derivation mechanism at all — there is
  nothing to reject because roles exist only via pairing
  (`03_CONTRACTS/wire-protocol.md`); prompt text cannot create one (F5).
- **T-policy-diff-versioned — policy changes are diffed and versioned**
  (spec: `03_CONTRACTS/schemas/security-policy.schema.json`, `03_CONTRACTS/CLI_REFERENCE.md`).
  Every policy change shows an effective diff, requires step-up confirmation, honors
  the downgrade cooldown, and is recorded as a versioned spine event.
- **T-approval-ttl-deny — approvals expire to deny**
  (spec: `03_CONTRACTS/state-machines.md`, `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`).
  A pending approval past `approvals.ttl_hours` transitions to expired = denied;
  rate limits hold; every transition is receipted (floor F8).
- **T-receipts-minimum — minimum observability**
  (spec: `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`).
  Sensitive-category disclosures are always itemized; aggregation is possible only
  for ordinary reads; export/import/merge/policy-change/approval/quarantine-purge
  events are always logged with actor identity (floor F10).

- **T-model-self-approval-rejected — an agent never approves its own request**
  (spec: `03_CONTRACTS/schemas/security-policy.schema.json`, `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`).
  `model_self_approval` is a schema const `false`; an approval decision whose
  approver equals the requesting agent actor is rejected, emits no state change,
  and is logged; a policy file setting `model_self_approval: true` fails
  `lamf security validate` with the F12 clause id.
- **T-approval-receipts — every approval transition is receipted**
  (spec: `03_CONTRACTS/state-machines.md`, `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`).
  Each approval transition (pending → approved / denied / expired) emits exactly
  one `approval` spine event and one receipt whose `receipt_id` references
  `receipts(receipt_id)`; an operator can list the receipt for every decided
  approval in the fixture run.
- **T-approval-rate-limit — per-actor approval rate limit enforced**
  (spec: `03_CONTRACTS/schemas/security-policy.schema.json`, `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`).
  The schema accepts `approvals.rate_limit_per_actor_per_hour` only in [1, 240];
  at runtime the (limit+1)-th approval request from one actor within one hour is
  refused with a rate-limit denial (no pending row created) and the refusal is
  logged with actor identity (F8/F10).
- **T-step-up-receipt — step-up auth is fresh and receipted**
  (spec: `03_CONTRACTS/wire-protocol.md`, `03_CONTRACTS/state-machines.md`).
  Step-up auth accepts only an operator-credential assertion <= 5 minutes old
  (operator token over the L0 socket, or OS-brokered biometric); a stale
  assertion is rejected (exit 3), and a successful step-up is recorded as an
  `approval` spine event with `kind: step_up` plus a receipt.
- **T-auto-merge-forbidden — no profile merges identities automatically**
  (spec: `03_CONTRACTS/state-machines.md`, `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`).
  Under all five setup choices, no code path transitions an identity link to
  `merged` without an operator confirmation event; scripted attempts (API, MCP,
  replayed events) leave the link `proposed` and the attempt is receipted (F6).
- **T-merge-requires-confirmation — even strong_id_confirmed requires the operator**
  (spec: `03_CONTRACTS/state-machines.md`). With
  `sharing.cross_channel_merge: strong_id_confirmed` and valid cryptographic
  cross-channel proof, the merge is only PROPOSED; it becomes `merged` solely
  after operator confirmation, and the confirmation is receipted.
- **T-group-channel-scope — group channels resolve at channel scope**
  (spec: `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`, `05_INTEGRATIONS/OPENCLAW_INTEGRATION.md`).
  A message in a group channel containing two merged principals is served at
  channel scope only: search and capsules in that channel return zero items from
  either participant's private scope (F6).
- **T-capsule-restricted-excluded — automatic capsules never contain restricted items**
  (spec: `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`, `03_CONTRACTS/state-machines.md`).
  In every profile, automatic capsule compilation includes zero `restricted`
  items (F12 const), and `sensitive` items appear only when per-purpose itemized
  receipts are emitted for each one.

## P1 — retrieval and speed

- **T-exact-id-first — exact lookup ranks first**
  (spec: `04_STORAGE/INDEXING_AND_SEARCH.md`). An exact ID or content-hash query
  returns that record first, ahead of any FTS/vector candidate.
- **T-authority-ranking — authority beats similarity**
  (spec: `04_STORAGE/INDEXING_AND_SEARCH.md`). Current user-stated or approved memory
  outranks a more similar agent inference or a superseded summary.
- **T-scope-before-vector — scope filters precede vectors**
  (spec: `04_STORAGE/INDEXING_AND_SEARCH.md`). Scope and security filtering run
  before any vector similarity; no out-of-scope candidate reaches reranking.
- **T-fts-p95 — warm FTS p95 <= 300 ms @ 100k chunks**
  (spec: `08_BUILD_PLAN/BENCHMARKS.md`). Measured on the 100k-chunk fixture with the
  harness methodology and p95 definition of that file.
- **T-capsule-p95 — context capsule p95 <= 2 s without LLM**
  (spec: `08_BUILD_PLAN/BENCHMARKS.md`). Deterministic capsule compilation meets p95
  with embeddings disabled.
- **T-capture-ack-p95 — capture ack p95 <= 200 ms**
  (spec: `08_BUILD_PLAN/BENCHMARKS.md`, `01_ARCHITECTURE/SYSTEM_OVERVIEW.md`).
  Ack (after sanitize + spool) meets p95 within the section-F bounds.
- **T-exact-lookup-p95 — exact lookup p95 <= 50 ms**
  (spec: `08_BUILD_PLAN/BENCHMARKS.md`).
- **T-no-rechunk — unchanged records not rechunked/re-embedded**
  (spec: `04_STORAGE/INDEXING_AND_SEARCH.md`). Content-hash-keyed manifests skip
  chunking and embedding for unchanged records across restarts.
- **T-vectors-optional — full function without vectors**
  (spec: `04_STORAGE/INDEXING_AND_SEARCH.md`). All functional search tests pass with
  embeddings disabled.
- **T-quarantine-lifecycle — quarantine state machine**
  (spec: `03_CONTRACTS/state-machines.md`). Quarantined items are encrypted at rest,
  excluded from search and export; approve ingests, purge destroys, TTL expiry purges;
  every transition emits a spine event.
- **T-capsule-policy-tighten — capsule invalidation on policy change**
  (spec: `03_CONTRACTS/state-machines.md`, `04_STORAGE/INDEXING_AND_SEARCH.md`).
  Any policy event or relevant record/quarantine change invalidates capsules keyed by
  `(policy_version, scope_set, record_watermark)`; a stale capsule is never served —
  it is recompiled or omitted with a reported omission.
- **T-deletion-crypto-shredding — erasure by crypto-shredding**
  (spec: `01_ARCHITECTURE/SYSTEM_OVERVIEW.md`, `03_CONTRACTS/state-machines.md`).
  Erasure tombstones the record, destroys its data key, shreds singly-addressed
  payload blobs, and emits `record_tombstoned`; raw-evidence fallback queries then
  exclude the shredded payload keys; ciphertext is unrecoverable.

- **T-record-lifecycle — record machine walks every pinned transition**
  (spec: `03_CONTRACTS/state-machines.md`, `03_CONTRACTS/schemas/memory-record.schema.json`).
  The fixture walks draft → active → superseded, active → contradicted → review
  resolution, active → expired, and active → tombstoned; each transition emits
  exactly one spine event of the pinned type, guards hold (superseder scope ⊆
  record scope, approver ≠ requester where required), and tombstoned is terminal
  (no outgoing transition succeeds).
- **T-expiry-keeps-evidence — expiry never deletes evidence**
  (spec: `03_CONTRACTS/state-machines.md`). An expired record is excluded from
  default serving yet remains retrievable as history with its source events
  intact; the expiry emits a `correction` (reason=expired) event, and the raw
  evidence chain verifies unchanged (`lamf verify --deep` exit 0).
- **T-quarantine-search-exclusion — quarantine invisible to retrieval**
  (spec: `03_CONTRACTS/state-machines.md`, `04_STORAGE/INDEXING_AND_SEARCH.md`).
  A quarantined item planted with unique tokens yields zero hits through FTS,
  graph expansion, vector similarity, and the bounded raw-evidence fallback, in
  every profile, until it is approved.

## P1 — interfaces

- **T-generic-mcp-client — generic MCP client round trip**
  (spec: `03_CONTRACTS/mcp-tools.yaml`, `03_CONTRACTS/wire-protocol.md`).
  A generic MCP client (not OpenClaw) performs capture, search, context, remember,
  handoff, and operator export using exactly the nine pinned tool names; agent actors
  are denied the operator-class tools `memory_approvals` and `memory_export`.

## P1 — OpenClaw

- **T-openclaw-fresh-install — fresh single-agent install**
  (spec: `05_INTEGRATIONS/OPENCLAW_INTEGRATION.md`, `07_PORTABILITY/NEW_OPENCLAW_COMPUTER.md`).
  A fresh OpenClaw install connects through the native memory plugin using only the
  install-contract commands.
- **T-orientation-first-session — orientation capsule on first turn**
  (spec: `03_CONTRACTS/mcp-tools.yaml`, `05_INTEGRATIONS/OPENCLAW_INTEGRATION.md`).
  The first session (fresh or post-import) receives a valid bounded orientation
  capsule with taint labels and the untrusted-data envelope notice.
- **T-checkpoints-nonblocking — lifecycle checkpoints never block**
  (spec: `05_INTEGRATIONS/OPENCLAW_INTEGRATION.md`, `01_ARCHITECTURE/SYSTEM_OVERVIEW.md`).
  `/new`, reset, compaction, and shutdown trigger sealed checkpoints; with the LAMF
  server down the Gateway proceeds normally and checkpoints catch up.
- **T-agent-scope-mapping — agentId to actor mapping**
  (spec: `05_INTEGRATIONS/OPENCLAW_INTEGRATION.md`). Each OpenClaw `agentId` maps via
  pairing to a distinct actor with a distinct private scope; no scope aliasing.
- **T-channel-identity — channel/thread identity preserved**
  (spec: `05_INTEGRATIONS/OPENCLAW_INTEGRATION.md`, `03_CONTRACTS/schemas/event.schema.json`).
  Captured events carry the optional `channel` object `{channel, channel_identity,
  thread}` (persisted in `events.channel_json`); a message replayed across two
  channels yields two events whose channel objects differ exactly in
  channel/channel_identity and whose sender attribution is unchanged.
- **T-wrong-merge-unmerge — merge requires confirmation; unmerge receipted**
  (spec: `03_CONTRACTS/state-machines.md`, `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`).
  No profile merges channel identities automatically (floor F6); a wrong merge is
  reversed by the unmerge workflow, which emits an inverse event and a receipt.
- **T-uninstall-preserves-data — uninstall removes owned config only**
  (spec: `05_INTEGRATIONS/OPENCLAW_INTEGRATION.md`, `03_CONTRACTS/CLI_REFERENCE.md`).
  `lamf adapter uninstall openclaw --keep-data` removes only plugin-owned config;
  the data directory and timestamped 0600 backups remain.
- **T-doctor-diagnostics — doctor finds the four failure classes**
  (spec: `03_CONTRACTS/CLI_REFERENCE.md`, `05_INTEGRATIONS/OPENCLAW_INTEGRATION.md`).
  `openclaw doctor` and `lamf doctor --adapter openclaw --deep` each identify:
  missing server, invalid token, stale plugin, policy mismatch.

## P1 — continuity

- **T-handoff-accept-once-fencing — exclusive accept with fencing**
  (spec: `03_CONTRACTS/state-machines.md`). An offered handoff is accepted exactly
  once (SQLite CAS on `(handoff_id, state='offered')`); the accepter receives a
  monotonic fencing token; accepting auto-expires other eligible handoffs for the
  same work item; A->B->A resume returns current state.
- **T-handoff-lease-expiry — lease expiry returns handoff**
  (spec: `03_CONTRACTS/state-machines.md`). A 30-minute lease left unrenewed expires,
  increments the fencing token, and returns the handoff to `offered`; stale-holder
  writes with the old fencing token are rejected.
- **T-scope-leakage — multi-agent scope isolation**
  (spec: `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`, `03_CONTRACTS/mcp-tools.yaml`).
  Across all profiles, agent A cannot read agent B's private scope through search,
  capsule, handoff, graph expansion, or raw-event fallback.
- **T-council-recorder-cannot-ratify — recorder alone never ratifies**
  (spec: `03_CONTRACTS/council.md`). A `council_decision` event ratifies only with
  >= quorum member signatures; a recorder signature alone fails verification.
- **T-provider-failure — failed model/provider is contained**
  (spec: `05_INTEGRATIONS/OPENCLAW_INTEGRATION.md`, `03_CONTRACTS/schemas/event.schema.json`).
  Per the provider-failure containment clause: a failed model/provider call emits a
  `failure` event carrying metadata only (provider, model, error class, latency);
  the session continues serving subsequent turns; no partial turn is promoted to
  memory; chain verification and pending handoffs are unaffected.

- **T-handoff-sibling-auto-expiry — accepting expires sibling offers**
  (spec: `03_CONTRACTS/state-machines.md`). Two eligible handoffs offered for the
  same work item: accepting one transitions the other to `expired` atomically
  with the accept (same transaction), and the expired sibling can no longer be
  accepted (CAS loses, conflict returned).
- **T-handoff-stale-fencing-rejected — stale fencing tokens never write**
  (spec: `03_CONTRACTS/state-machines.md`). After lease expiry increments the
  fencing token and a new accepter takes the handoff, complete/release requests
  carrying the old holder's token are rejected (token + holder mismatch), emit no
  state change, and the rejection is logged.
- **T-capsule-stale-never-served — stale capsule never reaches a consumer**
  (spec: `03_CONTRACTS/state-machines.md`, `04_STORAGE/INDEXING_AND_SEARCH.md`).
  After a record/quarantine change in the scope_set or any `policy_change` (which
  increments `policy_version`), a capsule whose key no longer matches — validity
  = `capsule.policy_version == head.policy_version` AND `capsule.record_watermark
  >= max(updated_seq over its scope_set)` — is never served; the serve-time key
  re-check against the committed head holds even under a WAL reader snapshot
  taken before the invalidating commit.
- **T-capsule-omission-reported — omissions are reported, never silent**
  (spec: `03_CONTRACTS/state-machines.md`). When a stale capsule cannot be
  recompiled within budget, the response contains a non-empty `omissions[]`
  entry naming what was left out; a capsule response with an omission and an
  empty `omissions[]` fails the test.
- **T-council-quorum-signatures — ratification requires quorum member signatures**
  (spec: `03_CONTRACTS/council.md`). A `council_decision` with fewer than
  floor(seats/2)+1 valid seat-bound member signatures (default quorum) fails
  ingester verification and is rejected at commit; with quorum met, each
  signature verifies against the actors table public key over the decision's
  canonical bytes; policy-raised quorums (two_thirds, unanimous) are enforced.
- **T-council-seat-not-model — seats bind to actors, never models**
  (spec: `03_CONTRACTS/council.md`). Swapping the model/provider behind an actor
  leaves seat authority unchanged; a vote whose `seat_id` is not bound to the
  signing actor is discarded with a `failure` event; prompt text naming a seat
  or role creates no binding.
- **T-council-handoff-roundtrip — council work item completes via the handoff ledger**
  (spec: `03_CONTRACTS/council.md`). A work item offered with the ratifying
  `council_decision` event id in `source_events` follows the ordinary handoff
  rules (accept-once CAS, fencing, 30-min lease); completion is authoritative in
  the handoff ledger, and council membership grants no scope exemption when the
  item is offered to a non-council actor.

## P1 — portability

- **T-export-import-clean-machine — clean-machine round trip**
  (spec: `07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`, `03_CONTRACTS/CLI_REFERENCE.md`).
  Export on computer A; on clean computer B: import --staged, rebind, verify --deep,
  activate; the same current records, policy profile, identities, and open handoffs
  are recovered and the standard query corpus answers identically.
- **T-import-path-traversal — unsafe bundle paths rejected**
  (spec: `07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`). Bundles containing `..`,
  absolute paths, symlinks, non-allowlist characters, or Windows device names are
  rejected before staging (floor F4).
- **T-import-only-tightens — weakening policy refuses import**
  (spec: `07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`, `03_CONTRACTS/schemas/security-policy.schema.json`,
  `03_CONTRACTS/CLI_REFERENCE.md` lamf import). Two legs (R3-03): **(a) clean-machine
  leg** — on an empty data directory there is no local profile, so the imported
  policy is compared against the **invariant floor** (per key, tighten lattice);
  an imported policy below any floor clause refuses the import. **(b)
  local-profile leg** — re-import into an already-initialized instance (which
  requires explicit operator confirmation): an imported policy weaker than the
  local profile on any key refuses the import. Tightening imports proceed in
  both legs.
- **T-needs-rebind — secrets reported, never exported**
  (spec: `07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`). Exported bundles contain no
  secret values; references appear as salted hashes flagged `needs_rebind`; import
  prompts for each before record restore.

- **T-quarantine-export-exclusion — quarantine never reaches a bundle**
  (spec: `03_CONTRACTS/state-machines.md`, `07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`).
  Build an export with quarantined items present; the bundle contains zero
  quarantine contents (items excluded unless approved first), and an imported
  instance shows no trace of the quarantined content.
- **T-import-never-auto-activates — import is always staged**
  (spec: `03_CONTRACTS/state-machines.md`, `03_CONTRACTS/CLI_REFERENCE.md`).
  `lamf import FILE.lamf --staged` completes with the live instance byte-identical
  (no `import` spine event, no policy change, no served record from the bundle)
  until `lamf activate` runs; import without `--staged` is a usage error (exit 2).
- **T-archive-extraction-limits — bundle extraction is bounded**
  (spec: `07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`). Import refuses archives
  exceeding 10,000 entries or 4 GiB uncompressed; entry names on the Windows
  device-name denylist (con, nul, aux, prn, com1–9, lpt1–9 — any case, any
  extension) are rejected outside the path regex, as are empty segments, `.`,
  `a//b`, `a/./b`, and trailing `/`; refusal happens before staging (exit 5).

## P2 — optional Git

- **T-git-off-core-passes — core suite passes with Git absent**
  (spec: `07_PORTABILITY/OPTIONAL_GIT.md`). Full P0/P1 suite passes with
  `git.mode: off` and no `git` binary on the machine.
- **T-git-local-commits — local mode produces coherent commits**
  (spec: `07_PORTABILITY/OPTIONAL_GIT.md`). Local mode creates coherent checkpoint
  commits of ordinary-class records; no sensitive/restricted content appears in any
  commit (floor F12).
- **T-git-failure-nonblocking — Git failure never blocks**
  (spec: `07_PORTABILITY/OPTIONAL_GIT.md`). Adapter failure leaves capture, search,
  policy, handoff, and export functional; a sync job catches up.
- **T-git-remote-explicit — remote never pushes without explicit policy**
  (spec: `07_PORTABILITY/OPTIONAL_GIT.md`, `03_CONTRACTS/schemas/security-policy.schema.json`).
  Remote mode pushes only with explicit policy plus operator-configured remote; the
  erasure non-support notice is displayed at enable time.
