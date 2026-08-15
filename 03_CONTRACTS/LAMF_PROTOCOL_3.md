# LAMF Protocol 3

Protocol 3 is a clean, quarantined successor to LAMF 2.x. It preserves the
provider-neutral MCP tool names. Fresh authorities are preferred; an existing
2.x authority can be upgraded only through the explicit, offline,
backup-first `lamf migrate-v3` operation.

## Security invariants

1. Memory bodies, titles, tags, and entities are encrypted with per-record
   XChaCha20-Poly1305 keys.
2. Search persists only HMAC-SHA256 blind terms derived from the instance key.
   A copied database cannot reveal searchable vocabulary without that key.
3. Context and orientation responses enforce their complete serialized budget
   and report omissions.
4. Optional optimization instructions are disabled by default, independently
   enabled, and hash-verified before loading.
5. HTTP authentication is constant-time, bounded, and rate-limited.
6. Runtime queues, request bodies, event batches, and security normalization
   passes are bounded.
7. Every live-client validation uses a new instance, synthetic canaries, and a
   client-specific configuration. Production 2.x state is read-only during the
   project.

## Compatibility

- Transport: MCP JSON-RPC over stdio and authenticated loopback HTTP.
- MCP protocol negotiation remains `2025-03-26` for current client support.
- Server identity is `lamf/3.0.0`.
- Existing 2.x databases fail closed during normal open. `lamf migrate-v3`
  first creates and integrity-checks a SQLite backup, then atomically encrypts
  legacy metadata, rebuilds blind search, and records migration version 3.

## Search behavior

Text is NFKC-normalized, case-folded, tokenized, stop-word filtered, and HMACed.
Candidate ranking weights title, entity, tag, and body matches. Authorization,
sensitivity, lifecycle, and scope filters remain authoritative after candidate
generation.

## Cutover rule

No client registration may replace an existing LAMF registration automatically.
Installers produce a side-by-side profile and a rollback manifest. Promotion is
a separate operator action after all security, recovery, and live-client gates
pass.
