# Risk Register

Residual and design risks for LAMF v2.0.0. Likelihood/impact: low / medium / high.
Status: `open | mitigated | accepted | deferred`. Mitigations cite the contract or
floor that controls the risk.

## R-01 — Merge-into-live-instance import deferred

- **description**: import targets an empty data directory only; merging a bundle into
  a live instance needs `--merge`, which is not in the v2.0 CLI. Operators needing
  consolidation must export/merge manually or stage a second instance.
- **likelihood**: medium (user need) | **impact**: medium
- **mitigation**: staged import + activate keeps the deferred path safe
  (`07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`); recorded as a future CLI addition
  in `03_CONTRACTS/CLI_REFERENCE.md`-compatible form only after semantics are
  designed. **status**: deferred

## R-02 — OpenClaw SDK drift

- **description**: the public OpenClaw SDK surface (memory capability registration,
  typed hooks, tool registration) may differ from what the scaffold assumes, or may
  change between OpenClaw releases.
- **likelihood**: high | **impact**: medium
- **mitigation**: all binding points are explicit `TODO-BIND:` markers in
  `05_INTEGRATIONS/openclaw-plugin/index.ts`; the normative hook table in
  `05_INTEGRATIONS/OPENCLAW_INTEGRATION.md` is LAMF-side; MCP boundary
  (`03_CONTRACTS/mcp-tools.yaml`) provides a stable fallback;
  T-doctor-diagnostics detects a stale plugin. **status**: open

## R-03 — Embedding inversion

- **description**: local vector embeddings can leak information about sensitive
  content (inversion attacks) even though raw text is encrypted.
- **likelihood**: medium | **impact**: high
- **mitigation**: vectors optional and scope-filtered before similarity
  (`04_STORAGE/INDEXING_AND_SEARCH.md`); sensitive/restricted embeddings live only in
  the protected store; T-scope-leakage and T-scope-before-vector enforce ordering;
  floor F5 keeps vector matches from ever becoming authority. **status**: mitigated

## R-04 — Approval fatigue

- **description**: high-friction profiles train operators to approve reflexively,
  hollowing out the gate.
- **likelihood**: high | **impact**: medium
- **mitigation**: floor F8 caps approval TTL and rate-limits per actor
  (`02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`); profiles graduate friction
  (`02_SECURITY/FEATURE_MATRIX.md`); T-approval-ttl-deny ensures timeouts deny;
  `lamf security explain` surfaces expected prompt volume before apply. **status**:
  mitigated

## R-05 — Sanitizer false-negatives

- **description**: a secret whose format matches no pattern, prefix, or entropy
  threshold reaches the spool and spine.
- **likelihood**: medium | **impact**: high
- **mitigation**: dual source+value detection (`02_SECURITY/SECRET_PATTERNS.md`);
  operator-registered secret values; export-time re-scan (floor F11);
  crypto-shredding erasure (floor F7) removes even committed evidence;
  T-secret-fixtures gates every detection class. **status**: mitigated

## R-06 — Clock skew

- **description**: wall-clock skew across machines corrupts ordering, lease TTLs, and
  approval expiry.
- **likelihood**: medium | **impact**: medium
- **mitigation**: `seq` is the ordering authority; `ts` is advisory
  (`03_CONTRACTS/schemas/event.schema.json`); handoff leases use fencing tokens, not
  timestamps, for correctness (`03_CONTRACTS/state-machines.md`); approval TTL is
  evaluated against the local monotonic clock where available. **status**: mitigated

## R-07 — Windows named-pipe parity

- **description**: the L0 auth rung depends on SO_PEERCRED-equivalent peer checks;
  Windows named pipes have different semantics and may lag in implementation.
- **likelihood**: medium | **impact**: medium
- **mitigation**: per-actor bearer token is required on every rung, so peer checks
  are defense-in-depth (`03_CONTRACTS/wire-protocol.md`); WSL2/Docker is the
  documented interim path (`07_PORTABILITY/NEW_OPENCLAW_COMPUTER.md`);
  T-identity-fail-closed must pass on Windows before release. **status**: open

## R-08 — Large-vault FTS degradation

- **description**: beyond the 100k-chunk benchmark point, FTS latency or capsule
  compile time may exceed targets.
- **likelihood**: medium | **impact**: medium
- **mitigation**: incremental indexing, hotsets, precompiled capsules
  (`04_STORAGE/INDEXING_AND_SEARCH.md`); benchmark gate at 100k chunks
  (`08_BUILD_PLAN/BENCHMARKS.md`); hotset invalidation keyed by
  (record_id, record_version). Re-benchmark at 10x before claiming more.
  **status**: open

## R-09 — Operator passphrase loss

- **description**: the export passphrase is mandatory (floor F3) and Argon2id is
  memory-hard; a lost passphrase makes a backup bundle unrecoverable.
- **likelihood**: medium | **impact**: high
- **mitigation**: `lamf export` displays the chain-head fingerprint and warns that
  passphrase loss is unrecoverable; operators are directed to a password manager or
  printed escrow; LAMF never stores the passphrase
  (`07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`). **status**: accepted

## R-10 — Council quorum misconfiguration

- **description**: a misconfigured quorum (too low, or seats bound to the wrong
  actors) lets a minority ratify decisions.
- **likelihood**: medium | **impact**: high
- **mitigation**: default quorum = majority of seats; seats are bound to paired
  actors, never to model text; ratification requires >= quorum member signatures on
  the `council_decision` event; recorder cannot ratify
  (`03_CONTRACTS/council.md`); T-council-recorder-cannot-ratify. **status**:
  mitigated

## R-11 — Cross-language hash drift

- **description**: Rust, TypeScript, and Python canonicalization implementations
  diverge (unicode normalization, number handling, escaping), breaking chain
  verification across components.
- **likelihood**: medium | **impact**: high
- **mitigation**: LAMF-CANON-1 is fully pinned
  (`03_CONTRACTS/canonical-hashing.md`) with `03_CONTRACTS/golden-vectors.json`;
  T-canonical-hash-parity runs all three languages, the Python leg being
  `tools/validate_package.py` check 4. **status**: mitigated

## R-12 — Supply-chain of local embedding models

- **description**: a downloaded local embedding model may be poisoned, backdoored, or
  license-incompatible.
- **likelihood**: low | **impact**: high
- **mitigation**: models are optional (T-vectors-optional); model choice is an
  explicit open decision recorded in OPEN_DECISIONS.md (from
  `08_BUILD_PLAN/OPEN_DECISIONS.template.md`); embeddings
  are keyed by (model, canonical content hash) so a model swap invalidates cleanly
  (`04_STORAGE/INDEXING_AND_SEARCH.md`); no model download happens during core
  install. **status**: open

## R-13 — Handoff fencing regression vs ai-memory parity

- **description**: subtle deviations in accept-once/lease semantics could either
  double-assign work or strand it, losing parity with ai-memory.
- **likelihood**: low | **impact**: medium
- **mitigation**: semantics pinned (CAS + fencing token + lease TTL + auto-expiry of
  eligible siblings) in `03_CONTRACTS/state-machines.md`;
  T-handoff-accept-once-fencing and T-handoff-lease-expiry. **status**: mitigated

## R-14 — Group-channel scope confusion

- **description**: a group channel resolved at merged-principal scope would leak one
  participant's private memory to the group.
- **likelihood**: medium | **impact**: high
- **mitigation**: floor F6 — group channels resolve at channel scope, never
  merged-principal scope (`02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`);
  T-channel-identity and T-scope-leakage. **status**: mitigated

## R-15 — Instance-key compromise and rotation

- **description**: the instance key (Ed25519 signing + wrapping counterpart) signs
  checkpoints and autonomous `lamf-system` events; compromise lets an attacker
  forge checkpoints and pass `lamf verify`. Rotation re-anchors trust and is
  operationally heavy.
- **likelihood**: low | **impact**: high
- **mitigation**: private part lives only in the OS keychain or a 0600 file and is
  NEVER exported (DECISIONS §U-13; `instance_identity` table pins pubkey +
  fingerprint); the fingerprint is displayed for out-of-band comparison and
  anchors import TOFU (T-instance-key-anchored); a rotated key is detectable
  because historical checkpoints no longer verify against the new key — rotation
  therefore requires an operator-attested re-anchoring event, recorded as an open
  procedure for phase 8. **status**: open

## R-16 — Pre-erasure export/backup residual

- **description**: exports and backups issued BEFORE an erasure still contain the
  erased content; operators may believe erasure reaches already-issued bundles.
- **likelihood**: medium | **impact**: medium
- **mitigation**: honesty clause (floor F7 + `02_SECURITY/THREAT_MODEL.md`,
  DECISIONS §U-08h): erasure covers the live instance and future exports only;
  pre-erasure bundles are outside erasure scope and must be destroyed or aged out
  by the operator; `lamf export` output and docs state this at build time.
  **status**: accepted

## R-17 — Clipboard paste-laundering

- **description**: a user pastes or file-drops sensitive content (including
  secrets) into a chat; if captured as ordinary user text it bypasses the taint
  rules that block `external_content` auto-promotion, laundering provenance.
- **likelihood**: medium | **impact**: medium
- **mitigation**: channel metadata marks paste/drop, and pasted/dropped content is
  captured as `external_content` unless re-typed by the human (DECISIONS §U-09c);
  `tool_output`/`external_content` never auto-promotes (T-taint-inheritance,
  T-remember-laundering-blocked); the sanitizer still scans pasted bytes
  pre-spool. Residual: deliberate re-typing is indistinguishable from authorship.
  **status**: mitigated

## R-18 — Policy-lattice mis-implementation

- **description**: the tighten/weaken lattice is per-key and non-obvious (e.g.
  SMALLER is tighter for numeric caps but LARGER is tighter for
  `downgrade_cooldown_hours`); a wrong comparator silently permits downgrades
  during import or policy apply.
- **likelihood**: medium | **impact**: high
- **mitigation**: normative per-key order pinned tightest-first in DECISIONS
  §U-10g; "downgrade" = ANY key moving down its lattice regardless of the
  `profile` label, evaluated by import only-tightens and the F8 cooldown alike;
  T-import-only-tightens and T-floor-enforced exercise both directions per key.
  **status**: mitigated

## R-19 — TOFU anchor misuse at import

- **description**: import anchors checkpoint verification on the instance pubkey
  pinned in the manifest plus operator fingerprint confirmation (TOFU, DECISIONS
  §U-13d); an operator who rubber-stamps the fingerprint anchors a malicious
  bundle's key.
- **likelihood**: medium | **impact**: high
- **mitigation**: the fingerprint must be typed (not clicked through) and compared
  against the value displayed at export time out-of-band
  (`07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`); mismatch or skipped
  confirmation refuses the import (exit 5); T-instance-key-anchored.
  **status**: mitigated
