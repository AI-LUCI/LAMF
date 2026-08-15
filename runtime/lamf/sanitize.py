"""LAMF sanitizer — fail-closed, pre-spool (02_SECURITY/SECRET_PATTERNS.md).

Implements floor clauses F1 (sanitize server-side, synchronously, BEFORE any
byte reaches the spool; never fail-open) and F11 (value-based detection in
every profile). Detection here is the VALUE side of the contract:

  * §3.1 known-prefix patterns (regex list encoded below from
    SECRET_PATTERNS.md, matched case-sensitively);
  * §3.2 per-encoding Shannon-entropy detector (base64/base64url runs
    >= 4.5 bits/char, hex runs >= 3.9 bits/char — build-time constants
    pinned by DECISIONS.md V-09/R3-19);
  * operator-registered values (§3.3 / U-15) are matched exact-substring
    when the caller passes them in (the registry lives in the store;
    plaintext values are decrypted into memory at service start and never
    logged).

Behavior (pinned for the reference runtime): ANY detector match anywhere in
the pre-truncation text raises SecretBlocked(category) — the event is
dropped and the capture path emits a `capture_dropped` gap event
(SECRET_PATTERNS.md §1 fail-closed rule). Redacted-span capture is a
profile-level capture-mode decision that lives above this module.

Byte bounds (DECISIONS.md §F.3, SECRET_PATTERNS.md §4 — all KiB are BYTES,
V1-20): message body <= 32 KiB, tool-result excerpt <= 8 KiB, single event
canonical size <= 64 KiB. Truncation appends the pinned marker "[TRUNCATED]"
(R3-16); silent truncation is forbidden.

Pinned interface (runtime/README.md):
    sanitize(text, policy, sensitivity) -> SanResult(text, notes)
    SecretBlocked(category)  — exception
"""

from __future__ import annotations

import math
import re
import base64
import unicodedata
import urllib.parse
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

# Pinned bounds (DECISIONS.md §F.3; V1-20: KiB are BYTES)
MESSAGE_MAX_BYTES = 32 * 1024
TOOL_EXCERPT_MAX_BYTES = 8 * 1024
EVENT_MAX_BYTES = 64 * 1024          # single canonical event incl. framing
TRUNCATION_MARKER = "[TRUNCATED]"    # pinned marker (R3-16)

# §3.1 known-prefix patterns (verbatim from SECRET_PATTERNS.md; matched
# case-sensitively on the canonical payload text).
SECRET_PATTERNS: Sequence[tuple] = tuple(
    (name, re.compile(rx))
    for name, rx in [
        ("aws_access_key_id", r"AKIA[0-9A-Z]{16}"),
        ("github_pat_classic", r"ghp_[0-9A-Za-z]{36,}"),
        ("github_pat_fine_grained", r"github_pat_[0-9A-Za-z_]{22,}"),
        ("openai_style_api_key", r"sk-[0-9A-Za-z]{20,}"),
        ("slack_token", r"xox[baprs]-[0-9A-Za-z-]{10,}"),
        ("pem_private_key",
         r"-----BEGIN (?:RSA |EC |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----"),
        ("jwt", r"eyJ[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{5,}"),
    ]
)

# §3.2 entropy detector constants (pinned per-encoding thresholds, R3-19)
_ENTROPY_RUN = re.compile(r"[0-9A-Za-z_+/=-]{20,}")
_HEX_RUN = re.compile(r"^[0-9a-fA-F]+$")
_PUBLIC_DIGEST_CONTEXT = re.compile(
    r"(?:sha-?256|sha-?512|checksum|digest|commit|content[ -]?hash|hash)"
    r"\s*(?:[:=]\s*)?$", re.IGNORECASE)
ENTROPY_THRESHOLD_BASE64 = 4.5   # bits/char for base64/base64url runs
ENTROPY_THRESHOLD_HEX = 3.9      # bits/char for hex runs


class SecretBlocked(Exception):
    """Raised fail-closed when a value detector matches candidate content.

    Attributes:
        category: detector class, e.g. "aws_access_key_id",
                  "high_entropy_base64", "high_entropy_hex",
                  "operator_registered".
    """

    def __init__(self, category: str):
        self.category = category
        # Never include the matched span in the message (SECRET_PATTERNS.md:
        # secret material is never logged).
        super().__init__(f"secret detector match: {category}")


@dataclass
class SanResult:
    """Result of a successful sanitize() call. PINNED dataclass shape."""

    text: str
    notes: List[str] = field(default_factory=list)


def shannon_entropy(s: str) -> float:
    """Shannon entropy in bits per character."""
    if not s:
        return 0.0
    counts: dict = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def scan(text: str, registered_values: Optional[Sequence[str]] = None) -> List[str]:
    """Run all value detectors; return the list of detector categories that
    matched (empty = clean). Detector runs happen on the FULL pre-truncation
    text (SECRET_PATTERNS.md §4)."""
    # Scan bounded normalized representations as well as the original.  This
    # closes common transport obfuscations without ever persisting decoded
    # material.  Work is linear and bounded to prevent decompression attacks.
    source = str(text or "")
    normalized = unicodedata.normalize("NFKC", source)
    normalized = re.sub(r"\\u([0-9a-fA-F]{4})",
                        lambda m: chr(int(m.group(1), 16)), normalized)
    decoded_url = urllib.parse.unquote(normalized[:MESSAGE_MAX_BYTES * 3])
    compact = "".join(ch for ch in decoded_url
                      if not ch.isspace() and unicodedata.category(ch) != "Cf")
    variants = [source, normalized, decoded_url, compact]
    for run in re.findall(r"[A-Za-z0-9_+/=-]{24,}", decoded_url)[:64]:
        try:
            raw = base64.urlsafe_b64decode(run + "=" * (-len(run) % 4))
            if 8 <= len(raw) <= MESSAGE_MAX_BYTES:
                variants.append(raw.decode("utf-8", "ignore"))
        except (ValueError, TypeError):
            pass

    hits: List[str] = []
    for candidate in variants:
        for name, rx in SECRET_PATTERNS:
            if rx.search(candidate):
                hits.append(name)
        # Prefixes that are case-insensitive in practice are checked after
        # normalization even though their canonical display form is cased.
        folded = candidate.casefold()
        if re.search(r"akia[0-9a-z]{16}", folded):
            hits.append("aws_access_key_id")
    for m in _ENTROPY_RUN.finditer(decoded_url):
        run = m.group(0)
        if _HEX_RUN.match(run):
            # Public digests are common durable identifiers, not secrets.
            # Exempt only explicitly labelled 40/64/128-character values;
            # unlabelled high-entropy hex remains fail-closed.
            prefix = text[max(0, m.start() - 32):m.start()]
            if len(run) in (40, 64, 128) and _PUBLIC_DIGEST_CONTEXT.search(prefix):
                continue
            if shannon_entropy(run) >= ENTROPY_THRESHOLD_HEX:
                hits.append("high_entropy_hex")
        else:
            if shannon_entropy(run) >= ENTROPY_THRESHOLD_BASE64:
                hits.append("high_entropy_base64")
    if registered_values:
        for _ in registered_values:
            if _ and _ in text:
                hits.append("operator_registered")
                break
    # de-duplicate, stable order
    seen = set()
    out = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def truncate_bytes(text: str, limit: int, notes: List[str]) -> str:
    """Enforce a BYTE bound on UTF-8 text; truncation appends the pinned
    [TRUNCATED] marker (never silent). The result fits within `limit` bytes
    including the marker; a multibyte character straddling the cut is dropped
    whole (never a partial UTF-8 sequence)."""
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    marker = TRUNCATION_MARKER.encode("utf-8")
    cut = max(0, limit - len(marker))
    kept = raw[:cut].decode("utf-8", "ignore")
    notes.append(f"truncated {len(raw)} -> {cut + len(marker)} bytes {TRUNCATION_MARKER}")
    return kept + TRUNCATION_MARKER


def sanitize(text: str, policy, sensitivity: str = "ordinary",
             registered_values: Optional[Sequence[str]] = None,
             excerpt: bool = False) -> SanResult:
    """Sanitize candidate capture text. PINNED SIGNATURE (extra kwargs have
    defaults and are optional extensions):

        sanitize(text, policy, sensitivity) -> SanResult

    Fail-closed (F1): any secret-pattern match raises SecretBlocked(category)
    — the caller MUST drop the event and emit `capture_dropped`.

    Otherwise enforces the policy byte bound (capture.bounds.message_max_kib,
    hard ceiling 32 KiB; `excerpt=True` selects the 8 KiB tool-excerpt bound)
    and returns SanResult(text, notes). `policy` may be a Policy, a raw
    mapping, or None (defaults: 32/8 KiB ceilings).
    """
    # Detectors first, on the FULL pre-truncation text (fail-closed).
    hits = scan(text, registered_values)
    if hits:
        raise SecretBlocked(hits[0])

    # Bound from policy (clamped to the hard ceilings).
    if excerpt:
        limit = TOOL_EXCERPT_MAX_BYTES
        getter = "tool_excerpt_max_kib"
    else:
        limit = MESSAGE_MAX_BYTES
        getter = "message_max_kib"
    kib = None
    if policy is not None:
        if hasattr(policy, getter):
            kib = getattr(policy, getter)
        elif isinstance(policy, dict):
            try:
                kib = int(policy["capture"]["bounds"][getter])
            except (KeyError, TypeError, ValueError):
                kib = None
    if kib:
        limit = min(limit, int(kib) * 1024)

    notes: List[str] = []
    out = truncate_bytes(text, limit, notes)
    return SanResult(text=out, notes=notes)


def sanitize_tool_excerpt(text: str, policy, sensitivity: str = "ordinary") -> SanResult:
    """Convenience: the 8 KiB tool-result excerpt bound (DECISIONS.md §F.3)."""
    return sanitize(text, policy, sensitivity, excerpt=True)
