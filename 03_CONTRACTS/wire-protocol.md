# Wire Protocol — Identity, Authentication, and Transport

Status: **normative**. Implements `DECISIONS.md` §E exactly. Applies to both
transports that carry the contracts in this directory: the MCP tool surface
(`mcp-tools.yaml`) and the REST hook/admin surface (`openapi.yaml`).

---

## 1. Actor model (`DECISIONS.md` §E.1)

An **actor** is the tuple:

```
actor = (actor_id, kind ∈ {human, agent, operator}, ed25519_public_key, scopes[])
```

- **Agents never self-register.** Actors are created ONLY via the pairing
  ceremony (§3, `lamf actor pair`).
- **One credential never grants another actor's identity.** Every event,
  disclosure, and approval is attributed to exactly one authenticated actor
  (rule 4 enforcement).
- **Prompt text, memory content, and model output can never change actor
  identity, seat authority, scope, or policy** (rule 4; floor F5). Identity
  comes exclusively from the authenticated transport boundary.

### Capability classes

Every MCP tool and REST operation is assigned one of two capability classes
(`DECISIONS.md` §D):

| class | grant |
|---|---|
| `agent` | any authenticated actor; each call is still policy-evaluated |
| `operator` | actors of kind `operator` only — **never grantable to an agent actor**, regardless of scopes |

Class is checked **after** authentication, **before** policy evaluation and
before any disclosure, promotion, or state change.

## 2. Authentication ladder (`DECISIONS.md` §E.2)

The ladder mirrors and hardens ai-memory's. Higher rungs are strictly opt-in;
the default is L0.

### L0 — local socket (DEFAULT)

- Unix domain socket (Linux/macOS) or Windows named pipe. **No TCP listener.**
- Peer identity check (U-14): `SO_PEERCRED` on Linux/macOS Unix domain
  sockets; the client-SID check on Windows named pipes (the server reads the
  pipe client's SID via the named-pipe impersonation API). The peer UID/SID
  MUST match the LAMF service account's allowed client set (default:
  same-UID/same-user only).
- Plus the **per-actor bearer token** (§4) on every request.
- Socket path: `<data-dir>/lamf.sock`, permissions `0600`.
- Policy value: `network.bind: socket_only` (U-10d, tightest rung of the
  tighten lattice) makes L0 the ONLY transport — no TCP listener is ever
  opened. The `locked` profile ships this value.

### L1 — loopback TCP (opt-in)

- Bind `127.0.0.1` / `::1` only. Enabled only by explicit policy
  (`network.bind` configuration).
- Per-actor **bearer token REQUIRED** on every request
  (`Authorization: Bearer <token>`).
- **Anti-DNS-rebinding validation, both headers checked:**
  - `Host` header MUST be in the allowlist `ALLOWED_HOSTS`, default
    `localhost,127.0.0.1,::1` (with optional port).
  - `Origin` header, when present, MUST match the same allowlist (scheme +
    host). Requests with a disallowed `Origin` are rejected.
- Failure of either check ⇒ 403, fail closed.

### L2 — LAN (explicit)

- **TLS 1.3 required** + per-actor bearer token REQUIRED.
- Refused at startup unless policy `network.lan.enabled: true` — and floor F12
  additionally requires `network.lan.tls: true` and `network.lan.auth: required`;
  a policy that sets `lan.enabled: true` without TLS and auth fails validation
  (`lamf security validate` MUST reject it).
- mTLS is permitted but never substitutes for the bearer token.

### Fail-closed error semantics

| condition | response |
|---|---|
| no credentials presented | `401` + `WWW-Authenticate: Bearer` (HTTP) / MCP auth error |
| invalid/expired/revoked token, peer-UID mismatch, bad `Host`/`Origin`, TLS failure | `401` (authentication) or `403` (transport constraint) |
| valid actor, capability class denied (e.g. agent calls an `operator` tool) | `403` |
| valid actor + class, policy denies the specific action | `403` with policy receipt reference |

Missing or invalid identity **always fails closed**. There is no anonymous
identity, no guest fallback, and no header/parameter that asserts identity
(`X-Actor`, `?actor=` etc. MUST be ignored or rejected as protocol errors).

## 3. Pairing ceremony (`lamf actor pair`)

Pairing is the ONLY actor-registration path (`DECISIONS.md` §E.1, floor F2).
U-14 hardening: the bearer token is issued **only AFTER** an out-of-band
operator confirmation, the pairing code carries **≥ 128-bit entropy**, and
code verification is rate-limited:

1. Operator runs `lamf actor pair` on the LAMF host (requires operator
   credential; on L0 it requires same-UID operator shell).
2. The CLI displays a short-lived (≤ 10 min), single-use **pairing code**
   (≥ 128-bit entropy, e.g. 32 hex chars or an 8-word phrase) and the server's
   Ed25519 public-key fingerprint.
3. The new actor's client presents the pairing code over an L0/L1/L2 channel.
4. The server verifies the code (single use, constant-time compare).
   Verification attempts are throttled with **exponential backoff** and a
   **5-attempt lockout** per pairing session (T-pairing-ceremony-lockout); a
   locked-out session requires the operator to restart the ceremony.
5. **The operator confirms the ceremony out-of-band** (compares the displayed
   server fingerprint and the pairing client's identity claim); ONLY THEN does
   the server record the actor `(actor_id, kind, public_key, scopes)` and issue
   the **256-bit bearer token** bound to that `actor_id`. No token exists
   before this confirmation.

**Key custody (R3-04, pinned):** actor Ed25519 keypairs are **generated
server-side at pairing** and held by the LAMF instance (the private key never
leaves the server; clients never hold signing keys). The bearer token is the
actor credential: it authorizes capture and request attribution, and the
ingester signs spine events with the actor's server-held key at ingestion —
consistent with the deferred spool form (`spool-format.md` §2), where the
spool line carries no spine `sig` and the ingester finalizes chain fields. A
hook-side `capture_sig`, when present, is signed by the adapter's own
hook-identity key, which is a capture-attestation credential, not the actor's
spine signing key.
6. Revocation is `lamf actor revoke ID`; revocation deletes the token hash and
   marks the actor revoked — future requests fail closed (401). Historical
   events keep the `actor` attribution. Revocation also invalidates that
   actor's pending council votes (`council.md` §3, U-16).

Agents pair the same way as humans; `kind` is fixed by the operator at pairing
time and is never derivable from request content. (`kind = system` is reserved
for the `lamf init`-created `lamf-system` actor and is never pairable.)

### Step-up authentication (U-14)

**Step-up auth** = a fresh operator-credential assertion **at most 5 minutes
old**: the operator presents their operator token over the L0 socket (with the
peer check above), or an OS-brokered biometric assertion. Required by
`policy_changes.step_up_auth: required` (floor F8) before any policy change
applies. Each step-up is recorded as an `approval` spine event whose **kind is
`step_up`**, receipted (T-step-up-receipt).

## 4. Token storage and verification

- Tokens are **256-bit random** values, shown to the client exactly once.
- The server stores only `SHA-256(token)` in the `actors` table — never the
  plaintext token.
- The client stores its token in a file with **0600** permissions
  (default `<config-dir>/actors/<actor_id>.token`), or in the OS keychain.
- Verification: `SHA-256(presented_token)` compared against the stored hash in
  constant time; the hash lookup also yields the `actor_id` used for all
  attribution. There is no token-to-actor mapping outside this lookup.

## 5. Per-request identity attribution

Every authenticated request establishes exactly one `actor_id`. That identity
is:

- stamped as `actor` on every spine event the request causes;
- the subject of policy evaluation (scope checks, capability class, rate
  limits per `approvals.rate_limit_per_actor_per_hour`);
- itemized on read receipts per floor F10 (`receipts.read`);
- recorded on approvals, quarantine actions, merges, policy changes, exports,
  and imports (floor F10 security-event logging).

## 6. Version negotiation

- Every REST response and MCP server handshake carries
  `LAMF-Protocol-Version: 2.0` (major.minor).
- Clients send `LAMF-Protocol-Version` with the highest minor they support.
- Rule: same **major** ⇒ proceed at `min(client_minor, server_minor)`; major
  mismatch ⇒ `426 Upgrade Required` (HTTP) / MCP protocol error with the
  supported versions listed. Minor-only negotiation never removes fields; it
  may only gate additive features.
- Schema versions are pinned in each schema's `$id`/`version` and in export
  manifests (`schema_versions`), so wire negotiation and stored-data versions
  are independent.

## 7. Request limits (mirror `DECISIONS.md` §F bounds)

Transport-level limits (enforced before parsing bodies):

| limit | value |
|---|---|
| single request body | ≤ 64 KiB (one canonical event max, §F.3) — see batch rule below |
| message body field | ≤ 32 KiB |
| tool-result excerpt | ≤ 8 KiB (truncated with marker) |
| `POST /v1/events` batch | **≤ 64 events AND ≤ 1 MiB total request body** (U-17/V3-07: this batch rule overrides the generic 64 KiB body limit for this endpoint only; each individual event still respects the 64 KiB canonical-event bound and §F.3 field bounds) |
| unauthenticated bytes before auth header | ≤ 8 KiB |

Oversized requests ⇒ `413`, fail closed, no partial ingestion.
