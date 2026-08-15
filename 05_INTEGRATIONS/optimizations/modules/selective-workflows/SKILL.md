---
name: selective-workflows
description: Select the smallest task workflow and avoid unnecessary skills, questions, tools, or agents. Use when routing engineering work, choosing between direct execution and specialized procedures, or controlling orchestration overhead.
---

# Selective Workflows

Choose one path:

- Simple read or answer: inspect and respond directly.
- Ambiguous expensive decision: request only input that changes the result.
- Implementation or diagnosis: load the matching specialized workflow.
- Independent bounded subtasks: use parallel agents when overhead is justified.
- Cross-session knowledge: use LAMF.
- Transient ownership and progress: use a task ledger, not durable memory.

Avoid activating overlapping workflows for the same task. Read [references/provenance.md](references/provenance.md) only when evaluating or updating this optimization.
