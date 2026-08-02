---
name: surgical-changes
description: Keep code changes tightly scoped to the requested outcome and avoid collateral edits. Use when modifying an existing repository, fixing bugs, reviewing diffs, or working in a dirty worktree.
---

# Surgical Changes

1. Inspect current state and preserve unrelated user changes.
2. Trace symptoms to the shared root cause and check affected callers.
3. Change only lines required for the requested result.
4. Match surrounding conventions; avoid opportunistic cleanup.
5. Remove only imports or code made obsolete by this change.
6. Report unrelated defects separately.

Read [references/provenance.md](references/provenance.md) only when evaluating or updating this optimization.
