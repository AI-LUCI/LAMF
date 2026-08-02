# Architecture

LAMF is one local authority exposed to compatible agents through MCP or harness adapters. Writes are sanitized and policy-checked before revisioned records are projected into the local store and append-only integrity spine. Retrieval is scope-filtered and returns provenance metadata. Optional views and integrations are downstream of the authority.

```mermaid
flowchart LR
  A["Codex / Claude / Kimi / other MCP client"] --> M["LAMF MCP and harness adapters"]
  M --> P["Policy, scope, approvals, secret exclusion"]
  P --> S["Local memory store"]
  P --> W["Append-only integrity spine"]
  S --> R["Scoped retrieval with provenance"]
  R --> A
  S --> V["Optional rebuildable views"]
  O["Separately installed optimization pack"] -. "agent behavior only" .-> A
```

The optimization pack is not in the write, storage, or retrieval authority path. Disabling or removing it does not delete or migrate memory.
