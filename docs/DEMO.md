# Reproducible cross-agent demo

Use a disposable data directory and a harmless fact. Never use real personal data.

1. Install core LAMF with two compatible harnesses and a temporary data directory.
2. In agent A, call `memory_remember` with title `Demo editor preference`, body `The demo project uses 100-column formatting`, and scope `project:lamf-demo`.
3. Close that task. In a new task or agent B, call `memory_search` for `demo project formatting` in `project:lamf-demo`, then `memory_get` for the returned record. Show the scope, record ID, version, and source event.
4. Disconnect networking and repeat recall to demonstrate that authority remains in the local data directory. This demonstrates local operation, not protection against a compromised host.
5. Install the separate LAMF Optimizations checkout. Run `lamf optimizations status`, disable it with `lamf optimizations off`, and recall again. The memory result should remain available because optimizations do not own storage.
6. Delete the disposable demo data only after confirming its exact path.

Record terminal commands, versions, OS, and expected/actual results. Do not claim compatibility for a harness not tested in that recording.
