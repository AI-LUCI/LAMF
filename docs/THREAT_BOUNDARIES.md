# Threat boundaries

LAMF reduces accidental cross-agent fragmentation and applies local policy controls; it does not make an untrusted or compromised host safe.

```mermaid
flowchart TB
  subgraph Public["Public, safe to publish"]
    C["Source checkout"]
    T["Synthetic tests and docs"]
  end
  subgraph Private["Private operator boundary — never commit"]
    D["Memory database and payload store"]
    K["Instance key and operator token"]
    L["Logs, spool, vaults, exports, configuration"]
  end
  C -->|"installs runtime"| Private
  H["Local agent processes"] -->|"localhost / stdio"| Private
  N["Network or other users"] -. "not trusted by default" .-> Private
```

Assumptions: the operator controls the machine and filesystem permissions; localhost is not exposed; dependencies and downloaded releases are verified; and sensitive backups are protected. Out of scope: a compromised OS or administrator, malicious agent with equivalent local access, physical extraction from an unlocked machine, and safety of third-party harnesses. Before reporting a bug, replace all live state with synthetic data.
