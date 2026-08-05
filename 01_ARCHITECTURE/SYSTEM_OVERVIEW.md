# System Overview — Normative Architecture

This is the normative architecture of LAMF. Where any other document disagrees with
this file, `DECISIONS.md` wins and this file is aligned to it. Binding contracts for
each mechanism are in `03_CONTRACTS/`; security invariants are in
`02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`.

## 1. Three layers and the authority rule

| layer | responsibility | contents |
|---|---|---|
| **Witness Spine** | record what happened, attributed and tamper-evident | append-only hash-chained JSONL event segments, payload store (content-addressed), sealed checkpoints |
| **Revisioned Memory Records** | compile evidence into current, usable memory | revisioned records with supersession, contradiction, expiry, tombstone lifecycle; scopes and sensitivity classes |
| **Associative Index** | make retrieval fast | SQLite FTS5, exact ID/hash indexes, relationship graphs, hotsets, capsule cache, optional local vector cache |

**Authority rule.** The Associative Index is a candidate generator, never authority.
The Witness Spine and Revisioned Memory Records are authority. Every search result is
re-checked for scope, supersession, contradiction, and redaction at read time
(`04_STORAGE/INDEXING_AND_SEARCH.md`); a vector or FTS hit never becomes truth because
it ranked well. Every index and cache is rebuildable from spine + records
(rebuildability rule, section 7).

## 2. Capture pipeline

Normative order (DECISIONS section F):

```text
hook -> sanitize (fail-closed) -> spool -> ack -> async ingestion
```

1. A harness adapter hook or REST/MCP call submits a capture
   request with actor, session, channel, and taint metadata.
2. **Sanitize** runs server-side, synchronously, BEFORE any byte reaches the spool.
   Detection is source-based (path/keyword exclusions per
   `02_SECURITY/SECRET_PATTERNS.md`) AND value-based (known-prefix patterns,
   Shannon-entropy detector, operator-registered secret values). If the sanitizer is
   unavailable or fails: drop the event, emit a `capture_dropped` gap event, alert
   the operator. Never fail open.
3. **Spool**: bounded local queue, 10,000 events or 256 MiB
   (`03_CONTRACTS/spool-format.md`). Overflow: drop-oldest + `spool_gap` event +
   operator alert. The host Gateway is never blocked; loss is never silent.
4. **Ack**: returned to the caller only after the sanitized event is durably spooled.
   Target p95 <= 200 ms (`08_BUILD_PLAN/BENCHMARKS.md`).
5. **Async ingestion**: canonicalize (LAMF-CANON-1), hash, sign, append to the spine,
   update records and indexes in one serialized-writer transaction.

Bounds: message body <= 32 KiB; tool-result excerpt <= 8 KiB (truncated with marker);
single event canonical size <= 64 KiB — larger payloads go to the payload store by
reference (`payload_ref` = sha256).

## 3. Event chain and sealed checkpoints

Events are pinned by `03_CONTRACTS/schemas/event.schema.json`: `id` (UUIDv7),
`seq` (strictly monotonic per instance — **seq is the ordering authority; `ts` is
advisory**), `ts`, `actor`, `session`, `type`, `scope`, `sensitivity`, `taint`,
`payload` XOR `payload_ref`, `payload_sha256`, `prev_hash`, `hash`, `sig`.
`hash` = SHA-256 over LAMF-CANON-1 bytes (`03_CONTRACTS/canonical-hashing.md`);
`sig` = the actor's Ed25519 signature over the hash.

**Sealed checkpoints.** Every 1,000 events OR 24 h (whichever first), the instance
writes a `checkpoint` event and a `checkpoints` SQLite row:
`(seq_hi, chain_head_hash, event_count, instance_sig)`.

- **Routine startup verifies ONLY the latest checkpoint row plus the events after it**
  (bounded tail). There is no full-memory scan at startup.
- **Full-chain verification is `lamf verify --deep`** (whole chain + payload store),
  run scheduled and at import time.
- Export bundles include the latest signed checkpoint; import verifies it and the
  operator confirms the head fingerprint out-of-band
  (`07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`).

## 4. Records lifecycle

Records move `draft -> active -> {superseded, contradicted, expired, tombstoned}`;
tombstoned is terminal, every transition emits a spine event, and contradiction
defaults to the review queue. Full machines (record, quarantine, approval, handoff,
capsule, identity merge, council): `03_CONTRACTS/state-machines.md` and
`03_CONTRACTS/council.md`.

Erasure is crypto-shredding (floor F7): per-record AES-256-GCM data keys wrapped by
the instance key; erasure = tombstone + destroy the data key + `record_tombstoned`
event; payload blobs addressed only by that record are shredded. Segment compaction
is an internal maintenance op that preserves hashes via a compaction checkpoint.

## 5. Runtime data directory layout

```text
<data-dir>/
  events/            append-only JSONL segments (sealed by checkpoint)
  payloads/          content-addressed payload store (sha256 names)
  state/index.sqlite index + records + state DB (single-writer WAL, read pool)
  spool/             bounded capture spool (see section 2)
  quarantine/        encrypted-at-rest quarantine; excluded from search and export
  policy.yaml        active policy; changes recorded as versioned spine events
  secrets/           0600 token/key material; never exported, never in Git
```

Checkpoint rows live in the state DB; the head is mirrored alongside the segments.
Quarantine is encrypted at rest, excluded from search, and excluded from export
unless explicitly approved first (`03_CONTRACTS/state-machines.md`).

## 6. Concurrency: single-writer WAL + read pool

`state/index.sqlite` runs in WAL mode with exactly one serialized writer and a
concurrent read pool. Cache invalidation (supersession, tombstone, contradiction,
expiry, quarantine, policy events) is applied synchronously before the committing
transaction returns; hotsets and capsule cache are keyed by
`(record_id, record_version)`; capsules are valid only for
`(policy_version, scope_set, record_watermark)`.

## 7. Rebuildability rule

Everything outside `events/`, `payloads/`, and the record data is disposable: the
FTS index, graph tables, hotsets, capsule cache, and vector cache can be dropped and
rebuilt from spine + records at any time with identical answers and citations.
Foreign `state/index.sqlite` files and vector caches are never trusted on import —
they are always rebuilt (floor F4).
