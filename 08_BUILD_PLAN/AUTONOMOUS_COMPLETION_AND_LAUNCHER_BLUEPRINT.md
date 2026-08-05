# LAMF Autonomous Completion and Multi-Agent Launcher Blueprint

Status: implementation blueprint  
Scope: LAMF core, governed Obsidian projection, retrieval, portability, harness adapters, and cross-platform launcher  
Platforms: Windows, macOS, Linux  

## 1. Outcome

Complete the currently partial LAMF capabilities without weakening the existing
security floor, then provide one launcher through which an operator can inspect,
connect, verify, disconnect, and repair every supported agent harness.

The launcher is a client of the existing LAMF authority. It does not create a second
database, policy, event spine, identity key, or memory store. Every harness connects
to the same `lamf-memory` MCP server and `LAMF_DATA_DIR`.

The target operator experience is:

```text
LAMF Agent Connections

Connected (3)
  OpenAI Codex          (o) Connected  ( ) Disconnected   Healthy
  Claude Code           (o) Connected  ( ) Disconnected   Restart required
  Kimi Code CLI         (o) Connected  ( ) Disconnected   Healthy

Not connected (4)
  OpenClaw              ( ) Connected  (o) Disconnected   Available
  Grok Build CLI        ( ) Connected  (o) Disconnected   Not installed
  Hermes Agent          ( ) Connected  (o) Disconnected   Available
  Generic MCP client    ( ) Connected  (o) Disconnected   Manual target needed
```

Each harness has a two-choice radio group, not one global radio group. Selecting
Connected runs a staged connection transaction. Selecting Disconnected removes only
LAMF-owned configuration. The row returns to its last confirmed state if the action
fails or is cancelled.

## 2. Non-negotiable invariants

1. LAMF remains harness-agnostic and local-first.
2. The signed Witness Spine and record store remain the sole authority.
3. Obsidian remains an optional, regenerable human projection.
4. Harnesses never read the database, keys, event segments, or governed Markdown.
5. Policy and scope filtering occur before ranking or disclosure.
6. Vector, graph, summary, and model-generated results are untrusted candidates, not
   authority.
7. Restricted content never appears in the vault. Sensitive content follows the
   active profile.
8. Connection changes are explicit operator actions. Autonomous work may implement,
   test, and prepare adapters, but must not connect accounts, accept approvals, expose
   tokens, push repositories, or modify an unselected harness.
9. Every changed configuration file is backed up and updated atomically.
10. Disconnect removes only LAMF-owned blocks, registrations, hooks, and plugin files.
11. A failed adapter operation must leave the previous working configuration intact.
12. Windows, macOS, and Linux must pass the same behavioral contract.

## 3. Architecture

```text
Launcher UI (local browser)
        |
        v
Launcher API / orchestration service
        |
        +--> Harness registry and capability probes
        +--> Transaction planner / backup / rollback
        +--> Adapter drivers
        |      +-- Codex
        |      +-- Claude
        |      +-- Kimi
        |      +-- Grok
        |      +-- OpenClaw
        |      +-- Hermes
        |      +-- Generic MCP
        |
        +--> LAMF health probe
                 |
                 v
         universal MCP launcher
                 |
                 v
       one LAMF authority and data directory
```

Use the existing Python runtime and built-in loopback web application. Do not add
Electron, Tauri, Node, or a native GUI dependency merely to obtain cross-platform
support. `lamf launcher` starts or reuses the loopback service and opens the system
browser. A headless equivalent remains available through `lamf harness ...`.

The UI must bind to loopback only, require the operator token, use CSRF protection,
and never place tokens or secrets in URLs, logs, browser storage, or rendered HTML.

## 4. Canonical harness state model

Do not infer connection state merely from whether a config file exists. Each adapter
returns a normalized observation:

```json
{
  "id": "openclaw",
  "label": "OpenClaw",
  "installation": "installed|not_installed|unknown",
  "registration": "connected|disconnected|partial|conflicted|unknown",
  "health": "healthy|degraded|unreachable|restart_required|not_tested",
  "capability_level": 1,
  "config_targets": [],
  "last_verified_at": null,
  "diagnostics": [],
  "available_actions": ["connect", "disconnect", "repair", "verify"]
}
```

UI grouping uses `registration`, not installation:

- **Connected:** `connected`, including `restart_required` health.
- **Not connected:** `disconnected` or `not_installed`.
- **Needs attention:** `partial`, `conflicted`, or `unknown`. This third group appears
  only when needed so ambiguous state is never misrepresented as safe.

## 5. Adapter driver contract

Replace harness-specific branching with a driver interface while preserving the
existing `Harness` registry:

```python
class HarnessDriver(Protocol):
    def detect(self, context) -> HarnessObservation: ...
    def plan_connect(self, context) -> ChangePlan: ...
    def connect(self, context, approved_plan) -> ChangeReceipt: ...
    def verify(self, context) -> VerificationReceipt: ...
    def plan_disconnect(self, context) -> ChangePlan: ...
    def disconnect(self, context, approved_plan) -> ChangeReceipt: ...
    def repair(self, context, approved_plan) -> ChangeReceipt: ...
```

Every driver must:

- resolve paths with platform APIs rather than hard-coded separators;
- detect the executable without executing untrusted project scripts;
- preserve unrelated configuration, comments where feasible, and file permissions;
- use owned blocks or exact structured keys;
- hash the inspected input and reject stale mutations;
- create a timestamped backup before mutation;
- write to a sibling temporary file, fsync where supported, then atomically replace;
- probe MCP `initialize`, `tools/list`, and `memory_status` after connection;
- roll back automatically if verification fails;
- report when the host must restart;
- be idempotent for repeated connect, disconnect, verify, and repair calls.

The Generic MCP driver only emits or copies a configuration snippet unless the
operator selects an explicit config target. It never guesses a writable target.

## 6. Connect and disconnect transactions

### Connect

1. Detect the harness installation and all candidate configuration scopes.
2. If multiple targets are materially different, ask the operator to select one.
3. Show the exact owned keys/files and whether a restart will be required.
4. Snapshot hashes and create the backup.
5. Apply the smallest registration change.
6. Start a disposable MCP handshake using the same resolved command and environment.
7. Require `initialize`, `tools/list`, and `memory_status` to succeed.
8. Confirm that the server resolves the authoritative `LAMF_DATA_DIR`.
9. Commit the transaction receipt and update the row.
10. On failure, restore the backup and show a bounded diagnostic.

### Disconnect

1. Detect every LAMF-owned registration for that harness.
2. Display exactly what will be removed and what will remain.
3. Back up the target.
4. Remove only owned keys/blocks/plugin registration.
5. Verify the unrelated configuration is byte-equivalent or semantically equivalent.
6. Leave the LAMF authority, data, vault, keys, CLI, and other harnesses untouched.
7. Record the receipt and update the row.

## 7. Harness delivery order

Implement adapters in increasing native-integration risk:

1. Generic MCP fixture driver.
2. Codex.
3. Claude Code/Desktop.
4. Kimi Code CLI.
5. Grok Build CLI.
6. Hermes Agent.
7. OpenClaw managed MCP registration.
8. OpenClaw native memory plugin hooks.

The launcher foundation is implemented before the OpenClaw adapter. Reaching the
OpenClaw milestone means adding OpenClaw to the same tested launcher—not creating a
special OpenClaw-only launcher.

## 8. Completion workstreams

### WS-A: Retrieval truth and exact lookup

Deliver:

- exact record ID, event ID, and content-hash indexes;
- scope and policy filtering before candidate generation;
- authority score derived from provenance, record state, taint, confidence, recency,
  and explicit operator decisions;
- deterministic explanation of why a result ranked where it did;
- superseded, contradicted, expired, and tombstoned handling consistent across MCP,
  HTTP, CLI, and projection.

Gate: planted exact-lookup fixtures return the correct object with provenance; no
out-of-scope candidate reaches ranking.

### WS-B: Graph retrieval

Deliver:

- normalized entity and typed-edge tables rebuilt from authoritative records;
- bounded one-hop expansion by default and policy-controlled multi-hop expansion;
- cycle, fan-out, and token-budget limits;
- edge provenance and state filtering;
- graph results merged as candidates without becoming authority.

Gate: deterministic graph fixtures prove typed traversal, scope isolation,
supersession invalidation, bounded fan-out, and reproducible rebuilding.

### WS-C: Optional local vectors and hybrid ranking

Deliver:

- a disabled-by-default local embedding provider interface;
- rebuildable vector cache containing no authoritative-only state;
- model/version/dimension metadata and invalidation;
- policy filtering before embedding lookup;
- reciprocal-rank fusion across exact, FTS, graph, and vector candidates;
- operation with vectors entirely absent.

Gate: the full suite passes with vectors off; hybrid evaluation improves a pinned
semantic-recall corpus without reducing exact/scope/security results.

### WS-D: Citations, receipts, and disclosure audit

Deliver:

- stable citations containing record ID, version, source-event IDs, state, and content
  hash where permitted;
- itemized sensitive disclosure receipts;
- aggregate ordinary-read receipts only where policy allows;
- context capsules that report included citations, omissions, ranking channels, and
  token accounting;
- operator-readable disclosure history without exposing protected content.

Gate: every returned context item can be traced to authoritative records and events;
receipt behavior passes all five profile matrices.

### WS-E: Full security-profile projection

Deliver a compiled projection policy for Locked, Controlled, Trusted Local, Open
Local, and AI-Custom that controls:

- whether a record is projected;
- metadata-only versus redacted versus full content;
- visible folders and dashboards;
- agent-memory visibility;
- permitted controlled edit actions;
- export and Git eligibility;
- approval and reauthentication prompts.

Restricted contents and registered secrets remain outside all projections.

Gate: a golden vault fixture for each profile proves exact paths and redactions, and
switching profiles removes stale files before exposing the new view.

### WS-F: Governed Obsidian editing

Keep the current restore-and-review behavior and add:

- live watcher health and last-projection status;
- a structured proposed-correction file linked to the authoritative record;
- approve/reject through controlled LAMF actions;
- conflict detection against the projected version;
- projection latency metrics and background rebuild isolation.

Gate: tamper, deletion, concurrent correction, watcher restart, and projection failure
never silently change authority or interrupt search.

### WS-G: Lifecycle capture and promotion

Deliver a provider-neutral capture envelope for prompt/tool/session hooks. Candidate
events are sanitized and classified before promotion. Promotion rules must distinguish
explicit user facts, confirmed decisions, stable project facts, transient logs,
inferences, and secrets. Native hooks degrade to MCP-only operation.

Gate: identical fixtures through each harness yield equivalent sanitized candidates;
no transcript is promoted wholesale and no secret reaches spool or storage.

### WS-H: Backup, export, and clean-machine recovery

Deliver:

- scheduled local encrypted backups with retention and health reporting;
- operator-configured destinations only;
- atomic bundle creation and restore staging;
- event-chain verification and fresh index rebuild;
- regeneration of the optional Obsidian projection;
- adapter reconnection through the launcher after import;
- a cross-platform clean-machine recovery rehearsal.

Gate: restore onto clean Windows, macOS, and Linux runners yields identical
authoritative record/citation results while generating new machine-local credentials.

### WS-I: Launcher and adapter management

Deliver the UI, normalized state model, driver contract, transactional mutations,
receipts, repair flow, and headless CLI parity described above.

Gate: every supported harness passes detect/connect/verify/reconnect/disconnect,
rollback, concurrent-edit, malformed-config, missing-executable, spaces-in-path, and
non-ASCII-path tests on all three operating-system families.

### WS-J: OpenClaw completion

Deliver:

- managed MCP registry connect/disconnect;
- native `kind: memory` plugin bound only to public OpenClaw SDK surfaces;
- automatic bounded orientation where supported;
- sanitized nonblocking final-turn capture;
- single- and multi-agent identity mapping;
- Doctor integration;
- graceful fallback from native hooks to MCP Level 1;
- launcher status that distinguishes MCP connected from native hooks active.

Gate: offline single-agent and multi-agent scenarios pass; uninstall leaves OpenClaw
unrelated settings and the shared LAMF authority intact.

## 9. Autonomous execution controller

An autonomous implementation agent follows a versioned backlog where every task has:

- requirement IDs;
- allowed file/resource scope;
- dependencies;
- observable acceptance criteria;
- required unit, integration, security, and platform tests;
- rollback instructions;
- evidence artifacts;
- an explicit list of actions requiring human approval.

The controller loop is:

```text
orient -> inspect current state -> select smallest unblocked task
       -> implement on an isolated branch/worktree
       -> run proportional tests
       -> run security and compatibility gates
       -> produce an evidence manifest
       -> mark complete only when every criterion passes
       -> continue to the next dependency-ready task
```

Autonomy stops and requests operator input only for:

- account authentication or reauthentication;
- selecting among materially different configuration targets;
- weakening a security profile or changing the invariant floor;
- approving a sensitive promotion or disclosure;
- enabling remote Git/network sharing;
- installing system-wide dependencies requiring elevation;
- publishing, pushing, merging, releasing, or deleting user data;
- an acceptance criterion that cannot be verified safely.

A failed test is not a reason to stop. The agent diagnoses, fixes, and reruns within
scope. Three repetitions of the same external blocker produce a blocked evidence
report rather than a false completion.

## 10. Phased implementation plan

### Phase 0 — Baseline and contracts

- Convert this blueprint into requirement IDs and machine-readable acceptance cases.
- Freeze current behavior with regression tests.
- Add capability flags so documentation never advertises unimplemented graph/vector
  behavior as active.

Exit: baseline suite passes on Windows, macOS, and Linux CI.

### Phase 1 — Launcher foundation

- Normalize harness detection and state.
- Add driver protocol and Generic MCP fixture.
- Add transactional backup, stale-hash protection, rollback, and receipts.
- Add launcher API and Connected/Not connected/Needs attention UI.
- Add headless CLI parity.

Exit: fixture driver passes the complete lifecycle on all platforms.

### Phase 2 — Existing harness adapters

- Migrate Codex, Claude, Kimi, Grok, and Hermes to drivers.
- Preserve existing config formats and unrelated settings.
- Add restart-required reporting and repair actions.

Exit: five real-format adapters pass golden fixtures and disposable integration tests.

### Phase 3 — Retrieval completion

- Implement exact indexes, authority scoring, graph retrieval, optional vectors, RRF,
  citations, and disclosure receipts in that order.

Exit: security, correctness, token-budget, performance, and 100k-record gates pass
with vectors both off and on.

### Phase 4 — Projection and lifecycle completion

- Compile all profile-specific vault views.
- Extend controlled correction workflows.
- Complete provider-neutral lifecycle capture and promotion classification.
- Add scheduled backup health.

Exit: five-profile vault goldens and all harness-equivalence fixtures pass.

### Phase 5 — OpenClaw

- Add managed MCP adapter to the launcher.
- Bind and validate native public SDK hooks.
- Test single-agent, multi-agent, fallback, Doctor, and uninstall flows.

Exit: OpenClaw shows accurate MCP/native status and passes the same transaction and
security contracts as every other harness.

### Phase 6 — Recovery and release readiness

- Rehearse clean-machine export/import/reconnect on all platforms.
- Run full threat, accessibility, performance, and migration suites.
- Generate a signed evidence manifest and operator release checklist.

Exit: no unmet P0/P1 criterion, no undocumented capability gap, and no secret or
machine-local credential in the package.

## 11. Test matrix

Every phase runs:

- Python versions supported by LAMF on Windows, macOS, and Linux;
- paths with spaces, Unicode, removable-drive roots, and read-only parents;
- missing, malformed, partially connected, and concurrently modified configs;
- repeated connect/disconnect idempotence;
- service running, stopped, degraded, and wrong-data-directory states;
- each fixed security profile plus representative AI-Custom policies;
- no-vector and vector-enabled retrieval;
- Obsidian absent, closed, open, indexing, and projection failure;
- harness absent, installed, running, and restart-required;
- accessibility: keyboard operation, visible focus, semantic fieldsets/legends,
  announced status changes, and no reliance on color alone.

Connection radio groups must have accessible labels and confirmation state. A busy
row is disabled only for its own transaction; unrelated harnesses remain usable.

## 12. Completion definition

The program is complete only when:

1. Every workstream gate has executable passing evidence.
2. Runtime capability reporting matches reality.
3. All supported harnesses share one authority and survive independent removal.
4. Launcher state is derived from detection plus verification, never wishful state.
5. Clean-machine recovery succeeds on Windows, macOS, and Linux.
6. Security floors pass with FTS, graph, vectors, projection, and native hooks enabled.
7. Token-bounded context reports citations, omissions, and accounting.
8. OpenClaw works through both MCP baseline and native hooks with safe fallback.
9. Documentation describes verified behavior and clearly labels optional components.
10. Final release/publish remains an explicit operator decision.

## 13. Recommended first implementation slice

Start with Phase 0 and the Generic MCP fixture in Phase 1. The first demonstrable
increment should show the launcher UI with accurate Connected, Not connected, and
Needs attention groups, then connect and disconnect a disposable generic harness
through an atomic, rollback-capable transaction. This validates the common machinery
before any real agent configuration is touched.
