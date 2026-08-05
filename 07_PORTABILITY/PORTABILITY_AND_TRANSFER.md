# Portability and Transfer

Normative spec for `.lamf` export bundles and clean-machine restore. This file
implements DECISIONS section M; it supersedes the v1 portability doc. CLI commands
used here are exactly those of `03_CONTRACTS/CLI_REFERENCE.md`.

## `.lamf` bundle layout (inside the encrypted container)

```text
manifest.json            # see 03_CONTRACTS/schemas/export-manifest.schema.json
config/policy.yaml       # active policy + policy version history
config/identities.json   # actors, scopes, channel bindings (public material only)
witness/events/*.jsonl   # raw evidence segments (hash-chained, signed)
witness/payloads/*       # content-addressed payload store blobs
records/**               # revisioned memory records
state/schema-version.json
checksums.sha256         # per-file sha256; MACed with the export key
```

The bundle manifest (schema: `03_CONTRACTS/schemas/export-manifest.schema.json`)
contains: format version, created seq range, the **latest signed checkpoint** (chain
head), file list with sha256, schema versions, and the policy.

**EXCLUDED from the bundle, always:**

- secret values (references are exported only as salted hashes of reference names,
  flagged `needs_rebind`);
- quarantine contents (excluded unless explicitly approved first — quarantine state
  machine, `03_CONTRACTS/state-machines.md`);
- vector caches and search indexes (always rebuilt from the spine; a foreign
  `state/index.sqlite` is never trusted — floor F4);
- receipts (operator-read-only, U-08f), spool segments, and **all instance key
  material** (the instance key never leaves the machine, U-13a).

## Crypto spec (floor F3 — passphrase mandatory)

- **Container format (U-13c):** a tar (ustar) payload encrypted with **chunked
  XChaCha20-Poly1305** — 1 MiB plaintext chunks, each AEAD-sealed with a **counter
  nonce** (chunk index, never reused within the bundle). No compression (ratio guards
  are therefore N/A).
- Key derivation: **Argon2id** with m = 64 MiB, t = 3, p = 4, over a mandatory
  operator passphrase + random salt.
- **Manifest MAC (U-13b):** `mac = HMAC-SHA-256(key = HKDF-SHA-256(export_key,
  info="lamf-manifest-mac"), msg = canon(manifest_without_mac) || canon(checksums))`;
  carried as the required `mac` field of `manifest.json`
  (`03_CONTRACTS/schemas/export-manifest.schema.json`) and verified after decrypt,
  before any extraction.
- **Key hierarchy (U-13a):** the instance key (Ed25519 signing + X25519/symmetric
  wrapping counterpart) is created at `lamf init`; its private part lives in the OS
  keychain or a 0600 file and is **NEVER exported**. Bundle records are serialized
  **plaintext INSIDE the AEAD container** — the container is the encryption layer —
  and import re-encrypts every record under NEW local per-record data keys. No
  instance key material, spool segments, receipts, quarantine, indexes, or vector
  caches ever enter the bundle.
- The passphrase is taken from an interactive prompt or the
  `LAMF_EXPORT_PASSPHRASE` environment variable — **never a CLI argument**.
- The manifest pins the **instance pubkey + fingerprint** that signed the bundled
  checkpoint; the chain-head fingerprint is displayed at export time and the operator
  confirms it out-of-band at import time (TOFU, U-13d; `T-instance-key-anchored`).
- Bundle contents are re-scanned for secrets at build time (floor F11).

## Export

```text
lamf export FILE.lamf
```

Indexes, vector caches, and quarantined events are never exported (floor F4):
indexes are always rebuilt from the spine on import.

## Import sequence (normative order)

Import always runs staged (`lamf import` with `--staged`) and never auto-activates.
Steps, in order:

1. **Verify passphrase / decrypt** the container (chunked XChaCha20-Poly1305, counter
   nonces checked in order).
2. **Verify manifest MAC + checksums** (U-13b construction; any mismatch refuses the
   bundle before extraction — `T-export-mac-verified`).
3. **Verify checkpoint signature and event chain** against the bundled signed
   checkpoint, anchored on the **instance pubkey pinned in the manifest** (U-13d);
   the operator confirms the fingerprint out-of-band.
4. **Extraction caps + path safety (U-13c, floor F4)** — reject on: more than
   **10,000 entries** or more than **4 GiB uncompressed** (`T-archive-extraction-limits`);
   path allowlist `^[a-z0-9_./-]+$` — no `..`, no absolute paths, no symlinks, no
   backslashes; PLUS the Windows **device-name denylist** (con, nul, aux, prn,
   com1–9, lpt1–9 — any case, any extension) enforced OUTSIDE the regex; and reject
   empty segments, `.`, `a//b`, `a/./b`, and trailing `/`.
5. **Migrate into a staging data directory** (schema migrations applied in staging).
6. **Policy only-tightens check** — the imported policy may only tighten the local
   profile/floor, evaluated per key against the tighten lattice
   (`02_SECURITY/SECURITY_PROFILE_OVERVIEW.md` §1.1); any weakening refuses the import.
7. **Rebind secrets** — prompt the operator for every `needs_rebind` reference.
   Rebinding precedes record restore.
8. **Restore / re-encrypt records** with NEW local per-record data keys (bundle
   records were plaintext inside the container; they are re-sealed under the NEW
   instance's keys, U-13a).
9. **Rebuild indexes and vector caches from the spine IN STAGING** (foreign indexes
   never used; the rebuild completes before verification and activation — U-17).
10. **`lamf activate`** — atomically swaps staging to live (rename + fsync) and emits
    an `import` spine event.

Canonical restore command order (DECISIONS section C):

```text
lamf import FILE.lamf --staged [--data-dir PATH]
# rebind secrets at the prompt
lamf verify --deep
lamf activate [--data-dir PATH]
lamf adapter install openclaw --apply
lamf doctor --adapter openclaw --deep
```

## Import-into-empty default

Import targets an **empty data directory by default**. Merging into a live instance
would require an explicit `--merge` flag; that flag is **not in the v2.0 CLI** —
deferred and recorded in `08_BUILD_PLAN/RISK_REGISTER.md`.

## Erasure, compaction, and verify (U-08i)

- `lamf verify --deep` accepts a `record_tombstoned` event plus the destroyed data
  key as **proof-of-erasure** and skips content rehash for the shredded payload
  references — a bundle or instance containing tombstones still verifies.
- Segment compaction (rewriting sealed segments minus shredded payloads) preserves
  hashes via a `compaction_checkpoint` payload that pins
  `{segment_range, retained_event_hashes[], removed_payload_refs[]}`.
- Honesty clause (U-08h): bundles exported BEFORE an erasure are outside erasure
  scope; erasure covers the live instance and future exports only.
