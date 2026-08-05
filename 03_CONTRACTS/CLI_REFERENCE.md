# LAMF CLI Reference (v2.0.0)

Status: **normative**. This is the exact CLI surface of `DECISIONS.md` §C. Every
other document in this package may reference ONLY these commands. No synonyms, no
extra verbs.

```
lamf init [--profile locked|controlled|trusted-local|open-local] [--data-dir PATH]
lamf start [--install-service] | lamf stop | lamf status
lamf doctor [--adapter openclaw] [--deep]
lamf verify [--deep]
lamf export FILE.lamf                              # passphrase: interactive prompt or LAMF_EXPORT_PASSPHRASE env; NEVER a CLI arg
lamf import FILE.lamf --staged [--data-dir PATH]   # always staged; never auto-activates
lamf activate [--data-dir PATH]                    # atomically activates staged import
lamf security validate FILE.yaml
lamf security explain FILE.yaml
lamf security apply FILE.yaml --require-confirmation
lamf approvals list | lamf approvals approve ID | lamf approvals deny ID
lamf optimizations status | on | off | doctor
lamf optimizations enable MODULE_ID | lamf optimizations disable MODULE_ID
lamf quarantine list | lamf quarantine approve ID | lamf quarantine purge ID
lamf actor list | lamf actor pair | lamf actor revoke ID
lamf adapter install openclaw [--apply] [--profile NAME]
lamf adapter uninstall openclaw [--keep-data]
```

## Global rules

- **Passphrase rule (floor F3):** an export/import passphrase is **never a CLI
  argument**. It is collected by interactive prompt (no echo) or from the
  `LAMF_EXPORT_PASSPHRASE` environment variable. Any invocation attempting to pass
  a passphrase positionally or via a flag is a usage error (exit 2).
- **Precedence rule (A1-32/A1-33):** `--profile` on `adapter install` is valid ONLY
  when no profile was set at `lamf init`. If an init profile exists, it wins and
  passing `--profile` is an error (exit 2).
- **Canonical restore order (A1-34/A1-35):**
  `lamf import FILE.lamf --staged` → rebind secrets → `lamf verify --deep` →
  `lamf activate` → `lamf adapter install openclaw` → `lamf doctor`.
  Rebind/re-encrypt ALWAYS precedes activation (`DECISIONS.md` §M.6).
- **Restore bootstrap (R3-02, self-contained — other docs reference this
  bullet):** a restore targets an EMPTY data directory, so
  `lamf import FILE.lamf --staged` CREATES a fresh instance identity key and
  the well-known `lamf-system` actor in the staged instance (`DECISIONS.md`
  §M/U-13: a bundle contains spine, records, and manifest — never instance key
  material and never actors). Import completion (`lamf activate`) performs a
  **bootstrap operator pairing**: the first human confirmation issues the
  operator credential for the restored instance. Actor bearer tokens are never
  exported and never survive a restore — every actor re-pairs after activate
  (`lamf actor pair` per actor).
- **verify ≠ doctor (A1-36):** `lamf verify` is integrity verification (checkpoints
  + chain tail; `--deep` = full chain + payload store). `lamf doctor` is
  environment/adapter health. They are distinct and never alias.
- Exit codes used by every command (per-command tables reference these):

| code | meaning |
|---|---|
| 0 | success |
| 1 | command executed; check/verification found failures |
| 2 | usage error (bad flags, profile precedence violation, passphrase as arg) |
| 3 | authentication/authorization failure (fail closed) |
| 4 | precondition not met (no staged import, service running, data-dir not empty) |
| 5 | integrity verification failure (chain/checkpoint/manifest) |

---

## lamf optimizations

**Synopsis:** `lamf optimizations status|on|off|doctor` ·
`lamf optimizations enable|disable MODULE_ID`

Controls optional, harness-neutral agent instruction modules. `off` disables
the whole layer without changing individual module selections. `enable` and
`disable` change only the named module. Invalid configuration or module content
must never prevent LAMF memory service from starting.

**Exit codes:** 0 command succeeded; 1 doctor found invalid configuration or a
quarantined module; 2 unknown action or module.

---

## lamf init

**Synopsis:** `lamf init [--profile locked|controlled|trusted-local|open-local] [--data-dir PATH]`

Initialize a data directory: creates `state/`, `spool/`, payload store, the
`actors` table with a bootstrap operator actor (via an interactive pairing),
and writes the selected profile as policy version 1.

| flag | meaning |
|---|---|
| `--profile NAME` | one of `locked`, `controlled`, `trusted-local`, `open-local`. If omitted, no profile is pinned and a later `adapter install --profile` or `security apply` must set one. |
| `--data-dir PATH` | default `~/.lamf` |

**Exit codes:** 0 initialized; 2 usage error; 4 data-dir exists and is non-empty.

**Example:**
```
$ lamf init --profile controlled --data-dir /srv/lamf
operator pairing: confirm fingerprint 7f3a…e2 on the operator device [y/N]: y
initialized /srv/lamf (profile=controlled, policy_version=1)
```

## lamf start | lamf stop | lamf status

**Synopsis:** `lamf start [--install-service]` · `lamf stop` · `lamf status`

Manage the `lamf-server` daemon (L0 socket by default; see `wire-protocol.md`).
The policy key `network.bind` selects the transport rung: `socket_only` (no TCP
listener at all — the tightest value, used by the `locked` profile), `loopback`
(L1), or `lan` (L2, TLS + auth required). With `socket_only`, `lamf start` never
opens a TCP port and L1/L2 configuration is inert.

| flag | meaning |
|---|---|
| `--install-service` | (start) register with the OS service manager (systemd/launchd/Windows Service) and enable at boot |

`lamf status` prints profile, policy_version, event/record counts, spool depth,
unacknowledged `spool_gap` count, and the latest sealed checkpoint head
(seq_hi + chain_head_hash).

**Exit codes:** 0 ok; 1 status reports degraded (sanitizer down / spool full /
unacknowledged gaps); 3 not authorized; 4 start while already running / stop
while not running.

**Example:**
```
$ lamf status
profile: controlled (policy_version 3)
events: 12,441  records: 1,203  spool: 0 events (0 B), gaps: 0
checkpoint: seq_hi=12000 chain_head=9c2f…1a (verified at startup)
```

## lamf doctor

**Synopsis:** `lamf doctor [--adapter openclaw] [--deep]`

Environment/adapter health: server reachable, socket/TCP/TLS configuration per
auth ladder, token validity, plugin version skew, policy mismatch, spool/fsync
health, clock sanity (ts advisory but gross skew is reported).

| flag | meaning |
|---|---|
| `--adapter openclaw` | also run the OpenClaw adapter checks (plugin installed, hooks wired, manifest version) |
| `--deep` | include slow checks (spool fsync probe, payload-store spot reads) |

**Exit codes:** 0 healthy; 1 one or more checks failed; 3 not authorized.

**Example:**
```
$ lamf doctor --adapter openclaw
[ok] server reachable via /srv/lamf/lamf.sock (peer-UID check passed)
[ok] actor token valid (actor=act_01H…, kind=agent)
[ok] openclaw plugin lamf-memory 2.0.0 matches server 2.0.0
[fail] policy mismatch: plugin profile cached 'trusted-local', server is 'controlled'
```

## lamf verify

**Synopsis:** `lamf verify [--deep]`

Integrity verification. Default: verify the latest sealed `checkpoints` row
(instance signature, event_count) plus the bounded chain tail after it
(`DECISIONS.md` §H — startup does the same; never a full scan). `--deep`:
full chain from genesis + payload store content hashes + spool replay
consistency.

| flag | meaning |
|---|---|
| `--deep` | full chain + payload store (slow; scheduled/import-time use) |

**Exit codes:** 0 verified; 5 integrity failure (hash/signature/checkpoint
mismatch); 3 not authorized.

**Example:**
```
$ lamf verify --deep
chain: 12,441 events verified (genesis → 9c2f…1a)  payloads: 312/312 ok
checkpoints: 12 sealed, all instance signatures valid
```

## lamf export

**Synopsis:** `lamf export FILE.lamf`

Build an encrypted portable bundle (`DECISIONS.md` §M): XChaCha20-Poly1305,
Argon2id KDF (m=64 MiB, t=3, p=4), MACed manifest
(`schemas/export-manifest.schema.json`), secrets re-scanned at build time;
quarantine, vector caches, and indexes are excluded (indexes are always rebuilt
from the spine on import, floor F4). Displays the chain-head fingerprint for
out-of-band confirmation at import.

**Passphrase:** interactive prompt or `LAMF_EXPORT_PASSPHRASE`. Never a CLI arg.

**Exit codes:** 0 exported; 2 passphrase passed as argument (usage error);
3 not authorized (operator only); 1 build failed (e.g. secret re-scan hit).

**Example:**
```
$ lamf export backup.lamf
passphrase: ********
export complete: seq 1..12441, 14 files, 38.2 MiB
chain head fingerprint: 9c2f…1a  (record this; import will ask for it)
```

## lamf import

**Synopsis:** `lamf import FILE.lamf --staged [--data-dir PATH]`

Decrypt → verify manifest MAC/checksums → verify checkpoint signature + chain →
reject unsafe paths (allowlist `^[a-z0-9_./-]+$`, no `..`, no absolute, no
symlinks) → migrate into staging → validate imported policy (may only tighten,
never weaken; weakening ⇒ import refused) → rebind secrets (`needs_rebind`
list) → restore/re-encrypt records with NEW local data keys. **Always staged;
never auto-activates.** Targets an EMPTY data directory (`--merge` is deferred,
`08_BUILD_PLAN/RISK_REGISTER.md`).

**Only-tightens baseline (R3-03):** on a clean machine (empty data directory)
there IS no local profile, so the only-tightens comparison baseline is the
**invariant floor** (F1–F12) — the imported policy must not sit below any floor
clause, evaluated per key on the tighten lattice
(`02_SECURITY/SECURITY_PROFILE_OVERVIEW.md` §1.1). The local-profile leg of the
comparison applies ONLY to a re-import into an already-initialized instance,
which additionally requires explicit operator confirmation.

| flag | meaning |
|---|---|
| `--staged` | REQUIRED. Import lands in `<data-dir>/staging/`; activation is a separate command |
| `--data-dir PATH` | target instance |

**Passphrase:** prompt or `LAMF_EXPORT_PASSPHRASE`. The operator MUST type the
chain-head fingerprint displayed at export (§H out-of-band confirm).

**Exit codes:** 0 staged; 4 data-dir not empty; 5 manifest/checkpoint/chain
verification failure or unsafe path rejected; 1 imported policy would weaken
(local profile/floor wins).

**Example:**
```
$ lamf import backup.lamf --staged --data-dir /srv/lamf
passphrase: ********
type the chain head fingerprint shown at export: 9c2f…1a
staged: 12,441 events, 1,203 records; 2 secrets need rebind:
  - openai_api_key (salted ref 8d21…)
  - github_token (salted ref 55af…)
next: rebind secrets, then `lamf verify --deep`, then `lamf activate`
```

## lamf activate

**Synopsis:** `lamf activate [--data-dir PATH]`

Atomically swap staging → live (rename + fsync) and emit an `import` spine
event. Refuses unless the staged import has been rebound and `lamf verify --deep`
has passed on the staging area (canonical restore order).

**Exit codes:** 0 activated; 4 no staged import, or rebind/verify incomplete.

**Example:**
```
$ lamf activate --data-dir /srv/lamf
activated staged import (seq_hi=12441) — import event seq 12442 emitted
```

## lamf security validate

**Synopsis:** `lamf security validate FILE.yaml`

Parse and validate a policy file against `schemas/security-policy.schema.json`
including all machine-checkable invariant-floor constants (F1–F12). Does not
change any state.

**Exit codes:** 0 valid; 1 schema/floor violation (each printed with clause id).

**Example:**
```
$ lamf security validate custom.yaml
[fail] F12: model_self_approval must be false (const)
[fail] F8: approvals.ttl_hours=720 outside [4,168]
```

## lamf security explain

**Synopsis:** `lamf security explain FILE.yaml`

Render the effective policy in human terms: profile cell values, which floor
clauses constrain which keys, and what each capture/promotion/sharing setting
means operationally.

**Exit codes:** 0 rendered; 1 file invalid (validate first).

## lamf security apply

**Synopsis:** `lamf security apply FILE.yaml --require-confirmation`

Apply a policy file: shows the effective diff (`policy_changes.diff_display:
required`, floor F8), requires typed confirmation, enforces step-up auth and
`downgrade_cooldown_hours` for weakening changes, then commits a `policy_change`
spine event and increments policy_version (invalidating all capsules, §N).

**Step-up auth (DECISIONS §U-14):** a fresh operator-credential assertion no more
than **5 minutes old** — an operator token presented over the L0 socket, or an
OS-brokered biometric. A stale or absent assertion fails with exit 3. A
successful step-up is recorded as an `approval` spine event whose `kind` is
`step_up`, with a receipt (T-step-up-receipt).

| flag | meaning |
|---|---|
| `--require-confirmation` | REQUIRED. Without it the command is a usage error (exit 2) |

**Exit codes:** 0 applied; 1 floor/policy violation or cooldown active; 2 missing
`--require-confirmation`; 3 step-up auth failed.

**Example:**
```
$ lamf security apply tightened.yaml --require-confirmation
diff (policy_version 3 → 4):
  capture.sensitive: quarantine → approval
type 'apply policy v4' to confirm: apply policy v4
applied; policy_version=4 (all capsules invalidated)
```

## lamf approvals

**Synopsis:** `lamf approvals list` · `lamf approvals approve ID` · `lamf approvals deny ID`

Operator approval queue (state machine `pending → {approved, denied, expired}`;
timeout = deny per `approvals.ttl_hours`, floor F8). Every transition is
receipted and emits an `approval` spine event.

**Exit codes:** 0 ok; 3 not operator; 1 unknown/expired ID (already decided).

**Example:**
```
$ lamf approvals list
appr_01J… kind=capture_sensitive requester=act_agent1 scope=user:ada sensitive  expires in 41h
$ lamf approvals deny appr_01J…
denied; receipt rcp_02K…; approval event seq 12443
```

## lamf quarantine

**Synopsis:** `lamf quarantine list` · `lamf quarantine approve ID` · `lamf quarantine purge ID`

Quarantine lifecycle (`quarantined → {approved→ingested, purged, expired→purged}`;
TTL = `quarantine.ttl_days`). Quarantine is encrypted at rest, excluded from
search, and excluded from export unless approved first. Approve/purge emit
`quarantine` spine events.

**Exit codes:** 0 ok; 3 not operator; 1 unknown ID.

**Example:**
```
$ lamf quarantine purge qu_01M…
purged qu_01M… (quarantine event seq 12444)
```

## lamf actor

**Synopsis:** `lamf actor list` · `lamf actor pair` · `lamf actor revoke ID`

Actor administration (wire-protocol.md §3). `pair` runs the operator-approved
pairing ceremony — the ONLY actor registration path (agents never
self-register). Issues a per-actor Ed25519 keypair (generated and held
SERVER-side; clients never hold signing keys, wire-protocol.md §3) + a 256-bit
bearer token (stored SHA-256-hashed server-side; client file 0600). `revoke`
fails future requests closed (401); historical events keep attribution.

**Exit codes:** 0 ok; 3 not operator; 4 pairing code expired/used; 1 unknown ID.

**Example:**
```
$ lamf actor pair
pairing code: 9F2A-7C41-D3E8-B6F0-1A5C-84E2-90DB-41CD (valid 10 min, single use; ≥128-bit, shown grouped)
server fingerprint: 7f3a…e2 — confirm on the new actor's client
actor registered: act_01N… kind=agent scopes=[project:lamf]
```

## lamf adapter install

**Synopsis:** `lamf adapter install openclaw [--apply] [--profile NAME]`

Install the OpenClaw adapter: writes the plugin config, wires typed hooks per the
normative hook table (`05_INTEGRATIONS/OPENCLAW_INTEGRATION.md`), backs up
touched files (0600, encrypted-at-rest note). Without `--apply`, prints a plan
(dry run).

| flag | meaning |
|---|---|
| `--apply` | actually modify OpenClaw config (otherwise dry run) |
| `--profile NAME` | ONLY valid when no profile was set at `lamf init`; otherwise an error (precedence: init profile wins) |

**Exit codes:** 0 installed/planned; 2 `--profile` passed while an init profile
exists; 4 OpenClaw installation not found.

**Example:**
```
$ lamf adapter install openclaw --apply
installed lamf-memory 2.0.0 → ~/.openclaw/plugins/lamf-memory
hooks wired: message_received, before_prompt_build, before_tool_call, after_tool_call, agent_end, model_call_started, model_call_ended
(llm_input/llm_output remain OFF — invariant floor)
```

## lamf adapter uninstall

**Synopsis:** `lamf adapter uninstall openclaw [--keep-data]`

Remove adapter-owned config only; restores backups. Memory data, spine, and
actors are preserved unless `--keep-data` is absent AND the operator confirms
deletion interactively (deletion follows `deletion.approval` policy).

| flag | meaning |
|---|---|
| `--keep-data` | remove plugin/config only; keep all LAMF data (default behavior unless operator confirms deletion) |

**Exit codes:** 0 uninstalled; 4 adapter not installed.

---

## Command-to-contract index

| command | contract |
|---|---|
| export / import / activate | `DECISIONS.md` §M, `schemas/export-manifest.schema.json`, `07_PORTABILITY/PORTABILITY_AND_TRANSFER.md` |
| verify | `DECISIONS.md` §H, `canonical-hashing.md` |
| approvals / quarantine | `state-machines.md` §3/§2, `mcp-tools.yaml` (`memory_approvals`) |
| actor | `wire-protocol.md` §3–§4 |
| security * | `schemas/security-policy.schema.json`, `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md` |
| adapter * | `05_INTEGRATIONS/OPENCLAW_INTEGRATION.md` |
| status / doctor | `wire-protocol.md`, `openapi.yaml` `/v1/status`, `/v1/health` |
