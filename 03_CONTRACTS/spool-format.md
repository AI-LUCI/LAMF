# Spool Format — Capture Buffer Between Hook and Ingestion

Status: **normative**. Implements `DECISIONS.md` §F (capture pipeline & bounds) and
§G (event fields, LAMF-CANON-1). The spool is the crash-durable buffer on the
capture path `hook → sanitize → spool → ack → async ingestion`.

---

## 1. Purpose and placement

The spool decouples the host runtime (e.g. the OpenClaw Gateway) from LAMF
ingestion. The capture hook must never block on indexing, record promotion, or
policy evaluation beyond the synchronous sanitizer. Everything that can fail
slowly happens after `ack`.

Pipeline (normative order, `DECISIONS.md` §F):

```
hook ──▶ sanitize (server-side, synchronous, fail-closed)
     ──▶ payload spill (oversized payloads → payload_store, §2)
     ──▶ spool append (fsync per deployment config, §4)
     ──▶ ack to hook                                  (p95 ≤ 200 ms)
     ──▶ async ingestion (chain assign seq/hash/sig, ingest to SQLite, index)
```

**Fail-closed rule:** if the sanitizer is unavailable or fails, the event is
dropped, a `capture_dropped` gap event is emitted, and the operator is alerted.
Nothing reaches the spool unsanitized. Never fail open.

## 2. On-disk layout

The spool lives under `<data-dir>/spool/` as **append-only JSONL segments**:

```
<data-dir>/spool/
  segment-000001.jsonl      # active (tail) segment
  segment-000002.jsonl      # sealed, older
  ...
```

- **One canonical event per line.** Each line is the LAMF-CANON-1 serialization
  of the event (see `canonical-hashing.md`) followed by a single `\n` (U+000A).
  No other framing, no length prefixes, no pretty-printing.
- **Segment rotation at 64 MiB.** When appending the next line would exceed
  64 MiB in the active segment, the segment is sealed (fsync + rename is not
  required; the numeric name is fixed at creation) and a new segment with the
  next monotonic number is opened. Sealed segments are never modified except by
  the compaction maintenance op (`DECISIONS.md` §L).
- **Max event size 64 KiB.** A single canonical event line MUST NOT exceed
  64 KiB (65,536 bytes including the newline). Events whose canonical size would
  exceed this bound carry their payload by reference (`payload_ref` into the
  payload store, per `DECISIONS.md` §G/§F.3) instead of inline. The async
  ingester enforces the bound again and quarantines violating lines rather than
  aborting replay.
- **Payload spill is pinned (U-04).** An oversized payload (> 4 KiB canonical)
  is written to the SQLite `payload_store` **BEFORE the spool append**; the
  spool line then carries `payload_ref` + `payload_sha256`. A spilled blob is at
  most **1 MiB**; a larger payload ⇒ `capture_dropped` (never a partial write).
  The ack is returned only **after spill + spool-append** (and the §4 fsync),
  so an acked event never references a missing blob. Spill rows orphaned by a
  crash between spill and append (no spool line / no spine event references
  them) are garbage-collected at checkpoint time.
- **Null payload storage (U-05).** A JSON `null` payload is carried inline as
  the canonical 4-byte text `null` — never elided. In SQLite it is stored as
  the text `'null'`, never SQL NULL (see `04_STORAGE/SCHEMA.sql` events).
- Segment file permissions: `0600`, owned by the LAMF service account.

### Spool-line event fields

Spool lines use the §G event field names exactly as in
`schemas/event.schema.json`: `id`, `seq`, `ts`, `actor`, `session`, `type`,
`scope`, `sensitivity`, `taint`, `payload`/`payload_ref`, `payload_sha256`,
`prev_hash`, `hash`, `sig`, plus the optional `channel`, `sanitizer_note`, and
`capture_sig`.

At spool-append time the event is **pre-chain**: `seq`, `prev_hash`, `hash`,
and `sig` are not yet knowable. There is exactly ONE representation (U-04 —
the pre-signed alternative is deleted):

- **Deferred (the only form):** the spool line omits `seq`, `prev_hash`,
  `hash`, `sig` entirely. The async ingester assigns `seq` (strictly
  monotonic), computes `prev_hash`/`hash` per LAMF-CANON-1, and produces the
  spine `sig` with the actor key at ingestion. If the adapter signed at capture
  time, that hook-side signature is carried as the **top-level optional field
  `capture_sig`** (base64url) — it attests capture content and is preserved in
  the finalized event; it is never a substitute for the spine `sig`.

## 3. Ack semantics

`ack` is returned to the capture hook **after** sanitize succeeds **and** any
oversized payload has been spilled to `payload_store` (§2) **and** the event
line has been appended to the active segment **and** the segment write has
been flushed per the fsync configuration (§4). An ack therefore means:
*sanitized, spilled, and crash-durable in the spool*. It does **not** mean
ingested, indexed, or promoted. The 200 ms p95 ack budget (`DECISIONS.md`
§F.3) covers sanitize + spill + append + fsync only.

If the append or fsync fails, the hook receives a negative ack, the event is
treated as dropped, and a `capture_dropped` event is emitted as soon as the
spool is writable again.

## 4. fsync configuration (U-17: deployment config, never a policy key)

fsync behavior is a **deployment configuration** in the runtime file
config/server.json (lives in the instance's config directory at deployment,
not in this package), key `durability.fsync` — read at startup; changes require
a service restart. It is **not** a security-policy key and never appears in
`profiles/*.yaml` or the policy schema:

- **Default (durable):** `durability.fsync: "per-append"` — `fsync` the segment
  file after every append, before ack.
- **Batched (operator opt-in, non-default):** `durability.fsync: "batched"` —
  fsync at most every 100 ms or 64 events, whichever first. This trades up to
  100 ms of spool loss on power failure for lower latency and MUST be surfaced
  by `lamf doctor`.
- On segment rotation: fsync the sealed segment and fsync the spool directory
  (so the new segment's directory entry is durable).
- On clean shutdown (`lamf stop`): fsync all segments and the directory.

## 5. Bounds and overflow (`DECISIONS.md` §F.4)

The spool is bounded at **10,000 events OR 256 MiB**, whichever is reached
first. On overflow:

1. **drop-oldest**: the oldest un-ingested event line(s) are discarded to make
   room. Ingested lines are removed by normal segment retirement, so overflow
   drops only affect the un-ingested tail.
2. Emit a **`spool_gap` event** recording: drop window (`first_dropped_id`,
   `last_dropped_id` or count), reason (`spool_overflow`), and the ingester
   high-water mark. The gap event is itself spooled and chained like any event.
3. **Alert the operator** (log + `lamf status` surfaces the gap until
   acknowledged).

The spool MUST never block the host Gateway and MUST never lose events
silently — every loss is a visible `spool_gap` or `capture_dropped` spine event.

## 6. Replay and idempotency

On startup or after a crash, the ingester replays un-ingested spool lines.
Replay MUST be idempotent; the dedup key is:

```
(event.id, payload_sha256)
```

- `(id, payload_sha256)` already present in the `events` table ⇒ the line is a
  duplicate from a pre-crash ack; skip it (count as replayed-duplicate).
- Same `id` with a **different** `payload_sha256` is an integrity anomaly: the
  line is quarantined, a `quarantine` event is emitted, and the operator is
  alerted. Never silently overwrite.
- Replay assigns `seq` in spool order (segment number, then line offset) so the
  chain order matches capture order.
- The ingester's durable progress marker — the replay high-water mark — lives in
  the **`ingester_state` table** (`04_STORAGE/SCHEMA.sql`, single row:
  `high_water_seq`, `updated_ts`), updated transactionally with each ingest
  batch (U-17). The `spool_gap` drop window in §5 is recorded against this
  watermark.
- Acceptance tests: crash-restart replay and duplicate-line idempotency are
  covered by **T-crash-replay-idempotent**.

## 7. Segment retirement

Once all lines in a sealed segment are ingested and covered by a `checkpoint`
(`DECISIONS.md` §H), the segment MAY be deleted or compacted. Compaction
(rewriting sealed segments minus crypto-shredded payloads, `DECISIONS.md` §L)
preserves hashes via a compaction checkpoint event.
