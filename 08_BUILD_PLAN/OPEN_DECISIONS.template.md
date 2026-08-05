# OPEN_DECISIONS — template

Copy this file to OPEN_DECISIONS.md (same directory, `08_BUILD_PLAN/`) at the start
of Phase 0 and keep one entry per open decision. Entries are append-only; resolutions
edit the `chosen` and `status` fields, never delete history.

Rules:

- Record every contract ambiguity here BEFORE resolving it in code.
- Never resolve an ambiguity by inventing an API, path, or command absent from the
  package tree (`DECISIONS.md` section A).
- If a resolution would change a frozen contract, stop and request operator
  disposition instead of editing the contract.
- OpenClaw SDK unknowns are `TODO-BIND` items in
  `05_INTEGRATIONS/openclaw-plugin/index.ts`, not open decisions — but the
  binding choice (SDK version pinned) IS recorded here.

## Entry template

### D-<nnn>: <short title>

- **date**: YYYY-MM-DD
- **context**: what ambiguity or conflict was found, where (cite contract paths)
- **options**: the candidate resolutions considered, with consequences
- **chosen**: the selected resolution, or `unresolved`
- **owner**: who is accountable for the decision (operator / builder)
- **status**: `open | decided | deferred | escalated`

### D-001: (worked example) embedding model selection

- **date**: 2026-01-01
- **context**: Phase 10 requires a local embedding model; the package pins no model
  (`04_STORAGE/INDEXING_AND_SEARCH.md` defines only the cache key shape).
- **options**: (a) builder picks a small open model, (b) defer embeddings entirely,
  (c) operator supplies model.
- **chosen**: unresolved
- **owner**: operator
- **status**: open
