---
name: minimal-solution
description: Reduce unnecessary code, dependencies, files, and work while preserving correctness and safety. Use when implementing, fixing, refactoring, or reviewing code where an agent might overbuild or duplicate existing capabilities.
---

# Minimal Solution

1. Understand the request and trace the affected flow.
2. Stop if the requested work is unnecessary.
3. Reuse existing code, standard-library or native features, then installed dependencies.
4. Add the minimum new implementation only after those options fail.
5. Preserve security, trust-boundary validation, accessibility, data-loss prevention, and explicit requirements.
6. Leave the smallest relevant verification for non-trivial behavior.

Read [references/provenance.md](references/provenance.md) only when evaluating or updating this optimization.
