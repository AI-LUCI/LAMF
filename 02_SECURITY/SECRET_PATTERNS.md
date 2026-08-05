# LAMF Secret Patterns — Sanitizer Contract

This is the normative contract for the LAMF sanitizer: what must never be captured, how
it is detected, what happens on failure, and what the acceptance tests must prove.
It implements floor clauses F1 (pre-spool, fail-closed) and F11 (value AND source
detection, export re-scan). Policy keys: `secrets.pre_sanitization`,
`secrets.value_detection`, `secrets.excluded_sources[]` (see
`SECURITY_PROFILE_OVERVIEW.md` glossary and
`../03_CONTRACTS/schemas/security-policy.schema.json`).

---

## 1. Placement and fail-closed behavior

- The sanitizer runs **server-side, synchronously, BEFORE any byte reaches the spool**:
  pipeline order is `hook → sanitize → spool → ack → async ingestion` (DECISIONS §F).
- **Fail-closed, never fail-open.** If the sanitizer is unavailable, errors, or exceeds
  its time budget: drop the event, emit a `capture_dropped` gap event, alert the
  operator. A memory gap is recoverable; a persisted secret is not.
- Sanitization must fit inside the 200 ms ack p95 budget (acceptance test
  `T-capture-ack-p95`), which is feasible only with the bounds in §4.
- Sanitized-away spans are replaced with a marker (`[REDACTED:<class>]`), never logged,
  never spooled, never sent to indexes, embeddings, Markdown, Git, or exports.
- Detection is the **conjunction** of source exclusions (§2) and value detectors (§3).
  Either one alone is insufficient and both are mandatory in every profile (F11).

---

## 2. Source exclusions (`secrets.excluded_sources`)

Content originating from these paths, files, or stores must never be captured —
regardless of whether a value detector fires. The shipped baseline (identical in all
four fixed profiles; operators may extend, never empty):

| Pattern | Covers |
|---|---|
| `.env`, `.env.*` | dotenv files (`.env.local`, `.env.production`, ...) |
| `*.pem`, `*.key` | certificate/private-key material |
| `*.p12`, `*.pfx` | PKCS#12 key bundles |
| `id_rsa*`, `id_ed25519*`, `id_ecdsa*`, `id_dsa*` | SSH private keys and their `.pub`/agent artifacts |
| `.aws/credentials` | AWS static credentials |
| `.netrc` | stored FTP/HTTP passwords |
| `.kube/config`, `kubeconfig` | Kubernetes client credentials/tokens |
| `browser_credential_stores` | Chrome/Edge/Firefox/Safari Login Data, `key4.db`, Cookies vaults |
| `os_keychain` | macOS Keychain, Windows Credential Manager, Linux Secret Service reads |

Matching is by path component and well-known store identifier, not merely filename
substring, so `myenv notes.md` is not excluded while `~/project/.env` is. Adapter
installers and hooks must apply the same exclusions to file-watch and command-capture
sources. Questionnaire Q19 answers extend this list.

---

## 3. Value detectors (`secrets.value_detection: required`)

Applied to every candidate capture payload, independent of source.

### 3.1 Known-prefix patterns (non-exhaustive, extensible)

| Class | Pattern (regex shape) |
|---|---|
| AWS access key ID | `AKIA[0-9A-Z]{16}` |
| GitHub PAT (classic) | `ghp_[0-9A-Za-z]{36,}` |
| GitHub PAT (fine-grained) | `github_pat_[0-9A-Za-z_]{22,}` |
| OpenAI-style API key | `sk-[0-9A-Za-z]{20,}` |
| Slack tokens | `xox[baprs]-[0-9A-Za-z-]{10,}` |
| PEM private keys | `-----BEGIN (RSA |EC |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----` |
| JWT | `eyJ[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{5,}` (three base64url segments, header decodes as JSON) |

Patterns are matched case-sensitively on the canonical payload text. New well-known
prefixes may be added by contract update; adding a pattern is a tightening and never
requires a policy change.

### 3.2 High-entropy detector

Tokens (contiguous `[0-9A-Za-z_+/=-]{20,}` runs) whose Shannon entropy per character
meets or exceeds the calibrated threshold are flagged as candidate secrets. The
threshold is **per-encoding** (a single 4.5 bits/char bar is unreachable for hex,
whose true-random ceiling is 4.0 bits/char): runs ≥ 20 chars in
**base64/base64url** encoding require **≥ 4.5 bits/char**; runs in **hex**
encoding require **≥ 3.9 bits/char** (hex of true randomness = 4.0, so the bar
sits just below the ceiling to catch real keys without flagging every hash).
The thresholds are build-time constants tuned
against the P0 fixtures to keep false positives (hashes, UUIDs, base64 media
fragments inside bounds) within the **false-positive budget: ≤ 0.1% on the ordinary
corpus** (normative target in `08_BUILD_PLAN/BENCHMARKS.md`, U-17/V3-13);
flagged ordinary-looking spans go to quarantine in profiles where that class exists,
and are redacted otherwise. Detector miscalibration NEVER disables fail-closed
behavior.

### 3.3 Operator-registered values

The operator may register specific secret values (rotated tokens, internal formats no
regex covers). **Registry storage (U-15):** registration stores, per entry —
`value_enc` (the value AES-256-GCM-encrypted under the **instance key**, random
96-bit nonce per registration), a random per-value `salt`, and `value_len` for
bounded matching. **Matching is in-memory plaintext compare:** values are decrypted
into memory at service start and matched exact-substring against candidate payloads;
plaintext registered values are **never logged**, never spooled, never exported, and
never written to indexes. `ref_name_salted_hash` stays for display/export (DECISIONS
§M.7: secret references export as salted hashes of names; values never export).
Registered values are honored by the export re-scan as well (§5).

---

## 4. Bounds (DECISIONS §F.3)

Sanitization and capture are bounded so the 200 ms ack p95 budget is real:

| Bound | Value |
|---|---|
| Message body | ≤ 32 KiB (`capture.bounds.message_max_kib`, hard ceiling 32) |
| Tool-result excerpt | ≤ 8 KiB (`capture.bounds.tool_excerpt_max_kib`, hard ceiling 8) |
| Single event canonical size | ≤ 64 KiB (larger payloads go to the payload store by reference and are sanitized before storage) |

Truncation appends an explicit marker (`[TRUNCATED]`); silent truncation is forbidden.
Detectors run on the full pre-truncation payload; anything beyond the stored bound that
matched a detector causes the event to carry a `sanitizer_note` — an optional string
field now pinned in `03_CONTRACTS/schemas/event.schema.json` (U-15) and the `events.sanitizer_note`
column — so the gap is auditable.

---

## 5. Export re-scan

At bundle build time every record and payload is re-scanned with the CURRENT detector
set (prefixes + entropy + operator-registered values) before encryption (DECISIONS
§F.2, F11). A match blocks the export with an itemized, receipted report — the bundle is
never built with the secret inside "encrypted"; encryption is not sanitization. This
catches secrets captured before a detector or registration existed.

---

## 6. P0 acceptance-test fixture classes

The P0 secret-exclusion tests must use fixtures from ALL of the following classes, each
asserted absent from spool, segments, payload store, SQLite, search results, capsules,
Git output, and export bundles:

1. **Known-prefix tokens** — every row of §3.1 (AWS `AKIA...`, `ghp_...`,
   `github_pat_...`, `sk-...`, `xoxb-/xoxp-/xoxa-/xoxr-/xoxs-...`, PEM private-key
   blocks, JWTs), planted in chat messages, tool outputs, file attachments, and
   channel-message capture.
2. **High-entropy unbranded tokens** — random strings ≥ 20 chars, each fixture
   **naming its encoding** and meeting the matching §3.2 threshold: base64url
   fixtures at ≥ 4.5 bits/char, hex fixtures at ≥ 3.9 bits/char; including
   lookalikes embedded in ordinary prose.
3. **Source-excluded content** — plausible non-secret content read from §2 sources
   (e.g. `DATABASE_URL=` line inside a `.env` file, a kubeconfig context block), proving
   source exclusion fires even when no value detector does.
4. **Operator-registered values** — a bespoke token matching no prefix/entropy rule,
   registered via the operator flow, then planted.
5. **Negative controls** — near-misses that MUST be captured normally: UUIDs, git commit
   hashes, `sk-proj` prose mentions below length, short passwords under 20 chars with low
   entropy, redaction markers themselves. Guards against an over-broad sanitizer silently
   eating memory.
6. **Late-registered values (export re-scan)** — a value captured BEFORE registration or
   before a prefix pattern existed, caught only by the §5 export re-scan.
7. **Fail-closed fault injection** — sanitizer crashed/timeout mid-capture ⇒ event
   dropped, `capture_dropped` gap event emitted, operator alert raised, nothing spooled.

Each positive class also asserts the redaction marker appears where the secret was, and
that no LAMF log line contains the fixture value.
