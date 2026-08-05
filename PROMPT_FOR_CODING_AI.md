# Prompt to Give Claude, Codex, Kimi, or Another Coding AI

Build Local Agent Memory Fabric (LAMF) from this package.

**Step 0 — before anything else**, run `python3 tools/validate_package.py` from the
package root. It must exit 0. If it fails, stop and report; do not build against a
broken package.

**Step 1** — read `BUILD_WITH_AI.md` first, then the files in its required reading
order. The contracts in `03_CONTRACTS/` are frozen: implement them, do not redesign
them.

**Step 2** — before writing code, copy `08_BUILD_PLAN/OPEN_DECISIONS.template.md` to
OPEN_DECISIONS.md (same directory) and record every contract ambiguity you find, one
entry per decision. Never resolve an ambiguity by inventing an API, file path, or
command not present in this package. Where the OpenClaw SDK surface is unknown, bind
to the installed public SDK at build time and keep the `TODO-BIND:` markers in
`05_INTEGRATIONS/openclaw-plugin/index.ts` until bound. (Most surfaces are bound
per DECISIONS §W-03; only research-flagged unknowns remain.)

**Step 3** — produce a phase-by-phase implementation plan mapped to
`08_BUILD_PLAN/WORK_BREAKDOWN.yaml`. Implement **Phase 0 and Phase 1 first**. Do not
implement embeddings, UI, or Git until deterministic storage, security, and FTS tests
pass.

## Milestones (order is normative; v1's impossible ordering is corrected)

- **M1** (after Phase 1): `lamf init --profile controlled`; a sanitized event captured
  through REST or MCP; a durable memory record with its source event; FTS search
  returning an exact citation; crash restart with idempotent replay. Fully offline.
- **M2** (after Phase 2): a policy-denied sensitive read with an itemized receipt.
- **M3** (after Phase 4): retrieval correctness and the benchmark targets of
  `08_BUILD_PLAN/BENCHMARKS.md` met **without embeddings**.
- **M4** (after Phase 5): a generic MCP client round-trip — capture, search, context,
  remember, handoff — against `03_CONTRACTS/mcp-tools.yaml`.
- **M5** (after Phase 8): `lamf export` on one machine; clean-machine
  `lamf import --staged` -> rebind secrets -> `lamf verify --deep` -> `lamf activate`;
  same current memory.

Then add the OpenClaw adapter using the current documented public plugin interfaces
(`05_INTEGRATIONS/OPENCLAW_INTEGRATION.md`). Do not couple the core to OpenClaw
internals.

Definition of done is in `BUILD_WITH_AI.md`; acceptance tests are
`08_BUILD_PLAN/ACCEPTANCE_TESTS.md`. A milestone is not done because it compiles.
