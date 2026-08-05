# Benchmarks

Performance targets and the harness that proves them. A benchmark is met only when
measured by this harness on a reported machine baseline.

> **Status as of 2026-08-01: all runtime targets measured and passing.** The
> normative 100,000-record run is preserved in
> `../benchmark-results/lamf-100k-windows-2026-08-01.json` and is reproducible with
> `../tools/run_benchmarks.py`. These measurements describe LAMF on the reported
> machine only; they are not cross-product claims about ai-memory.

## Targets

| # | metric | target | verifying test |
|---|---|---|---|
| 1 | capture acknowledgement | p95 <= 200 ms | T-capture-ack-p95 |
| 2 | exact ID/hash lookup | p95 <= 50 ms | T-exact-lookup-p95 |
| 3 | warm FTS search | p95 <= 300 ms @ 100,000 chunks | T-fts-p95 |
| 4 | deterministic context capsule compilation | p95 <= 2 s (no LLM) | T-capsule-p95 |
| 5 | routine startup | no full-memory scan: verify latest checkpoint + <= 1,000 tail events | T-startup-scan-budget |
| 6 | sanitizer false-positive rate | <= 0.1% on the ordinary-corpus fixture | T-secret-fixtures |

## Executed result: Windows, 2026-08-01

| metric | target | measured p95/result | status |
|---|---:|---:|---|
| capture acknowledgement | <= 200 ms | 1.2324 ms | PASS |
| exact ID lookup | <= 50 ms | 0.2321 ms | PASS |
| exact hash lookup | <= 50 ms | 0.1648 ms | PASS |
| warm FTS search at 100,000 records | <= 300 ms | 1.8460 ms | PASS |
| deterministic context capsule | <= 2,000 ms | 10.2437 ms | PASS |
| routine startup verification | <= 1,000 events | 1,000 events / 102.6277 ms | PASS |
| sanitizer false-positive rate | <= 0.1% | 0 / 10,000 (0%) | PASS |

The planted 200-query retrieval corpus had zero misses. Fixture construction took
386.97 seconds through the encrypted production record path; bulk ingest throughput
is reported transparently but is not yet a normative gate.

Capture-ack is measured within the capture bounds of
`01_ARCHITECTURE/SYSTEM_OVERVIEW.md` section 2 (message <= 32 KiB, tool excerpt <=
8 KiB, event <= 64 KiB). Sanitization runs inside the ack budget.

## Harness sketch

### Fixture: 100k-chunk generator

A deterministic generator (seeded, to be checked into the test suite) produces 100,000
memory-record chunks across the record types of
`03_CONTRACTS/schemas/memory-record.schema.json`:

- distribution: ~40% facts/observations, 15% preferences, 10% decisions, 10% tasks,
  10% procedures, 5% failures/lessons, 5% episodes, 5% relationships/handoffs;
- chunk sizes log-normal, median ~600 bytes, max 4 KiB (inline payload limit);
- a planted query corpus: 200 queries with known correct answers and citations
  (exact-ID, keyword, paraphrase, scoped, and superseded-record traps);
- sensitivity mix: 80% ordinary, 15% sensitive, 5% restricted; scopes: 3 agents +
  1 shared scope; taint mix per `03_CONTRACTS/schemas/event.schema.json`.

The generator emits spine events first, then derives records, then builds indexes —
the same path as production ingestion.

### Fixture: ordinary corpus (sanitizer false-positive budget)

A deterministic generator (seeded, to be checked into the test suite) produces an
**ordinary corpus**: >= 10,000 ordinary-class captures (chat messages, tool
excerpts, file drops) that contain NO secrets — everyday prose, documentation
snippets, source code without credentials, URLs, UUIDs, hashes, and base64
lookalikes deliberately included as near-miss bait. Row 6 is met when the
sanitizer (`02_SECURITY/SECRET_PATTERNS.md` detector set: source exclusions,
known-prefix patterns, entropy detector, operator-registered values) flags at
most 0.1% of the corpus (<= 10 per 10,000) as secret-bearing. Every flag in
excess of the budget is a defect against the responsible detector, not a reason
to weaken detection; the corpus grows with each found false positive.

### Methodology

- **Warm**: after a routine startup and one unmeasured warm-up pass over the query
  corpus (hotsets/caches populated as in normal operation).
- **Cold** (reported for information, not gated): first run after process start with
  OS page cache dropped where the platform allows.
- Each query/operation is executed >= 200 times; wall-clock latency recorded per run.
- **p95** = the 95th-percentile latency of the recorded runs (nearest-rank method).
- Startup budget: instrument the verifier to count events verified at routine
  startup; the count must equal (events after latest checkpoint) and be <= 1,000;
  wall time is reported but the gate is the count.
- All benchmark runs are executed with embeddings disabled (vectors optional per
  T-vectors-optional) and Git absent (`git.mode: off`).

### Machine baseline fields to report

Every reported result includes: CPU (model, cores), RAM, storage type (NVMe/SATA/SSD
class), OS + version, filesystem, Rust/toolchain versions, SQLite version, LAMF
build hash, dataset seed, profile under test, and warm/cold mode. Results without a
baseline block are not comparable and do not close the gate.
