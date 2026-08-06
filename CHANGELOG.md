# Changelog

All notable changes to the LAMF package are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Optional self-contained Windows 11 x64 installer (`dist/LAMF-Setup-x64.exe`)
  with embedded Python runtime, native `lamf.exe` / `lamf-control.exe` /
  `uninstall.exe` launchers, selectable install/data paths, security profiles,
  harness integrations (Codex, Claude, Kimi, Gemini, Grok, OpenClaw, Hermes,
  generic MCP), optimization module selection, and preserved data on uninstall.
  Verified: 14/14 smoke tests, 141 installer/launcher tests, live Kimi MCP
  acceptance. Current artifact is unsigned; SmartScreen/AppLocker warnings are
  expected and a SHA256 checksum is provided for integrity only.
- Claude Desktop MCPB adapter with cross-platform existing-install discovery,
  explicit Electron stdio proxying, and a live initialization test.
- Provider-neutral harness registrations and tests for Codex, Claude, Kimi,
  Grok Build, OpenClaw, Hermes, and generic MCP clients.
- Privacy-safe recall defaults: automatic orientation, ordinary searches, and
  context capsules exclude sensitive/restricted records unless a call explicitly
  raises `sensitivity_max` in response to a user request.

- Fail-open support for separately distributed agent optimization modules, with
  a global emergency switch and independent enable/disable state per module.
- `lamf optimizations status|on|off|doctor` and per-module
  `enable|disable MODULE_ID` controls.
- Dynamic MCP startup guidance that appends only enabled, valid modules while
  preserving the original LAMF instructions on any optimization failure.
- Isolation tests proving one broken or disabled module cannot affect other
  modules or LAMF memory service.
- Isolation tests proving invalid, disabled, or absent optional modules cannot
  affect the core LAMF memory service.

## [2.0.0] — 2026-01-01 (reconditioning freeze)

The v1 package was attacked in three review rounds (findings in `DEFECT_LEDGER.md`)
and rebuilt into a build-ready architecture package. `DECISIONS.md` is the binding
record of every design decision; below is the summary.

### Added — missing contracts authored

- `03_CONTRACTS/CLI_REFERENCE.md` — the exact `lamf` CLI surface (was implied and
  contradictory across v1 docs).
- `03_CONTRACTS/canonical-hashing.md` + `03_CONTRACTS/golden-vectors.json` —
  LAMF-CANON-1 canonical JSON profile with test vectors.
- `03_CONTRACTS/spool-format.md`, `03_CONTRACTS/wire-protocol.md`,
  `03_CONTRACTS/openapi.yaml` — previously assumed, never specified.
- `03_CONTRACTS/mcp-tools.yaml` — the nine pinned MCP tool names.
- `03_CONTRACTS/state-machines.md` — seven state machines: the six §J machines
  (record, quarantine, approval, handoff, capsule, identity merge) plus the import
  machine; council is specified in `03_CONTRACTS/council.md`.
- `03_CONTRACTS/council.md` — seats, roles, rounds, quorum ratification.
- `03_CONTRACTS/schemas/` — event, memory-record, security-policy, export-manifest
  JSON Schemas, each with `$id` and `version`.
- `02_SECURITY/` — invariant floor F1–F12, threat model, secret patterns, feature
  matrix, four machine-readable profile YAMLs.
- `tools/validate_package.py` — runnable validation harness; the package's only
  "validated" claim.
- `MANIFEST.sha256` — authoritative inventory.
- `08_BUILD_PLAN/WORK_BREAKDOWN.yaml`, `08_BUILD_PLAN/BENCHMARKS.md`,
  `08_BUILD_PLAN/RISK_REGISTER.md`, `08_BUILD_PLAN/OPEN_DECISIONS.template.md`.

### Fixed — contradictions

- **Capture pipeline**: normative order is now
  `hook -> sanitize (fail-closed) -> spool -> ack -> async ingestion`; v1's
  spool-before-sanitize flow would have let secrets reach disk.
- **Startup verification**: sealed checkpoints (every 1,000 events or 24 h) resolve
  the v1 conflict between "verify the chain" and "no full scan at startup"; routine
  startup verifies the latest checkpoint plus a bounded tail.
- **Export crypto**: export is always encrypted (XChaCha20-Poly1305, Argon2id
  m=64 MiB t=3 p=4) and MACed; passphrase mandatory (floor F3); secret values never
  exported; import order corrected to rebind/re-encrypt before activation.
- **CLI canonicalization**: one exact command surface; `lamf verify` (integrity) vs
  `lamf doctor` (environment/adapter) disambiguated; restore order pinned;
  init-profile precedence over `adapter install --profile` pinned.
- **Milestone reordering**: v1's first milestone demanded export/import before the
  phases that build them; milestones M1–M5 now follow phases 1, 2, 4, 5, 8.
- **State machines**: the five lifecycle machines are fully specified with pinned
  transitions; handoff accept-once uses CAS + fencing tokens.
- **Invariant floor F1–F12**: contradictions between profiles resolved by an
  unweakenable floor enforced by the policy schema (fail-closed sanitization,
  authenticated actors, encrypted export, safe import, memory-is-data taint,
  confirmed merges, crypto-shredding erasure, approval hygiene, chain integrity,
  minimum receipts, secret exclusion, no self-approval).

### Removed — duplicates

- All `(1)` duplicate files; the docx/txt duplicate pair; the second copy of
  `PROMPT_FOR_CODING_AI.md`. The manifesto text lives once, in
  `00_EXECUTIVE/OVERVIEW.md`, with claims corrected (twelve phases, three
  blueprints, no restated file counts).

## Round 2 — defect-closure amendments (DECISIONS.md §U)

A second review round (defects V1-*, V2-*, V3-* in `DEFECT_LEDGER.md`) produced
the binding §U amendments. Summary:

- **Validator hardening** — `tools/validate_package.py` executes an `events_fts`
  MATCH plus both FTS rebuilds, and mechanically fails on any referenced but
  undefined test ID; the unsigned-manifest honesty note is stated (accidental
  drift detection, not malice).
- **Erasure architecture** — record bodies become `body_enc` (AES-256-GCM under
  per-record data keys); non-ordinary events must use `payload_ref` (CHECK);
  FTS purge-on-tombstone triggers; quarantine items get per-item data keys that
  purge shreds; receipts carry ids+hashes only; the pre-erasure export/backup
  honesty clause is explicit.
- **Provenance inheritance** — derived content inherits the strictest taint and
  max sensitivity of its `source_events`; tainted `memory_remember` never
  auto-promotes; paste/drop is captured as `external_content`.
- **Tighten lattice** — normative per-key tightest-first order; "downgrade" is
  any key moving down its lattice, enforced by import only-tightens and the F8
  cooldown alike.
- **Schema hardening** — the 16-pattern `excluded_sources` baseline is enforced
  via `allOf`+`contains` (extension-only); approval rate/TTL and downgrade
  cooldown bounds; `network.bind` gains `socket_only`; council policy keys
  (`max_seats_per_actor` const 1, quorum enum) added.
- **Test-registry closure** — `08_BUILD_PLAN/ACCEPTANCE_TESTS.md` is the single
  test-ID registry: 11 renames applied and 37 new tests added (90 registered
  tests); weak citations re-grounded.
- **Crypto pinning** — manifest HMAC, tar (ustar) container with chunked
  XChaCha20-Poly1305 and extraction caps plus a device-name denylist, and the
  instance-key hierarchy (never exported; import anchored on the pinned pubkey
  + TOFU fingerprint).
- **Pairing & step-up** — pairing tokens issued only after out-of-band operator
  confirmation, ≥ 128-bit codes, 5-attempt lockout with backoff; step-up auth =
  a ≤ 5-minute operator assertion recorded as an `approval` event of kind
  `step_up`.
- **Index-export flag removed** — the v1 flag for bundling indexes into exports is
  gone from every surface (CLI, MCP, REST); indexes are never exported, always
  rebuilt from the spine (floor F4).
- **Naming unification** — hyphenated profile names everywhere (`trusted-local`,
  `open-local`, `ai-custom`); snake_case variants banned.

## Round 3 — residual-sweep amendments (DECISIONS.md §V)

A third review round (defects R3-* in `DEFECT_LEDGER.md`; residual sweep + verified
competitive audit) produced the binding §V amendments. Summary:

- **Restore bootstrap** — staged import into an empty data dir creates the instance
  identity key and `lamf-system` actor, and `lamf activate` performs a bootstrap
  operator pairing; all other actors re-pair after restore (tokens never exported).
- **Import only-tightens baseline** — clean-machine imports compare against the
  floor; the local-profile leg applies only to re-import into an initialized
  instance with operator confirmation.
- **Actor key custody** — keypairs are generated server-side at pairing and held by
  the instance (required by the deferred-spool signing form); clients hold only
  bearer tokens.
- **Durability config surface** — batched-fsync lives in `config/server.json`
  (`durability.fsync`), not in a CLI command or a policy key.
- **Handoff actions completed** — `memory_handoff` gains `cancel` and `renew`;
  offers expire after 24 h unaccepted.
- **REST/MCP twin parity** — `/v1/context` clamps at 4000 like `memory_context`;
  `/v1/records/{id}` gains `include_history`; `/v1/orientation` added.
- **Payload-key model** — `record_keys` may key event payloads (events.id) and
  `payload_store` carries the AEAD nonce, making event-payload crypto-shredding
  representable in the schema.
- **Lattice totality** — `capture.ordinary` lattice pins
  `approval > quarantine > automatic`, covering all three schema enum values.
- **Propagation sweep** — F8 bounds, F12 const set, council keys in the §I key tree,
  schema `$id` base, FTS rebuild wording, ≥128-bit pairing examples, pinned
  `[TRUNCATED]` marker, per-encoding entropy thresholds, roadmap scheduling of all
  90 registered tests, and byte-vs-char label corrections.
- **Honesty amendments** — all "Proven by T-…" claims reworded to unexecuted
  acceptance gates; benchmark numbers carry a zero-measurements banner;
  competitive claims reduced to documented parity; `EVALUATION_REPORT.md` records
  the concessions (time-to-first-use, maturity, runnable artifact, ecosystem,
  harness coverage, UI) against Obsidian and akitaonrails/ai-memory.
- **Validator check 8** — Round-3 regression guards (schema `$id` base, F8 bound
  parity, nonexistent-command grep, REST/MCP max_tokens parity, lattice totality,
  handoff actions, quorum definition, truncation marker).

## Round 4 — the build round (DECISIONS.md §W)

The package gained a working reference implementation, the Obsidian operator
workspace, the real OpenClaw plugin, and a noob-first installer.

### Added

- **`runtime/`** — Python reference implementation of the contracts: LAMF-CANON-1
  canonical hashing (byte-exact vs all six golden vectors), Ed25519 hash-chained
  spine with checkpoints, fail-closed sanitization, deferred spool + ingester,
  SQLite store executing `04_STORAGE/SCHEMA.sql` as-is, supersession with history,
  FTS5 search, loopback HTTP API (bearer + Host allowlist), stdio MCP server with
  all nine pinned tools, MAC-verified export/import, and a 16-command CLI.
- **`runtime/tests/smoke_test.py`** — 13-stage end-to-end executable proof
  (golden vectors → init → capture incl. blocked secret → drain → search →
  optimistic-version correction → projection format → watcher restore →
  export/import/verify_deep → MCP handshake → U-08b CHECK). Green.
- **`09_OBSIDIAN/OBSIDIAN_INTEGRATION.md`** + projection/watcher — the Obsidian
  vault as the primary human workspace: eleven pinned areas, governed vs
  operator-editable folders, flat-Properties frontmatter with typed quoted
  wikilinks, native base/query/Mermaid dashboard, watcher that restores tampered
  governed files and preserves edits in `07 Review Queue/`, profile-gated
  projection, regenerable vault.
- **`05_INTEGRATIONS/openclaw-plugin/`** — the real OpenClaw memory plugin
  (replaces the TODO-BIND scaffold): context injection with taint banner, bounded
  `agent_end` capture, tool wrappers, graceful degradation; agent SKILL.md;
  bound to the research-verified OpenClaw surface (2026-07-30).
- **`installer/`** — one-command cross-platform install (sh/ps1/command wrappers
  over `install.py`): venv (with `--copies` + data-dir fallback for symlink-less
  filesystems), init, token, first projection, background start/stop helpers,
  OpenClaw auto-registration with config backup + merge, doctor with per-item fix
  commands, idempotent re-runs, uninstall with purge double-confirm.
- **`runtime/README.md`** — pinned module interface contract + usage.

### Fixed (Round-4 defects, ledger R4-*)

- `lamf serve` now runs the ingester drain loop + throttled projection trigger —
  captured events become searchable records and vault notes with no extra command.
- venv creation falls back (`--copies`, then data-dir location) on filesystems
  without symlink support; helper scripts pass `--data-dir`/`--vault` explicitly
  (HOME-independent).
- `--data-dir` accepted both globally and per-subcommand (order-free CLI).
- `lamf init` is idempotent against installer artifacts; refuses only real prior
  instances.
- `store.get_record` lineage walk cycle-guarded; SQLite connections usable from
  handler threads.
- Export serializes spine segments verbatim (hash-covered fields preserved).
- Runtime crypto deviations documented (DECISIONS §W-06): Argon2id p=1 (libsodium),
  XChaCha20-Poly1305 for record bodies with per-row algorithm recording.

### Hardened — WSL + Windows-drive data dirs (ledger R4-13, R4-14)

- `journal_mode=DELETE` pinned at db creation (persists in the db header): WAL
  needs mmap semantics that Windows-drive mounts in WSL (drvfs/9p, e.g. `/mnt/y`)
  do not reliably provide. Later opens retry best-effort and tolerate SQLITE_BUSY
  from concurrent readers (journal-mode changes ignore busy_timeout) — R4-13.
- `lamf doctor` no longer hard-fails the 0600 operator-token check on drvfs/9p
  mounts, where chmod does not persist; it explains that Windows ACLs protect the
  file instead — R4-14.
- **MCP fallback actually works now (R4-15, found on first real OpenClaw
  attach):** the installer registered the MCP server as bare
  `python -m lamf.mcp_server`, whose entrypoint served all nine tools with
  `store=None` — every call failed `store not attached to server context`.
  Registration now launches `-m lamf.cli mcp --data-dir <dir>` (full context:
  store, policy, spine, ingester) with `LAMF_DATA_DIR` set; the bare module
  entrypoint also attaches the store when an initialized instance exists.
- **Installer is sticky (R4-16, found in the field):** a bare re-run no longer
  creates a second instance at the default `~/LAMF` — it adopts the existing
  registration (data dir + vault recorded in the plugin entry config).
  Explicit `--data-dir`/`--vault` flags re-register with a loud warning.
- **Agent skill boundaries (R4-17):** SKILL.md now forbids the agent from
  running the installer, `init`/`--reset`, editing host config, or killing
  LAMF processes; on memory errors it must report to the operator and continue
  with workspace files.
- **Vault refreshes after direct writes (R4-18, found in the field):**
  `memory_remember`/`correct` via HTTP or MCP and CLI `remember` now refresh
  the Obsidian projection immediately (throttled); previously the vault only
  updated on spool captures or a manual `lamf project`.

## [1.0.0] — original package

Initial architecture package (superseded; retained only as provenance for the
defect ledger).
