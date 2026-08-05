# Obsidian Integration — the operator workspace (normative)

Authority: DECISIONS.md §W-01. This document is the full projection specification;
the executable implementation is `runtime/lamf/project.py` + `runtime/lamf/watch.py`.

**Positioning:** LAMF is the secure memory engine and includes its own local human
workspace. Obsidian is an optional parallel visual layer for operators who prefer a
Markdown vault. Codex, Claude, Kimi, Grok, OpenClaw, Hermes and other AI systems are
interchangeable clients. Obsidian displays
and operates the memory system; it never defines, validates, authorizes, or directly
rewrites memory.

## 1. Architecture

```
LAMF authority (spine + records + policy)
   ├─ built-in local LAMF workspace (always available with the HTTP server)
   └─ optional policy-filtered projection → Obsidian vault (regenerable)
```

- The vault is a **projection, never the database**. Every governed note carries an
  immutable `lamf_id`; any governed file can be regenerated from the authority.
- Obsidian closed ⇒ nothing stops (capture, search, handoffs, security continue).
- LAMF stopped ⇒ the vault keeps its last readable projection; governed changes and
  agent memory operations pause.
- Agents must NEVER treat the vault as their memory interface — they call the LAMF
  API / MCP tools (permission-aware, scope-aware, audited). Obsidian search is for
  the human; LAMF search is for agents and advanced views.
- Harness identity is projected into `04 Agents/`, activity timelines and project
  dashboards so a human can see which client recalled, captured or changed memory.
  Those visual distinctions never create separate stores or separate truths.

## 2. Vault areas and editing rules

```
LAMF Vault/
├── 00 Home.md            (dashboard: native base/query embeds + Mermaid)
├── 01 Memory/            GOVERNED — current memory projections
├── 02 Activity/          GOVERNED — sessions, timelines
├── 03 Projects/          GOVERNED — project dashboards
├── 04 Agents/            GOVERNED — agent profiles/activity
├── 05 Council/           GOVERNED — council rounds/decisions
├── 06 Security/          GOVERNED — security reports/profile state
├── 07 Review Queue/      CONTROLLED — corrections, approvals, external edits
├── 08 Drafts/            OPERATOR — normal notes; never auto-imported
├── 09 Operator Notes/    OPERATOR — normal notes; never auto-imported
└── 99 System/            GOVERNED — instance status, checkpoints
```

- **Governed (01–06, 99):** generated; direct edits are intercepted by the watcher
  (§4). `lamf_editable: false` is displayed on every governed note.
- **07 Review Queue:** the operator acts via LAMF commands (`lamf approvals`,
  correction requests) — never by editing governed files. External-edit copies land
  here as `External Edit - <name>.md`.
- **08/09:** ordinary Obsidian notes. They do not become memory automatically.
  Promotion is explicit only ("submit to LAMF") and enters with taint
  `external_content` — never auto-promoted (U-09).

## 3. Note format (Obsidian Properties contract)

Flat YAML frontmatter ONLY (nested maps are unsupported by Obsidian Properties):

```yaml
---
lamf_id: mem_01K3BC2Q7G
record_type: preference
lamf_version: 4
authority: direct-user-statement
confidence: confirmed
scope: user-private
sensitivity: ordinary
taint: user_direct
projection_hash: 94f72a…
last_projected: 2026-07-30T13:51:00
lamf_editable: false
integrates_with:
  - "[[OpenClaw]]"
supersedes:
  - "[[mem_01K3BC2Q00]]"
---
```

Rules: one first-level list property PER relation type; every wikilink QUOTED;
`last_projected` in `YYYY-MM-DDTHH:mm:ss`; no reserved keys (`tags`, `aliases`,
`cssclasses`) unless their Obsidian semantics are intended. Body: a
`> [!warning] LAMF-governed note` callout, human-readable prose, and a
`## Relations` mirror list (`- integrates-with → [[OpenClaw]]`). Graph edges come
from the first-level property links and body links (Mermaid links do NOT feed the
graph).

`00 Home.md` uses native core features only — `base` embeds, `query` embeds,
Mermaid. NO community plugins (no Dataview). If embeds don't render: Settings →
Core plugins → enable Bases and Search.

## 4. Watcher: protected-file enforcement

`lamf watch` (polling, 1 s) owns governed files:

1. Governed file changed or deleted → compute divergence vs `projection_hash`.
2. Restore the governed version from the authority (temp-file + atomic rename).
3. Preserve the operator's edit as `07 Review Queue/External Edit - <name>.md` —
   work is never discarded.
4. Emit an audit spine event; policy decides warn-only vs restore.
5. NEVER silently import an external edit into authoritative memory.
6. Never write into `.obsidian/` (application-owned); never touch 08/09.

## 5. Security profiles govern the projection

| profile | vault behavior |
|---|---|
| locked | sensitive records project as metadata-only stubs ("Content: request access via `lamf`") |
| controlled | ordinary visible; sensitive stubs pending approval |
| trusted-local | most visible; restricted categories stubbed |
| open-local | all non-secret content visible inside the local trust boundary |
| ai-custom | projection reflects the generated policy (folders, redaction, visibility) |

Secrets NEVER project (F11); exports of the vault re-scan (§M).

## 6. Performance contract (projection never slows agents)

Agent retrieval path is unchanged (API → policy filter → FTS/graph → capsule).
Projection updates are asynchronous: write confirmed BEFORE projection update;
projection normally within 1 s; large dashboard regeneration in background; search
available during rebuilds; projection failures never affect authoritative memory.
The vault can be rebuilt any time: `lamf project --rebuild`.

## 7. Portability

Export bundles MAY include a vault snapshot under `interfaces/obsidian-vault/`;
import never requires it — step 6 of any restore is `lamf project --rebuild`, then
open the folder as a vault in Obsidian (Manage Vaults → Open folder as vault).

## 8. Known limits (file-only MVP, no Obsidian plugin)

True read-only enforcement, approve/reject buttons inside Obsidian, typed graph-edge
labels, and nested-schema editing require an optional Obsidian community plugin
later (manifest.json + main.js per the official sample). The MVP achieves governance
via the watcher + naming + callouts + properties — and states so honestly.
