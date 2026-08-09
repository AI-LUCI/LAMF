# Universal Memory Benchmark (UMB) v1

UMB is a deterministic, provider-neutral contract for comparing memory systems
and experimental adapters. A conforming result MUST include the fixture SHA-256,
seed, host/runtime metadata, adapter configuration, raw per-query results, and
aggregate metrics. The authoritative store MUST be disposable test data.

## Required metrics

| Dimension | Metric |
|---|---|
| Retrieval | Recall@k, Precision@k, MRR, nDCG@k |
| Performance | load throughput; write and search p50, p95 and p99 latency |
| Context economy | returned UTF-8 bytes and `ceil(bytes / 4)` deterministic token proxy |
| Governance | scope isolation and sensitive-canary leakage rate |
| Fidelity | provenance coverage, contradiction retention, false consolidation rate |
| Durability | result equivalence after adapter close/reopen |

The token proxy is intentionally tokenizer-independent and MUST NOT be described
as model-token usage. Accuracy is measured against logical relevance judgments;
one consolidated result can cite multiple authoritative source record IDs.

## Pass rules

All governance and fidelity metrics must be perfect. An experiment is a useful
candidate only when it preserves baseline retrieval quality and improves at least
one declared objective without a material latency regression. Results are evidence
for review, never permission to merge or modify live memory.

## Adapter contract

Adapters expose `load(records)`, `search(query, k, filters)`, `close()`, and
`reopen()`. Results contain `source_ids`, `text`, `scope`, `sensitivity`, and a
numeric score. This small contract maps directly to JSON-RPC/JSONL for adapters in
Python, TypeScript, Rust, Go, or another harness.
