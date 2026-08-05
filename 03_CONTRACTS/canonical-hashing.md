# LAMF-CANON-1 — Canonical JSON Profile & Event Hashing

Status: **normative**. Binding per `DECISIONS.md` §G. Every implementation of LAMF
(Rust, TypeScript, Python) MUST reproduce the canonical bytes and hashes in
`golden-vectors.json` exactly (see §8, cross-language parity rule).

LAMF-CANON-1 defines how any JSON value is serialized to a unique sequence of
UTF-8 bytes so that SHA-256 over those bytes is deterministic across languages,
libraries, and platforms. It is the hash basis for the Witness Spine event chain.

---

## 1. Scope

LAMF-CANON-1 applies to:

- every spine **event** (minus `hash` and `sig`) when computing `hash` (§6);
- every **payload** when computing `payload_sha256` (§6);
- any other value whose hash appears in a LAMF contract (checkpoints, manifests).

## 2. Character encoding and string normalization

1. Output is **UTF-8**, no BOM.
2. Every string (object keys and string values) is normalized to **Unicode NFC**
   before any other processing. A combining sequence and its precomposed equivalent
   MUST produce identical canonical bytes (see vector `non-ascii-nfc`).
3. Non-ASCII characters are emitted **raw** as UTF-8. They are never `\uXXXX`-escaped.
4. The solidus `/` is **never** escaped.

## 3. String escaping (minimal)

Inside a string, exactly the following are escaped:

| character      | escape |
|----------------|--------|
| `"` (U+0022)   | `\"`   |
| `\` (U+005C)   | `\\`   |
| BS  (U+0008)   | `\b`   |
| FF  (U+000C)   | `\f`   |
| LF  (U+000A)   | `\n`   |
| CR  (U+000D)   | `\r`   |
| TAB (U+0009)   | `\t`   |

All **other** control characters `< U+0020` are emitted as `\u00xx` with
**lowercase** hexadecimal digits (e.g. U+0001 → `\u0001`, U+001F → `\u001f`).
No other escaping is permitted.

## 4. Objects

1. Keys are sorted by the **UTF-8 byte order** of the NFC-normalized key
   (lexicographic byte comparison, not code-point or locale collation).
   Example order: `"10"` < `"Alpha"` < `"Zulu"` < `"_under"` < `"beta"` < `"zeta"`
   (see vector `key-sorting-proof`).
2. There is **no whitespace**: the member separator is `,` and the key/value
   separator is `:`, with nothing around them.
3. **Duplicate object keys MUST be rejected at parse time.** A parser that silently
   keeps the last value (the default in many JSON libraries) is non-conformant.
   Because key comparison happens after NFC, two keys that differ only in
   normalization form also count as duplicates and MUST be rejected.
4. Empty object: `{}`.

## 5. Arrays, numbers, literals

1. Arrays keep their input order; separator `,` with no whitespace. Empty array: `[]`.
2. **Integers only** inside hashed payloads. Floating-point numbers are forbidden;
   encoders MUST raise an error rather than round or format them.
3. Integer formatting: base-10, **no leading zeros** (`0`, `42`, `-7` are valid;
   `007`, `+1` are not). **`-0` is forbidden** and canonicalizes to `0`; an encoder
   MUST never emit `-0` and a parser MUST reject a literal `-0` in hashed payloads.
4. Literals: `null`, `true`, `false` (lowercase, as in JSON).

## 6. Event hash, prev_hash, payload hash, signature

Given a spine event (fields pinned in `DECISIONS.md` §G and
`schemas/event.schema.json`):

1. `payload_sha256` = lowercase hex SHA-256 of the LAMF-CANON-1 bytes of the
   payload value — identical whether the payload is inline (`payload`) or stored
   by reference (`payload_ref`); the hash is always over the payload **content**.
   For a null payload, `payload_sha256` is the SHA-256 of the canonical
   bytes of `null` (i.e. of the 4 bytes `6e 75 6c 6c`). A null payload is a
   real, hashed value — it is stored inline as the canonical text `null`
   (never SQL NULL, U-05) and hashes identically to any other content.
2. `hash` = lowercase hex SHA-256 of the LAMF-CANON-1 bytes of the event object
   **with the `hash` and `sig` members removed**. All other fields, including
   `prev_hash`, are hashed.
3. `prev_hash` of the **genesis** event (seq 1) is the 64-character ASCII string
   `0000000000000000000000000000000000000000000000000000000000000000`.
   Every later event's `prev_hash` equals the `hash` of the event at `seq − 1`.
4. `sig` = Ed25519 signature by the authoring actor's private key over the
   **32 raw bytes** of `hash` (not the hex string), encoded **base64url**
   (RFC 4648 §5, with padding). Autonomous events authored by the well-known
   system actor **`lamf-system`** (checkpoint, spool_gap, capture_dropped,
   TTL/lease sweeps — `actors.kind = 'system'`) are signed by the **instance
   key** (U-07); verification resolves the actor's key from the `actors` table
   as usual.

## 7. Reference algorithm (Python)

This implementation is the reference. The validation harness
`tools/validate_package.py` re-implements the same rules independently.

```python
import unicodedata, hashlib

_ESCAPES = {'"': '\\"', '\\': '\\\\', '\b': '\\b', '\f': '\\f',
            '\n': '\\n', '\r': '\\r', '\t': '\\t'}

def _ser_str(s: str) -> str:                      # NFC + minimal escaping
    s = unicodedata.normalize('NFC', s)
    out = ['"']
    for ch in s:
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif ord(ch) < 0x20:
            out.append('\\u%04x' % ord(ch))       # lowercase hex
        else:
            out.append(ch)                        # non-ASCII raw; '/' unescaped
    out.append('"')
    return ''.join(out)

def canon(obj) -> bytes:                          # canonical UTF-8 bytes
    def ser(o):
        if o is None:  return 'null'
        if o is True:  return 'true'
        if o is False: return 'false'
        if isinstance(o, str): return _ser_str(o)
        if isinstance(o, int):
            return str(o)                         # no leading zeros; '-0' == 0
        if isinstance(o, float):
            raise ValueError('floats forbidden in hashed payloads')
        if isinstance(o, (list, tuple)):
            return '[' + ','.join(ser(x) for x in o) + ']'
        if isinstance(o, dict):
            items, seen = [], set()
            for k, v in o.items():
                nk = unicodedata.normalize('NFC', k)
                kb = nk.encode('utf-8')
                if kb in seen:
                    raise ValueError('duplicate key after NFC: %r' % k)
                seen.add(kb)
                items.append((kb, nk, v))
            items.sort(key=lambda t: t[0])        # UTF-8 byte order
            return '{' + ','.join(_ser_str(nk) + ':' + ser(v)
                                  for _, nk, v in items) + '}'
        raise TypeError('unsupported type: %r' % type(o))
    return ser(obj).encode('utf-8')

def event_hash(event: dict) -> str:
    e = {k: v for k, v in event.items() if k not in ('hash', 'sig')}
    return hashlib.sha256(canon(e)).hexdigest()
```

## 8. Cross-language parity rule

`golden-vectors.json` is the single parity oracle. The Rust, TypeScript, and
Python implementations MUST, for every vector:

1. parse `input` with a **duplicate-key-rejecting** JSON parser;
2. produce `canonical` byte-for-byte (including NFC normalization);
3. produce `sha256` equal to SHA-256 of those canonical bytes.

Failure on any vector fails acceptance test **T-canonical-hash-parity** (the Python leg of
which is `tools/validate_package.py`, per `DECISIONS.md` §P.4). Implementations
may not "fix" a vector to match their output; the vectors are authoritative.

## 9. Worked example

Input event (genesis; `hash`/`sig` omitted before hashing — this is vector
`lamf-event-genesis` in `golden-vectors.json`):

```json
{
  "id": "018f3c4a-9b2e-7c1d-8a5f-2e6d4c8b1a09",
  "seq": 1,
  "ts": 1735689600000,
  "actor": "act_01HF6ZK4QW7EXAMPLE0000000A",
  "session": "ses_01HF6ZK4QW7EXAMPLE0000000B",
  "type": "message",
  "scope": "user:ada",
  "sensitivity": "ordinary",
  "taint": "user_direct",
  "payload": {"role": "user", "text": "Remember that I prefer morning meetings."},
  "payload_sha256": "c51086efd2178ac63c221a7b3a3c6b4d0eddabe3b2cf129438bb74ff43225d0d",
  "prev_hash": "0000000000000000000000000000000000000000000000000000000000000000"
}
```

Canonical bytes (one line, no whitespace; keys in UTF-8 byte order):

```
{"actor":"act_01HF6ZK4QW7EXAMPLE0000000A","id":"018f3c4a-9b2e-7c1d-8a5f-2e6d4c8b1a09","payload":{"role":"user","text":"Remember that I prefer morning meetings."},"payload_sha256":"c51086efd2178ac63c221a7b3a3c6b4d0eddabe3b2cf129438bb74ff43225d0d","prev_hash":"0000000000000000000000000000000000000000000000000000000000000000","scope":"user:ada","sensitivity":"ordinary","seq":1,"session":"ses_01HF6ZK4QW7EXAMPLE0000000B","taint":"user_direct","ts":1735689600000,"type":"message"}
```

Result:

- `hash` = `343aa05fabc07d730e648a73d1a008727a85797826e4ce6603e0b845c7e6fab2`
- `sig` = base64url(Ed25519_sign(actor_secret_key, bytes.fromhex(hash)))
