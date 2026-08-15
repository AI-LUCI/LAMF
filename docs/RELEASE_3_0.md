# LAMF 3.0 release and benchmark disclosure

Release date: 2026-08-15

## Protocol and security changes

LAMF 3 encrypts record bodies, titles, tags, and entities at rest. Search uses a
contentless FTS5 index containing 96-bit HMAC-SHA256 tokens derived from the local
instance key, not plaintext vocabulary. The index is disposable: opening a store
checks structural integrity and active-record coverage and rebuilds it from the
encrypted authoritative records when necessary.

The release also enforces context/orientation token budgets, rate-limits repeated
HTTP authentication failures, bounds the store work queue, normalizes and checks
encoded/Unicode secret forms, pins runtime dependencies, prevents installer
credential logging, and verifies optional optimization instructions against a
SHA-256 manifest. Windows data-file ACLs are built from protected per-file ACL
objects for owner, SYSTEM, and Administrators.

Validation included 41 passing protocol/runtime tests; a 14-stage inherited smoke
suite; the eight package checks; adversarial sanitizer and authentication cases;
concurrent writes; forced termination recovery; disk-full rollback; raw SQLite
plaintext canaries; and partial/corrupt search-index recovery. The dependency audit
found no known vulnerabilities, and Bandit reported no high or medium findings at
the validated revision.

These controls protect the local data format and service boundary. They do not
protect a compromised operating-system account, malicious administrator, exposed
instance key, or plaintext returned to an authorized client. The unsigned package
manifest detects drift but is not a signature.

## Store migration

`lamf migrate-v3 --data-dir PATH` creates and integrity-checks a backup before
changing a protocol-2 database or legacy protocol-3 blind-term index. A rehearsal
over 19,195 records preserved every record and the exact decrypted-content SHA-256,
completed in 22.844 seconds, and left a healthy 19,195-row keyed index. Keep the
backup until post-upgrade recall and deep verification pass.

## MemoryBench retrieval result

The final result is the median/representative quality from three fresh isolated
stores. Each run ingested 19,195 LongMemEval-derived documents and issued the same
500 frozen queries. No live LAMF memory was used.

| Metric | Established 2.x | LAMF 3.0 | Delta |
|---|---:|---:|---:|
| Ingest, docs/s | 199.995 | 264.826 | +32.4% |
| Disk amplification | 3.66013x | 2.64459x | -27.7% |
| Recall@5 | 0.329600 | 0.329600 | 0 |
| Recall@10 | 0.426067 | 0.426067 | 0 |
| MRR | 0.330252 | 0.330252 | 0 |
| nDCG@10 | 0.324238 | 0.324238 | 0 |
| Query p50 | 204.1751 ms | 129.6833 ms | -36.5% |
| Query p95 | 269.5887 ms | 169.6499 ms | -37.1% |
| Query p99 | 293.3827 ms | 185.0096 ms | -36.9% |

The measured code-path change is native BM25 over compact keyed FTS postings,
followed by decryption of only the winning records. Quality parity means the speed
result did not trade away any of the four frozen retrieval metrics. Results remain
machine- and fixture-specific and are not a universal performance guarantee.

## Optimization options benchmarked

The optional behavior layer exposes six independent switches, disabled by default:

1. `active-work-awareness`
2. `minimal-solution`
3. `selective-workflows`
4. `stale-context-guards`
5. `surgical-changes`
6. `verified-execution`

All 64 subsets (2^6), including all-off and all-on, were screened on the same
five-test coding fixture with a fixed model. Ten selected subsets then received two
confirmation repeats each, for 84 executions total. Every execution passed all five
tests. The fastest screening observation was `selective-workflows` plus
`verified-execution`: 8 tool calls, 28.072 seconds, $0.2640, and 2,261 output tokens,
versus all-off at 16 tool calls, 33.850 seconds, $0.2700, and 3,097 output tokens.
This is a small single-fixture experiment; interactions were non-additive, so the
release keeps modules opt-in and makes no claim that one subset is universally best.

The benchmark axes recorded for each option were task correctness, changed files
and lines, dependency-file creation, tool-call count and names, wall time, model
cost, input/cache/output token usage, permission denials, and the final result.

## Reproduction and provenance

The source revision validated before release is `5063dbd`. Benchmark results are
reported from isolated MemoryBench stores; optimization state was captured before
the matrix and restored afterward. Consult `benchmark-results/` and `benchmarks/`
for the repository's public synthetic benchmark harnesses. Do not point a benchmark
adapter at live memory or use private records as fixtures.
