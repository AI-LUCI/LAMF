# LAMF vs. akitaonrails/ai-memory: reproducible comparison

Audit date: 2026-08-01  
ai-memory source audited: `93e743fac4c0ce5a2ec4f39a5add76fc00c8a55e`  
ai-memory release inspected: `v1.20.2`

## Comparison rule

“Better” is never a single unqualified label. An axis is a LAMF win only when:

1. both products are tested for the same behavior on the same machine and fixture; or
2. the capability is structurally present in LAMF and structurally absent in the
   pinned ai-memory source, with exact evidence recorded.

Documentation claims and planned acceptance tests do not count as runtime wins.

## Current result

LAMF does **not** currently have evidence for an overall win over ai-memory. It has
strong, executable advantages in cryptographic history, fail-closed capture, governed
Obsidian projection, and explicit taint/policy controls. ai-memory is ahead in
retrieval breadth, lifecycle automation, first-party harness coverage, project
routing, web UX, optional embeddings, graph retrieval, and maturity.

The older claim that ai-memory is “plain Markdown plus grep with no secret defense”
is false for v1.20.2 and must not be repeated.

## Evidence matrix

| Axis | LAMF evidence | ai-memory v1.20.2 evidence | Result |
|---|---|---|---|
| Cryptographic event integrity | Ed25519-signed, SHA-256 hash-chained spine; deep and bounded-tail verification in the 13-stage smoke suite | Git-versioned Markdown plus database audit rows; no signed per-event hash chain found in pinned source | LAMF win |
| Memory-as-untrusted-data boundary | Taint and sensitivity returned on every result; capsules carry an explicit untrusted-data notice | `UNTRUSTED_MEMORY_NOTICE` and authority-aware recall are implemented | Parity; different policy depth |
| Secret handling | Fail-closed before spool; secret-looking capture is dropped; 0/10,000 false positives in executed fixture | Typed sanitizer boundary and server-side redaction; project SECURITY.md explicitly describes it as best effort | LAMF stronger mode; comparative recall fixture still needed |
| Revision history | Immutable correction event plus v1→v2 supersession chain | Page versioning, supersession metadata, and Git history | Parity at feature level; integrity model differs |
| Full-text retrieval | FTS5, typed/scope filters, token-bounded context capsule; 1.846 ms p95 at 100k synthetic records | FTS5 plus authority adjustment | Both ship; no fair cross-product latency result yet |
| Semantic/hybrid retrieval | No embedding or graph-neighbor engine | Entity, graph-neighbor, optional vector RRF | ai-memory win |
| Harness adapters | Codex, Claude, Kimi, Grok, OpenClaw, Hermes, generic MCP | Broader first-party matrix; Hermes is community-maintained | ai-memory win overall; LAMF wins first-party Hermes |
| Lifecycle capture | Shared MCP and CLI memory operations | Extensive per-harness prompt/tool/session hooks and managed workstreams | ai-memory win |
| Human visual layer | Native Obsidian projection, 11 pinned areas, governed/self-healing notes, operator-owned areas | Built-in read-only web UI and Markdown wiki usable in Obsidian | Different strengths; LAMF wins governed Obsidian behavior |
| Portability | Encrypted passphrase export/import with integrity checks | Backup/restore, Git/versioned Markdown, importer ecosystem | Different strengths |
| Installation/runtime | Python runtime and one shared installation | Static Rust binaries, Docker, packages | ai-memory win |

## Gates required before any overall “beats ai-memory” claim

- Run the same planted retrieval fixture against both products and report recall@5,
  MRR, p50/p95 latency, index/build time, and disk usage.
- Add a shared secret corpus and report secret recall, false positives, and behavior
  (drop, quarantine, or redact) separately.
- Add crash/recovery and deliberate-corruption scenarios for both products.
- Measure session-to-session handoff completeness across supported harnesses.
- Define a published weighting before results are known; never invent a score after
  seeing which product wins each axis.
- Preserve all raw result JSON and exact versions/hashes.

Until those gates close, the permitted claim is: **LAMF provides stronger
cryptographic governance and an Obsidian-first authority projection; it is not yet
proven better than ai-memory overall.**
