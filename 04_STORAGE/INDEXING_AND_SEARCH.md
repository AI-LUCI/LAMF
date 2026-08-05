# Indexing and Search

Storage: `04_STORAGE/SCHEMA.sql`. Contracts: `DECISIONS.md` §F (capture bounds),
§H (sealed checkpoints), §N (index & cache invalidation), §K (taint).
Patched from v1: adds the §N invalidation rules, the §F capture bounds, the
§H startup rule (checkpoint + tail only — no full scan), and aligns the
acceleration/vector sections with the reconditioned contracts.

**The index is a candidate generator, never authority** (§N). Search results
always re-check scope, sensitivity, and supersession at read time before any
item is disclosed. Index deletion and full rebuild must preserve answers and
citations (T-index-rebuild).

## Deterministic indexes

- FTS5 over records (title/body/tags/entities — `records_fts`) and over spine
  events (`events_fts`, payload text/actor/type/scope/session). `events_fts` is
  **contentless** (`content=''`); triggers own ALL sync (no application-side
  FTS writes), and the documented rebuild is the U-02 DELETE+INSERT..SELECT —
  in the contentless-portable form pinned in `04_STORAGE/SCHEMA.sql` comments:
  `INSERT INTO events_fts(events_fts) VALUES('delete-all');` then
  `INSERT INTO events_fts(rowid, payload_text, actor, type, scope, session)
  SELECT rowid, coalesce(payload_json,''), actor, type, scope,
  coalesce(session,'') FROM events;`
  (SQLite forbids `DELETE FROM` on a contentless FTS5 table before 3.43's
  contentless_delete option — `delete-all` is the equivalent wipe step.)
  `records_fts` stores its own content: record bodies are field-level encrypted
  (`body_enc`, U-08a), so SQL triggers cannot index the body — the ingester
  (holding the per-record data key in the write transaction) owns
  INSERT/refresh, while triggers own the delete paths: purge-on-tombstone
  (U-08c) removes the FTS row the moment a record is tombstoned, and row
  DELETE removes it on hard delete. Rebuild: `DELETE FROM records_fts;` +
  app-side re-index of non-tombstoned records from decrypted content;
- exact ID and content-hash indexes (`records.id`, `events.id`,
  `events.payload_sha256`, and the `payload_store` content-hash column) —
  exact-ID lookups return the exact record first (T-exact-lookup-p95);
- scope, owner, record type, sensitivity, state, and time indexes
  (`idx_records_*`, `idx_events_*` in SCHEMA.sql);
- graph adjacency (`edges`) for supports, contradicts, supersedes, depends_on,
  belongs_to, and related_to;
- entity aliases and channel identity links (`identity_links` — merge state per
  the identity-merge machine, `03_CONTRACTS/state-machines.md` §6; automatic
  merging forbidden, floor F6);
- hotset cache for active user/project/session/task, keyed by
  (record_id, record_version) (§N).

## Invalidation (DECISIONS.md §N)

- Hotsets and the capsule cache are keyed by **(record_id, record_version)**;
  capsules additionally carry the key **(policy_version, scope_set,
  record_watermark)** (`capsules` table, `03_CONTRACTS/state-machines.md` §5). Capsule
  validity is decided by **watermark comparison, not a membership table**:
  a capsule is valid iff `capsule.policy_version == head.policy_version` AND
  `capsule.record_watermark >= max(updated_seq over its scope_set)`
  (DECISIONS §U-12; `policy_version` = count of `policy_change` spine events,
  tracked in the single-row `policy_state` table; serve-time re-check against
  the committed head closes the WAL reader-snapshot race).
- **FTS purge-on-tombstone (DECISIONS §U-08c):** triggers DELETE the record's
  `records_fts` rows in the tombstoning transaction, and tombstone also deletes
  the record's `embedding_cache` rows — erased content leaves no searchable or
  vector residue (T-fts-purge-on-tombstone, T-erasure-checklist).
- Supersession, tombstone, contradiction, expiry, quarantine, and **any policy
  event** invalidate affected entries **synchronously, before the committing
  transaction returns**. A policy event invalidates **all** capsules
  (policy_version increments).
- A stale capsule is never served: it is recompiled, or omitted with a reported
  omission in the capsule response.
- Every search result item is re-checked at read time for scope, sensitivity,
  and supersession — a hit in any index or cache is a candidacy, not a
  disclosure decision (policy evaluation point: before disclosure,
  `03_CONTRACTS/mcp-tools.yaml`).

## Startup and capture bounds

- **Startup verification = latest sealed checkpoint + bounded tail only**
  (DECISIONS.md §H). The ingester verifies the newest `checkpoints` row
  (seq_hi, chain_head_hash, event_count, instance_sig) and the events after it;
  it never full-scans the chain at startup. Full-chain + payload-store
  verification is `lamf verify --deep` (scheduled/import-time only).
  Acceptance: T-startup-scan-budget.
- **Capture bounds (§F.3):** message body ≤ 32 KiB; tool-result excerpt ≤ 8 KiB
  (truncated with marker); single canonical event ≤ 64 KiB — larger payloads go
  to `payload_store` by reference (`payload_ref`). Indexing consumes only what
  passed these bounds plus sanitization; the sanitizer is fail-closed and no
  unsanitized byte can reach an index.
- Spool bounds (§F.4): 10,000 events / 256 MiB, drop-oldest + `spool_gap` event
  + operator alert on overflow; replay dedup key = (event id, payload_sha256)
  (`03_CONTRACTS/spool-format.md` §6).

## Search acceleration upgrades

- generated search manifest keyed by record content hash;
- incremental event-driven updates (spine seq watermark per index) rather than
  full scans — startup replays only the tail after the last checkpoint (§H);
- unchanged chunks are not re-tokenized or re-embedded (source-hash keyed);
- embedding cache key = model ID + canonical text hash + generation version
  (`embedding_cache`: model_id, source_hash, record_id, dim, version) —
  `record_id` (U-08d) lets tombstone purge delete a record's vectors;
- precompiled orientation and task capsules invalidated only by relevant
  changes — via the (record_id, record_version) and
  (policy_version, scope_set, record_watermark) keys above;
- single SQLite writer with WAL and a read connection pool (`SCHEMA.sql`
  pragmas; busy_timeout for writer contention);
- bounded raw-evidence fallback only after records miss — fallback queries
  exclude events whose payload keys are destroyed (crypto-shredded payloads are
  unrecoverable by construction) and apply the same redaction filter as the
  retrieval pipeline (DECISIONS.md §L);
- RRF (reciprocal rank fusion) instead of allowing vector scores to dominate;
- current authoritative records outrank superseded summaries; superseded items
  are historical and never default authority (`include_superseded` surfaces
  them explicitly, labeled);
- negative filters (scope, sensitivity, tombstoned/quarantined exclusion,
  expiry) are applied before semantic retrieval;
- query budgets limit candidates, graph expansion depth, and token output;
  capsule output is bounded by `context.capsule_max_tokens`.

## Optional vectors

Vectors run locally by default and may be disabled entirely — all functional
search tests must pass with embeddings off (T-vectors-optional).
`embedding_cache` stores model ID, dimension, source hash, owning `record_id`
(U-08d — tombstone purge deletes the record's vectors), and generation
version per vector. A provider/model change invalidates only the rows with the
old model_id/version; records are never re-embedded when their source hash is
unchanged. Vector caches are EXCLUDED from export bundles and always rebuilt
from the spine on import (DECISIONS.md §M.3/§M.8).

## Retrieval order (normative)

1. negative filters (scope/sensitivity/state/expiry) → candidate set;
2. FTS5 rank + graph expansion (bounded depth) → ranked candidates;
3. optional vector similarity → RRF fusion with (2);
4. read-time authority re-check per item (scope, sensitivity, supersession,
   taint labeling) — policy decision, receipts per `receipts.read` (F10);
5. return with citations (`source_events`) and taint labels per item (§K).
