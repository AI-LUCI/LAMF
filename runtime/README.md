# LAMF Reference Runtime (`runtime/`, Python ≥ 3.10)

Reference implementation of the LAMF 2.0.0 spec package (DECISIONS.md §W-02).
**Reference quality: correct, smoke-tested, not production-hardened.** The spec
is the authority; any conflict between it and this code is a bug in this code.

Dependencies: **pyyaml + pynacl ONLY** (`requirements.txt`, pinned by W-02).

```
runtime/
  requirements.txt
  lamf/
    __init__.py     # __version__ = "2.0.0"
    canon.py        # LAMF-CANON-1 canonical JSON + hashing
    crypto.py       # InstanceKey (Ed25519/X25519) + export AEAD
    policy.py       # policy load + invariant-floor check
    sanitize.py     # fail-closed secret blocking + byte bounds
    spine.py        # Witness Spine (append-only hash chain)
    store.py        # SQLite store (04_STORAGE/SCHEMA.sql as-is)
    ingest.py       # spool + capture path + async ingester
    optimizations.py # fail-open, independently switchable agent guidance
    cli.py          # lamf CLI
```

---

## PINNED MODULE INTERFACE CONTRACT

A second coder builds `api.py`, `mcp_server.py`, `project.py`, `watch.py`,
`export_import.py` against these signatures. **Do not diverge.** (Extensions
are allowed only as new optional kwargs with defaults, or new functions.)

### `lamf.canon`

```python
canonicalize(obj) -> str
```
LAMF-CANON-1 (03_CONTRACTS/canonical-hashing.md): NFC, keys sorted by UTF-8
byte order, minimal escaping (`\" \\ \b \f \n \r \t`, other controls as
lowercase `\u00xx`, non-ASCII raw), integers only (floats raise
`CanonError`), duplicate keys rejected (`DuplicateKeyError`, incl. after NFC).
Parity oracle: `03_CONTRACTS/golden-vectors.json` — all vectors reproduced.

```python
sha256_hex(text: str) -> str     # hex SHA-256 of text.encode("utf-8")
```

Also provided: `canonical_bytes(obj)`, `event_hash(event)` (minus hash/sig),
`payload_sha256(payload)` (null payload hashes the 4 bytes `null`),
`parse_json(text)` (duplicate-key-rejecting parser — use for all untrusted
JSON), `CanonError`, `DuplicateKeyError`.

### `lamf.crypto`

```python
class InstanceKey:
    @classmethod generate(path) -> InstanceKey   # fresh Ed25519, file 0600
    @classmethod load(path) -> InstanceKey
    sign(data: bytes) -> bytes                   # raw 64-byte sig
    verify(data: bytes, sig: bytes) -> bool
    pub_hex -> str                               # hex Ed25519 pubkey
    # extensions: pub_b64url, fingerprint(), wrap_key/unwrap_key
    #             (X25519 sealed-box counterpart, U-13a — used by store.py)

export_encrypt(passphrase: str, blob: bytes) -> bytes
export_decrypt(passphrase: str, blob: bytes) -> bytes
```
Container: `b"LAMF1" || salt(16) || nonce(24) || XChaCha20-Poly1305 ct`;
key = Argon2id(passphrase, salt, m=64 MiB, t=3). **Documented deviation:**
§M.1 pins p=4, but libsodium's `crypto_pwhash` API (the only pinned path)
fixes parallelism=1; t/m are exact, p=1 is a libsodium constant on both
sides, so the format is self-consistent. Wrong passphrase / tamper ⇒
`ValueError`. Empty passphrase refused (floor F3).

### `lamf.policy`

```python
PROFILES                                # Path to 02_SECURITY/profiles/
load_policy(path) -> Policy             # Policy(name: str, raw: dict)
floor_check(policy) -> list[str]        # [] = conformant
```
`floor_check` enforces the machine-checkable F1–F12 subset mirroring
`03_CONTRACTS/schemas/security-policy.schema.json` (consts, enums, bounds, the 16-pattern
excluded_sources baseline, the LAN conditional). Violation strings are
clause-prefixed (`"F8: approvals.ttl_hours=720 outside [4,168]"`). F4/F9 are
runtime clauses, not document-checkable. All four shipped profiles pass.
Also: `SOURCE_EXCLUSION_BASELINE`, `Policy.get/message_max_kib/
tool_excerpt_max_kib/capsule_max_tokens`.

### `lamf.sanitize`

```python
sanitize(text: str, policy, sensitivity: str) -> SanResult(text, notes: list[str])
class SecretBlocked(Exception)   # .category: str
```
Fail-closed (F1): any detector match raises `SecretBlocked(category)` — the
caller drops the event and emits `capture_dropped`; nothing is spooled.
Detectors: the 7 SECRET_PATTERNS.md §3.1 prefix regexes, the §3.2
per-encoding entropy detector (base64/base64url ≥ 4.5, hex ≥ 3.9 bits/char,
runs ≥ 20 chars — pinned build-time constants), and optional operator-
registered values (`registered_values=` kwarg, exact substring, §3.3/U-15).
Byte bounds (BYTES, V1-20): message 32 KiB / tool excerpt 8 KiB
(`excerpt=True` kwarg or `sanitize_tool_excerpt`) / event 64 KiB; truncation
appends the pinned `[TRUNCATED]` marker and fits the result inside the bound.
Also: `scan(text, registered_values) -> list[str]`, `truncate_bytes`,
constants `MESSAGE_MAX_BYTES / TOOL_EXCERPT_MAX_BYTES / EVENT_MAX_BYTES /
TRUNCATION_MARKER`, `SECRET_PATTERNS`.

### `lamf.spine`

```python
class Spine(events_dir, instance_key=None):
    append(event: dict) -> tuple[int, str]   # (seq, hash)
    verify_tail(n=1000) -> bool
    verify_deep() -> bool
    head() -> tuple[int, str]                # (0, "0"*64) when empty
```
`append` accepts two forms. DEFERRED (capture/spool, spool-format.md §2 — no
seq/prev_hash/hash/sig): assigns seq (strictly monotonic) and prev_hash
(genesis = 64 zeros), computes `hash = sha256_hex(canonicalize(event −
hash/sig))`, signs the 32 raw hash bytes with the InstanceKey (Ed25519 →
base64url), finalizing the dict **in place**. FINALIZED (import/restore
replay, §M): all four chain fields present — validated (seq == head+1,
prev_hash == head, hash recomputes, sig well-formed) and appended **as-is**,
preserving the source instance's signature (U-13d anchors trust on the
manifest-pinned pubkey). Partially-chained events are rejected. Lines go to
`events/segment-NNNNNN.jsonl` (rotation at 64 MiB, 0600, fsync per-append,
64 KiB line bound). V-03 custody: signing is server-side; the reference
runtime signs local events with the instance key (U-07). `verify_tail(n)`
checks the bounded tail; `verify_deep` checks from genesis — hashes and chain
continuity always; signatures follow the restore-aware policy: all-local,
all-foreign (hash-only, TOFU per §H), or foreign-prefix→local-suffix are
valid; any non-verifying signature AFTER a locally-verified one is a splice
(T-chain-splice-rejected) and fails. Also: `uuid7()`, `now_ms()`,
`iter_events()`, `GENESIS_PREV_HASH`, `SpineError`.

### `lamf.store`

```python
Store.open(db_path, schema_path="04_STORAGE/SCHEMA.sql") -> Store
    # optional kwarg: instance_key=… (else auto-loads <db_dir>/instance.key)
.upsert_record(rec: dict) -> str                       # record_id
.supersede(record_id, new_rec: dict, reason: str) -> str   # NEW record_id
.get_record(record_id, include_history=False) -> dict  # + history / superseded_chain
.search_fts(query, limit=20, filters=None) -> list[dict]   # dicts carry "score"
.stats() -> dict
.close()
```
Executes `04_STORAGE/SCHEMA.sql` as-is on a fresh db; `PRAGMA
foreign_keys=ON`, WAL, busy_timeout. Records are field-level encrypted
(U-08a): per-record 256-bit data key wrapped to the instance key's X25519
counterpart; `body_enc = nonce(24) || ct || tag(16)`. **Documented
deviation:** SCHEMA comments say AES-256-GCM, but pynacl has no AES-GCM — the
runtime substitutes XChaCha20-Poly1305 (AEAD, random nonce per message;
`record_keys.alg` records the actual algorithm; crypto-shredding erasure
semantics identical). FTS: `records_fts` is app-maintained (plaintext body
indexed only inside the write transaction; tombstone-purge triggers own
deletes); search re-checks state/scope/sensitivity at read time (§N: index is
a candidate generator, never authority). Additional primitives for api:
`insert_event`, `event_exists`, `put_payload`/`get_payload` (content-
addressed, V-07 key model), `ensure_actor`, `actor_exists`, `set_high_water`,
`list_approvals`, `decide_approval`, `head_seq`, `StoreError`.

### `lamf.ingest`

```python
class Ingester(spool_dir, spine, store, policy, instance_key=None, on_event=None):
    drain_once() -> int          # newly ingested events
    run_forever(interval=0.5)
```
Replay per spool-format.md §6: order = (segment, offset); idempotency key
(id, payload_sha256) — duplicates skip; same id with a different payload hash
⇒ quarantine row + `quarantine` spine event, never overwrite. Accepted
events are chain-finalized by `Spine.append` (server-held key) and mirrored
into SQLite; the ingester high-water mark moves transactionally (U-17);
drained segments are retired. `on_event(event)` fires after indexing (the
projection hook, W-02). Also provided for the capture path:
`capture_event(spool_dir, store, event, policy) -> ack` (sanitize →
U-04/U-08b spill → spool → ack; raises `SecretBlocked` / `CaptureDropped`
fail-closed), `spool_append(spool_dir, event)`, `CaptureDropped`.

### `lamf.cli`

```
lamf [--data-dir PATH] <command>     # data dir: --data-dir > LAMF_DATA_DIR > ~/LAMF
init [--profile locked|controlled|trusted-local|open-local]   # default controlled
serve | capture | search | remember | get | context | status | doctor
project | watch | export | import | verify | mcp | approvals
```
`init` creates `events/  spool/  lamf.db  policy.yaml  instance.key(0600)
operator.token(0600, 32-byte hex)`, seeds the `lamf-system` + `lamf-operator`
actors and the `instance_identity` row, and prints next steps.
Export/import passphrases come from the interactive prompt or
`LAMF_EXPORT_PASSPHRASE` — never a CLI arg (floor F3). Exit codes per
CLI_REFERENCE.md (0/1/2/3/4/5). `api` / `mcp_server` / `project` / `watch` /
`export_import` are imported **lazily** inside their subcommands; a missing
module breaks only its own command.

### ctx contract for the second coder

`cli._open_ctx()` returns the namespace handed to `api.serve(ctx)`,
`mcp_server.serve_stdio(ctx)`, `watch.watch_loop(vault, ctx)` with fields:
`data_dir` (Path), `store` (Store), `policy` (Policy|None), `spine` (Spine),
`instance_key` (InstanceKey|None), `ingester` (Ingester). Pinned W-02
delegation signatures: `api.serve(ctx)`, `mcp_server.serve_stdio(ctx)`,
`project.project_all(store, policy, vault) -> dict` (+ `project_record`),
`watch.watch_loop(vault, ctx)`, `export_import.export_bundle(dest,
passphrase)` / `export_import.import_bundle(src, passphrase, dest_dir)`.

## Running

```
python3 -m venv /tmp/lamf-venv && /tmp/lamf-venv/bin/pip install -r requirements.txt
/tmp/lamf-venv/bin/python -m lamf.cli init --profile controlled
```
