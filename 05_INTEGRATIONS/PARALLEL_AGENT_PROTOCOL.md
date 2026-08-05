# Parallel Agent Write Protocol

LAMF supports any number of registered local MCP participants; it has no
configured agent-count limit. Every harness follows the same protocol whenever
two tasks could touch the same file or memory.

1. Call `memory_handoff` with `action: presence`, then check `inbox` and `list`.
2. Before mutation, `offer` a work item listing every target in `resources`.
   Use `file:<absolute-path>` or `memory:<record-id>`.
3. If the result is `queued`, do not edit. Immediately tell the user the
   returned `user_notice` and `queue_position`, then poll `list` or `inbox`.
4. Only an `offered` claim may be accepted. Acceptance returns a renewable
   30-minute lease and monotonic fencing token.
5. Read again after acceptance. Memory corrections include `expected_version`.
   A conflict requires rereading and merging both changes; blind overwrite is
   forbidden.
6. Renew long work. Complete or release with the exact fencing token; stale
   tokens are rejected.
7. Completion, release, or cancellation promotes the oldest non-conflicting
   queued claim. Resource comparison is case-insensitive and slash-normalized.

The FIFO queue prevents concurrent ownership. Optimistic versions prevent old
writers from erasing new memory. The signed Witness Spine audits transitions.
