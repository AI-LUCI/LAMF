# Optimization discovery process

This process finds evidence that could reduce token use or improve agent
accuracy without compromising LAMF's local authority, portability, or
harness-neutral design. Discovery is advisory until a candidate passes every
gate below. Trend rank alone is never sufficient.

## Daily sources

- GitHub Trending for Python and TypeScript, plus relevant repository history.
- Hugging Face trending models, datasets, and Spaces.
- OSSInsight AI repository and category rankings.
- daily.dev AI, agent, MCP, local-runner, and developer-tool coverage.
- Maintained Awesome AI Agents, Awesome AI Apps/LLM Apps, and Awesome AI Tools
  lists. Curated lists are discovery indexes; upstream repositories remain the
  evidence authority.

## Candidate gates

For each candidate, record:

1. **Signal:** dated source, upstream URL, current revision/version, maintainer,
   observed license, and why the change is newly relevant.
2. **Delta:** the behavior LAMF does not already provide. Reject duplicates or
   update the existing module when that is the smaller honest change.
3. **Benefit:** the expected token or accuracy mechanism and a falsifiable check.
4. **Safety:** prompt-injection, supply-chain, privacy, destructive-action,
   licensing, and second-memory-authority risks.
5. **Independence:** one behavior, its own switch, no dependency on another
   optimization, and fail-open behavior that preserves original LAMF.
6. **Agnostic portability:** instruction-level baseline through the universal
   MCP launcher; no mandatory provider, model, cloud, editor, shell, language,
   or harness feature. Optional native accelerators must have a generic fallback.
7. **Compatibility:** describe interactions with every current optimization and
   run the complete Codex, Claude, Kimi, Grok, OpenClaw, Hermes, and generic MCP
   adapter matrix.
8. **Verification and credit:** update tests, `CHANGELOG.md`, `Credit.md`, module
   provenance, package manifest, and the portable archive. Never claim an
   upstream benchmark as a LAMF result.

## Decision outcomes

- **Adopt:** create or update an independently switchable module and validate it.
- **Evaluate only:** record a useful boundary or candidate needing benchmarks.
- **Reject for now:** record why it duplicates LAMF, harms portability, lacks
  sufficient evidence, has unsuitable licensing, or creates unacceptable risk.

Daily reports live under the `reports/` directory; see the
[first discovery report](reports/2026-08-02.md). Repeated runs update the same
day's report instead of creating duplicates.
