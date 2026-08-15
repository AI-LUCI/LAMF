---
name: stale-context-guards
description: Prevent incorrect or wasteful mutations caused by files, records, configuration, or remote state changing after inspection. Use when editing mutable state, especially during long, concurrent, multi-agent, or externally synchronized work.
---

# Stale Context Guards

1. Identify whether the mutation target could have changed since the last read.
2. Prefer a native optimistic-concurrency feature: content hash, version, ETag,
   test-and-set, anchored patch, or equivalent precondition.
3. If none exists, re-read only the smallest region needed immediately before
   the mutation. Do not repeatedly reload stable state.
4. Treat a failed precondition as new evidence. Refresh and reconcile current
   user or concurrent changes; never force the stale mutation.
5. Recompute the change from current state and retry once. Diagnose repeated
   divergence rather than entering a blind retry loop.
6. For atomic multi-target tools, preflight every target when the harness
   supports it. Otherwise keep the change narrow and verify the resulting state.

This module strengthens `surgical-changes` by protecting unrelated concurrent
work and strengthens `verified-execution` by making current state part of the
evidence. It does not require either module and remains useful when both are off.

Read [references/provenance.md](references/provenance.md) only when evaluating or updating this optimization.
