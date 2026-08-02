"""LAMF-CANON-1 canonical JSON profile (03_CONTRACTS/canonical-hashing.md).

Normative rules implemented here (DECISIONS.md §G):
  * UTF-8 output, no BOM; every string NFC-normalized before any processing.
  * Object keys sorted by UTF-8 byte order of the NFC key; separators are
    "," and ":" with no whitespace.
  * Minimal string escaping: \\" \\\\ \\b \\f \\n \\r \\t; other control
    characters < U+0020 as lowercase \\u00xx; non-ASCII raw; "/" unescaped.
  * Integers only; floats are rejected (never rounded/formatted). "-0"
    canonicalizes to "0" (Python ints have no negative zero).
  * Duplicate object keys MUST be rejected — including keys that differ only
    in Unicode normalization form.

Pinned interface (runtime/README.md):
    canonicalize(obj) -> str
    sha256_hex(text: str) -> str

`parse_json` is the duplicate-key-rejecting parser the chain of custody
requires (canonical-hashing.md §4.3 / §8); use it for every untrusted JSON
document (spool lines, bundle manifests, ...).
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any

_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


class CanonError(ValueError):
    """Raised for any LAMF-CANON-1 violation (float, duplicate key, type)."""


class DuplicateKeyError(CanonError):
    """Raised when a JSON object repeats a key (after NFC normalization)."""


def _ser_str(s: str) -> str:
    """NFC + minimal escaping (canonical-hashing.md §2/§3)."""
    s = unicodedata.normalize("NFC", s)
    out = ['"']
    for ch in s:
        esc = _ESCAPES.get(ch)
        if esc is not None:
            out.append(esc)
        elif ord(ch) < 0x20:
            out.append("\\u%04x" % ord(ch))  # lowercase hex
        else:
            out.append(ch)  # non-ASCII raw; solidus never escaped
    out.append('"')
    return "".join(out)


def _ser(o: Any) -> str:
    if o is None:
        return "null"
    if o is True:
        return "true"
    if o is False:
        return "false"
    if isinstance(o, str):
        return _ser_str(o)
    if isinstance(o, int):
        # bool handled above; ints format with no leading zeros by construction
        return str(o)
    if isinstance(o, float):
        raise CanonError("floats forbidden in hashed payloads (canonical-hashing.md §5.2)")
    if isinstance(o, (list, tuple)):
        return "[" + ",".join(_ser(x) for x in o) + "]"
    if isinstance(o, dict):
        items = []
        seen = set()
        for k, v in o.items():
            if not isinstance(k, str):
                raise CanonError("object keys must be strings: %r" % (k,))
            nk = unicodedata.normalize("NFC", k)
            kb = nk.encode("utf-8")
            if kb in seen:
                raise DuplicateKeyError("duplicate key after NFC: %r" % k)
            seen.add(kb)
            items.append((kb, nk, v))
        items.sort(key=lambda t: t[0])  # UTF-8 byte order
        return "{" + ",".join(_ser_str(nk) + ":" + _ser(v) for _, nk, v in items) + "}"
    raise CanonError("unsupported type: %r" % type(o))


def canonicalize(obj: Any) -> str:
    """Return the LAMF-CANON-1 canonical string for a JSON value.

    Raises CanonError on floats, non-string keys, duplicate keys after NFC,
    or unsupported types. PINNED SIGNATURE — do not change.
    """
    return _ser(obj)


def canonical_bytes(obj: Any) -> bytes:
    """canonicalize(obj) encoded as UTF-8 (the hashed byte string)."""
    return canonicalize(obj).encode("utf-8")


def sha256_hex(text: str) -> str:
    """Lowercase hex SHA-256 of text encoded as UTF-8. PINNED SIGNATURE."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes_hex(data: bytes) -> str:
    """Lowercase hex SHA-256 of raw bytes (payload blobs, raw hash material)."""
    return hashlib.sha256(data).hexdigest()


def event_hash(event: dict) -> str:
    """hash = SHA-256 of the canonical bytes of the event minus hash/sig
    (canonical-hashing.md §6.2)."""
    e = {k: v for k, v in event.items() if k not in ("hash", "sig")}
    return sha256_hex(canonicalize(e))


def payload_sha256(payload: Any) -> str:
    """SHA-256 of the canonical bytes of a payload value; identical inline or
    by reference. A null payload hashes the 4 canonical bytes of `null`
    (canonical-hashing.md §6.1, U-05)."""
    return sha256_hex(canonicalize(payload))


def parse_json(text: str) -> Any:
    """Parse JSON rejecting duplicate object keys (canonical-hashing.md §4.3).

    Standard-library json keeps the last duplicate silently, which is
    non-conformant; this parser raises DuplicateKeyError instead. NFC-colliding
    duplicates are additionally rejected by canonicalize().
    """

    def _hook(pairs):
        obj = {}
        seen = set()
        for k, v in pairs:
            if k in seen:
                raise DuplicateKeyError("duplicate object key: %r" % k)
            seen.add(k)
            obj[k] = v
        return obj

    return json.loads(text, object_pairs_hook=_hook)
