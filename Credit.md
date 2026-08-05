# Credit

This is LAMF's living attribution ledger. It records external work that
influenced LAMF's design, implementation, evaluation, documentation, or
boundaries so future public releases can give appropriate credit.

This ledger is not a substitute for upstream license notices. Before a public
release, re-check the referenced repository, license, authorship, and whether
any source code or text was copied. The entries below describe the state of the
LAMF package as inspected on 2026-08-02.

## Entry schema

Every entry must contain:

- **Credit ID:** stable identifier used by module provenance files.
- **Upstream:** project name and repository URL.
- **Creator or maintainer:** attribution visible in the repository or license.
- **License observed:** license found in the inspected snapshot; note ambiguity.
- **Snapshot inspected:** commit or version used during evaluation.
- **What influenced LAMF:** concrete ideas, workflows, or boundary decisions.
- **LAMF surfaces:** modules, files, or architectural decisions affected.
- **Incorporation:** conceptual synthesis, adapted workflow, vendored code, or
  evaluated-only.
- **Copied source:** state whether code or prose was copied and identify notices
  required when applicable.
- **Notes:** evidence limits, distinctions, or follow-up checks.

## LAMF Optimizations

### OPT-PONYTAIL — Ponytail

- **Upstream:** [DietrichGebert/ponytail](https://github.com/dietrichgebert/ponytail)
- **Creator or maintainer:** Dietrich Gebert.
- **License observed:** MIT; root license copyright Dietrich Gebert, 2026.
- **Snapshot inspected:** `16f2980` on 2026-08-02.
- **What influenced LAMF:** the ordered minimal-solution ladder; reuse before
  adding code; prefer standard-library, native, and already-installed features;
  preserve safety while reducing code; review diffs for overengineering; measure
  tokens, cost, time, changed lines, and safety rather than relying on slogans.
- **LAMF surfaces:** `minimal-solution`; optimization evaluation criteria.
- **Incorporation:** conceptual synthesis and adapted workflow.
- **Copied source:** no upstream runtime code or prose is vendored.
- **Notes:** Ponytail's published measurements are narrow and are not claimed as
  LAMF results. LAMF requires its own cross-harness evaluation.

### OPT-MATT-SKILLS — Matt Pocock Skills

- **Upstream:** [mattpocock/skills](https://github.com/mattpocock/skills)
- **Creator or maintainer:** Matt Pocock.
- **License observed:** MIT; root license copyright Matt Pocock, 2026.
- **Snapshot inspected:** `2ab9580` on 2026-08-02.
- **What influenced LAMF:** small composable skills; progressive disclosure;
  selective loading of detailed workflows; verification-oriented diagnosis,
  implementation, review, TDD, specification, and handoff patterns.
- **LAMF surfaces:** `selective-workflows`; `verified-execution`; modular skill
  packaging and provenance references.
- **Incorporation:** conceptual synthesis and adapted workflow selection.
- **Copied source:** no upstream skill files or prose are vendored.
- **Notes:** LAMF intentionally adopted a small subset of concepts rather than
  installing the whole collection.

### OPT-KARPATHY-GUIDELINES — Andrej Karpathy-derived guidelines

- **Upstream:** [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills)
- **Creator or maintainer:** packaged by Multica AI; derived from public
  observations by Andrej Karpathy. Credit is due to both.
- **License observed:** the included skill declares MIT, but the inspected
  repository snapshot had no root license file; re-check before publication.
- **Snapshot inspected:** `2c60614` on 2026-08-02.
- **What influenced LAMF:** surface assumptions and uncertainty; avoid
  overcomplication; make surgical changes; define observable success criteria;
  avoid unrelated edits.
- **LAMF surfaces:** `surgical-changes`; `verified-execution`.
- **Incorporation:** original conceptual synthesis, deliberately using new
  wording because repository-level licensing was ambiguous.
- **Copied source:** no upstream file or prose is vendored.
- **Notes:** the underlying observations belong to Andrej Karpathy; the skill
  organization and packaging were produced by Multica AI.

### OPT-MULTICA — Multica

- **Upstream:** [multica-ai/multica](https://github.com/multica-ai/multica)
- **Creator or maintainer:** Multica AI contributors.
- **License observed:** current root file is the custom **Multica License**:
  Apache License 2.0 text plus additional source-available restrictions,
  including limits on hosted, embedded, and commercially distributed uses
  without a commercial license. It must not be described as plain Apache-2.0.
- **Snapshot inspected:** `37f3bb7` on 2026-08-02.
- **What influenced LAMF:** vendor-neutral agent support; stable task lifecycle
  and routing concepts; keeping a control plane separate from agent providers;
  reusable skills that compound without binding to one harness.
- **LAMF surfaces:** `selective-workflows`; harness-neutral optimization module
  packaging and optional task-ledger boundary.
- **Incorporation:** conceptual synthesis.
- **Copied source:** no upstream code or prose is vendored.
- **Notes:** Multica's managed-agent platform is not a LAMF dependency.

### OPT-GASTOWN — Gas Town

- **Upstream:** [gastownhall/gastown](https://github.com/gastownhall/gastown)
- **Creator or maintainer:** Steve Yegge and Gas Town contributors.
- **License observed:** MIT; root license copyright Steve Yegge, 2025.
- **Snapshot inspected:** `649b832` on 2026-08-02.
- **What influenced LAMF:** persistent task ledgers, handoffs, mailboxes, and
  work ownership; the architectural distinction between transient coordination
  state and durable personal/project memory; gating heavy multi-agent machinery
  to workloads where its overhead is justified.
- **LAMF surfaces:** `selective-workflows`; decision that LAMF memory is not a
  general-purpose task ledger.
- **Incorporation:** conceptual synthesis and boundary definition.
- **Copied source:** no upstream code or prose is vendored.
- **Notes:** Gas Town is an optional orchestration reference, not bundled runtime.

### OPT-RUFLO — Ruflo

- **Upstream:** [ruvnet/ruflo](https://github.com/ruvnet/ruflo)
- **Creator or maintainer:** ruvnet / rUv and contributors.
- **License observed:** MIT; root license copyright ruvnet, 2024–2026.
- **Snapshot inspected:** `913f9ea` on 2026-08-02.
- **What influenced LAMF:** evaluation of swarm routing, topology selection,
  hooks, learning loops, and large tool catalogs; the resulting decision to keep
  orchestration optional and avoid enabling a broad agent/tool surface by default.
- **LAMF surfaces:** `selective-workflows`; independent module switches and
  conservative orchestration boundary.
- **Incorporation:** evaluated-only architectural influence.
- **Copied source:** no upstream code or prose is vendored.
- **Notes:** Ruflo's runtime, memory, daemon, and agent catalog are not bundled.

### OPT-MEM0 — Mem0

- **Upstream:** [mem0ai/mem0](https://github.com/mem0ai/mem0)
- **Creator or maintainer:** Mem0 maintainers and contributors.
- **License observed:** Apache License 2.0 in the root license.
- **Snapshot inspected:** `50bdaae` on 2026-08-02.
- **What influenced LAMF:** memory-evaluation awareness; bounded retrieval;
  semantic, keyword, entity, and temporal ranking concepts; most importantly,
  the decision not to introduce a second writable memory authority beside LAMF.
- **LAMF surfaces:** memory evaluation backlog; the boundary keeping LAMF the
  sole durable-memory writer and optimization modules memory-independent.
- **Incorporation:** evaluated-only concepts and architectural boundary.
- **Copied source:** no upstream SDK, storage implementation, or prose is vendored.
- **Notes:** managed-platform benchmark results include proprietary optimization
  and are not claimed as LAMF results. Any future retrieval adaptation requires
  independent evaluation and a new ledger update.

### OPT-OH-MY-PI - oh-my-pi Hashline

- **Upstream:** [can1357/oh-my-pi](https://github.com/can1357/oh-my-pi),
  specifically the `@oh-my-pi/hashline` component.
- **Creator or maintainer:** Can Boluk; the root license also credits Mario
  Zechner.
- **License observed:** MIT in the root license and Hashline package metadata.
- **Snapshot inspected:** `06343fef4200c4e32d18f08df5a6a8bd84dcc710`
  on 2026-08-02.
- **What influenced LAMF:** content-hash mutation preconditions, stale-anchor
  rejection before mutation, narrow recovery from current state, and preflight
  of multi-target edits before any part lands.
- **LAMF surfaces:** `stale-context-guards`; the daily optimization discovery
  process and its first report.
- **Incorporation:** conceptual synthesis with a generic optimistic-concurrency
  fallback for harnesses without hash-anchored editing.
- **Copied source:** no Hashline source, prompt text, grammar, or patch format is
  vendored. LAMF uses original provider-neutral wording.
- **Notes:** upstream token and edit-success measurements are not claimed as
  LAMF results. LAMF's module requires independent cross-harness validation.

## Maintenance record

| Date | Change | Updated by |
|---|---|---|
| 2026-08-02 | Created the living ledger and recorded all repositories evaluated for LAMF Optimizations. | Codex, at Marcel's request |
| 2026-08-02 | Added `OPT-OH-MY-PI` for the stale-context optimization found by the first daily discovery scan. | Codex, at Marcel's request |
| 2026-08-02 | Re-checked upstream licenses before the first public distribution. Confirmed Ponytail, Matt Pocock Skills, Gas Town, and Ruflo as MIT; Mem0 as Apache-2.0; the Karpathy-derived repository still has no root license; corrected Multica from Apache-2.0 to its current restricted Multica License. No upstream code or prose is vendored. | Codex |
| 2026-08-02 | Re-confirmed oh-my-pi's root MIT license before publishing the optimization layer as a separate optional download. | Codex |
| 2026-08-02 | Re-checked current upstream repository license metadata for the public-launch gate: Ponytail, Matt Pocock Skills, Gas Town, Ruflo, and oh-my-pi report MIT; Mem0 reports Apache-2.0; the Karpathy-derived repository still reports no root license; Multica remains non-standard/NOASSERTION and must retain its restricted-license warning. No external material was newly incorporated. | Codex |
