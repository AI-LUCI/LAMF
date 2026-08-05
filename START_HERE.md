# START HERE — 5-Minute Orientation

LAMF (Local Agent Memory Fabric) is a build-ready architecture package for a
local-first, event-sourced agent memory system. This file orients you; it is not the
spec. Every normative statement lives in the contract files listed below.

## Step 1 — Verify the package (both audiences)

```text
python3 tools/validate_package.py
```

Requires Python >= 3.10 (stdlib + PyYAML; uses `jsonschema` if installed, otherwise a
built-in floor checker). Exit 0 means the package's reference integrity, policy
conformance, SQLite schema, canonical-hash golden vectors, and `MANIFEST.sha256` all
pass. That is the package's entire "validated" claim.

## Step 2 — Reading order

### Human operator / evaluator

1. `README.md` — what LAMF is, the three layers, the five setup choices.
2. `00_EXECUTIVE/OVERVIEW.md` — the vision, capabilities, honest claims.
3. `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md` — the invariant floor F1–F12 and the
   four fixed profiles + AI-Custom.
4. `02_SECURITY/FEATURE_MATRIX.md` — side-by-side profile comparison.
5. `07_PORTABILITY/NEW_OPENCLAW_COMPUTER.md` — what running it looks like.

### Coding-AI builder

1. `PROMPT_FOR_CODING_AI.md` — the entry prompt, milestones M1–M5.
2. `BUILD_WITH_AI.md` — master instruction, reading order, 18 non-negotiable rules.
3. `01_ARCHITECTURE/SYSTEM_OVERVIEW.md` — the normative architecture.
4. `02_SECURITY/*` — floor, threat model, secret patterns, matrix, profile YAMLs.
5. `03_CONTRACTS/*` — CLI reference, canonical hashing, wire protocol, MCP tools,
   state machines, council, all schemas. These are the frozen contracts.
6. `04_STORAGE/SCHEMA.sql` + `04_STORAGE/INDEXING_AND_SEARCH.md`.
7. `05_INTEGRATIONS/OPENCLAW_INTEGRATION.md`.
8. `08_BUILD_PLAN/IMPLEMENTATION_ROADMAP.md`, `08_BUILD_PLAN/ACCEPTANCE_TESTS.md`,
   `08_BUILD_PLAN/WORK_BREAKDOWN.yaml`.

Before writing code, record every contract ambiguity in OPEN_DECISIONS.md
(create it from `08_BUILD_PLAN/OPEN_DECISIONS.template.md`, in the same directory).
Do not resolve ambiguity by inventing APIs.

## Step 3 — Package map

```text
LAMF-reconditioned/
  README.md                       package overview + honest inventory
  START_HERE.md                   this file
  VERSION / CHANGELOG.md / LICENSE
  PROMPT_FOR_CODING_AI.md         single entry prompt (milestones M1-M5)
  BUILD_WITH_AI.md                master build instruction
  DECISIONS.md                    binding design decisions (v2.0.0)
  DEFECT_LEDGER.md                attack findings + dispositions
  EVALUATION_REPORT.md            attack/fix report
  MANIFEST.sha256                 authoritative file inventory
  00_EXECUTIVE/OVERVIEW.md        the vision, claims corrected
  01_ARCHITECTURE/SYSTEM_OVERVIEW.md
  02_SECURITY/                    floor F1-F12, threat model, profiles
  03_CONTRACTS/                   CLI, hashing, wire protocol, MCP tools, schemas
  04_STORAGE/                     SCHEMA.sql, indexing & search
  05_INTEGRATIONS/                OpenClaw integration + plugin scaffold
  06_SETUP/                       AI-Custom questionnaire + generator contract
  07_PORTABILITY/                 export/import, optional Git, new-computer guide
  08_BUILD_PLAN/                  roadmap, tests, breakdown, benchmarks, risks
  blueprints/                     3 architecture diagrams (.dot sources + .svg)
  tools/validate_package.py       the validation harness
```

The full normative tree is `DECISIONS.md` section A. No document may reference a path
outside it.

## Step 4 — First milestone pointer

The builder's first demonstrable milestone is **M1** (after Phase 1): `lamf init`,
sanitized capture, a durable record with its source event, FTS exact citation, and
crash-restart idempotent replay — fully offline. See `PROMPT_FOR_CODING_AI.md` for
M1–M5 and `08_BUILD_PLAN/IMPLEMENTATION_ROADMAP.md` for the twelve phases.
