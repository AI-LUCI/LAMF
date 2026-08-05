# Harness Adapter Contract (normative)

LAMF is a local memory service, not a feature of any one agent harness. One LAMF
installation owns one authority (event spine, record store, policy, keys and
projection state). Codex, Claude, Kimi, Grok, OpenClaw, Hermes and future clients attach
to that same authority through replaceable adapters.

## Stable core boundary

Every harness MUST use `runtime/lamf_mcp.py` over MCP stdio or the loopback HTTP
API. It MUST NOT read or write `lamf.db`, event segments, key files or governed
Obsidian notes directly. The nine MCP tools and their schemas are the portable
agent contract. The same `LAMF_DATA_DIR` MUST be supplied to every adapter.

An adapter supplies only:

1. harness identity (`harness`, `agent`, `session`, `run`, optional channel/thread);
2. lifecycle mapping (orientation, search, explicit remember, final-turn capture);
3. registration/configuration for the harness;
4. graceful degradation when LAMF is unavailable.

Memory returned to a model is untrusted data. It never overrides the current user,
system/developer instructions, repository guidance, approvals or tool policy.
Automatic and default retrieval MUST use `sensitivity_max=ordinary`. An adapter
may elevate a single search or context call only when the user explicitly asks
for sensitive detail. A broad request such as “what do you know about me?” must
summarize that protected records exist without returning their values.

## Capability levels

- **Level 1 — MCP tools:** portable baseline; all supported harnesses.
- **Level 2 — context hook:** optional automatic, bounded orientation injection.
- **Level 3 — capture hook:** optional sanitized, nonblocking end-of-turn capture.
- **Level 4 — native memory slot:** optional harness-specific integration.

Levels 2–4 are enhancements, never prerequisites. Missing native APIs must reduce
to Level 1 without losing or forking memory.

## Supported registrations

Run `lamf harness list`, `lamf harness emit <id>`, or `lamf harness doctor`.

| harness | baseline | optional native path |
|---|---|---|
| Codex | MCP stdio | repository skill/AGENTS guidance |
| Claude Code | MCP stdio user/project registration | project/user instructions |
| Claude Desktop Home | MCPB extension installed through Advanced settings | desktop extension wrapper |
| Kimi Code CLI | `~/.kimi/mcp.json` | agent skills where supported |
| Grok Build CLI | `~/.grok/config.toml`; `lamf harness apply grok` | Grok skills/hooks |
| OpenClaw | managed MCP registry | native memory plugin hooks |
| Hermes Agent | `~/.hermes/config.yaml`; `lamf harness apply hermes` | Hermes skills/instructions |
| Other | generic MCP JSON | client-defined hooks |

Registration must be idempotent, preserve unrelated settings, back up a file before
changing it, and probe `initialize`, `tools/list`, and `memory_status` afterward.

The installer MUST ask for harness scope on an interactive terminal. `none`, any
subset, and `all` are valid. Noninteractive setup defaults to `none` unless explicit
repeatable `--harness` flags are supplied. Harness scope changes registration only;
LAMF CLI, API, integrity, projection and portability never depend on a harness.

## Single-install invariant

Adapters contain no database, policy, cryptographic key, projection cache or copy
of durable records. Removing one adapter leaves LAMF and every other harness
untouched. Upgrading LAMF changes the universal launcher once; adapters continue to
reference it. Exports contain one authority plus the optional Obsidian projection,
never a separate export per harness.
