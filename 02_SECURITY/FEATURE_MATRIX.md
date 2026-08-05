# LAMF Security Feature Matrix

Five setup choices, one invariant floor. Cell values are the pinned policy keys from
`../DECISIONS.md` §I; every term is defined normatively in
`SECURITY_PROFILE_OVERVIEW.md` §3 (glossary). Fixed profiles: `profiles/locked.yaml`,
`profiles/controlled.yaml`, `profiles/trusted-local.yaml`, `profiles/open-local.yaml`.
AI-Custom is generated per `SECURITY_PROFILE_OVERVIEW.md` §4 and validated by
`../03_CONTRACTS/schemas/security-policy.schema.json`.

| Policy key | Locked | Controlled | Trusted Local | Open Local | AI-Custom |
|---|---|---|---|---|---|
| `actor_auth` | required | required | required | required | Floor-fixed: `required` (F2). Not configurable. |
| `network.bind` | socket_only | loopback | loopback | loopback | User-configurable within floor: `socket_only` (no TCP listener — tightest) / `loopback` default; `lan` only via explicit operator request, and then F12 forces `lan.enabled/tls/auth` (see LAN rows). |
| `network.lan.enabled` | false | false | false | false | User-configurable within floor: `true` only with `bind: lan` (F12 conditional). |
| `network.lan.tls` | true | true | true | true | Floor-bounded: `true` whenever LAN enabled (F12). |
| `network.lan.auth` | required | required | required | required | Floor-fixed: `required` (F12). Not configurable. |
| `secrets.pre_sanitization` | required | required | required | required | Floor-fixed: `required` (F1). Not configurable. |
| `secrets.value_detection` | required | required | required | required | Floor-fixed: `required` (F11). Not configurable. |
| `secrets.excluded_sources` | baseline list | baseline list | baseline list | baseline list | User-configurable within floor: may only EXTEND the baseline (F11); the 16-pattern baseline is mandatory (schema `minItems: 16` + `contains`). Baseline in `SECRET_PATTERNS.md` §2. |
| `capture.ordinary` | quarantine | automatic | automatic | automatic | User-configurable within floor: `approval` / `quarantine` / `automatic`. Bounds (§F) always apply. |
| `capture.sensitive` | approval | quarantine | protected_automatic | sanitized_automatic | User-configurable within floor: `approval` / `quarantine` / `protected_automatic` / `sanitized_automatic`. No ungated `automatic` exists for sensitive content (F5/F10). |
| `capture.full_prompt` | off | session_policy | sanitized | sanitized | User-configurable within floor: `off` / `session_policy` / `sanitized`. Raw capture does not exist (F11). |
| `capture.llm_transcript` | off | off | off | off | Floor-fixed: `off` (F12; hooks `llm_input`/`llm_output` stay OFF in all profiles). Not configurable. |
| `capture.bounds.message_max_kib` | 32 | 32 | 32 | 32 | User-configurable within floor: 1–32 KiB (§F.3). |
| `capture.bounds.tool_excerpt_max_kib` | 8 | 8 | 8 | 8 | User-configurable within floor: 1–8 KiB (§F.3). |
| `promotion.auto_durable_facts` | no | rule_limited | yes_except_protected | yes_except_invariant | User-configurable within floor: up to `yes_except_invariant`; sensitive/restricted categories can never auto-promote (F5, F12). |
| `promotion.external_content` | never_auto | never_auto | never_auto | never_auto | Floor-fixed: `never_auto` (F5). Not configurable. |
| `model_self_approval` | false | false | false | false | Floor-fixed: `false` (F12). Not configurable. |
| `context.automatic` | no | same_scope_bounded | shared_bounded | shared_bounded | User-configurable within floor: `no` / `same_scope_bounded` / `shared_bounded`. Taint labels and policy-versioned capsules apply regardless (F5, §J). |
| `context.capsule_max_tokens` | 800 | 1200 | 1200 | 1200 | User-configurable within floor: 200–4000 tokens. |
| automatic capsule restricted-exclusion | restricted excluded | restricted excluded | restricted excluded | restricted excluded | Floor-fixed (F12, U-12): automatic capsules NEVER include `restricted` items; `sensitive` items enter automatic capsules only with per-purpose itemized receipts. Not configurable. |
| `sharing.cross_agent_read` | approval | role_scope | registered_local | registered_local | User-configurable within floor: `approval` / `role_scope` / `registered_local`. Actors are always paired + authenticated (F2). |
| `sharing.cross_channel_merge` | manual | confirmed | suggest_confirm | strong_id_confirmed | User-configurable within floor: the enum tops out at `strong_id_confirmed`; automatic merging is FORBIDDEN (F6). Unmerge with receipt always exists. |
| `receipts.read` | every_item | sensitive_itemized | sensitive_itemized | sensitive_itemized_aggregate_ordinary | User-configurable within floor: sensitive disclosures ALWAYS itemized; aggregation permitted only for ordinary reads (F10). No `off`. |
| `deletion.approval` | every_durable_item | protected_items | protected_items | security_identity_only | User-configurable within floor: `every_durable_item` / `protected_items` / `security_identity_only`. |
| `deletion.erasure` | crypto_shredding | crypto_shredding | crypto_shredding | crypto_shredding | Floor-fixed: `crypto_shredding` (F7). Not configurable. |
| `encryption.at_rest` | required | required | sensitivity_driven | recommended | User-configurable within floor: `required` / `sensitivity_driven` / `recommended`. Quarantine stays encrypted regardless (§J). |
| `encryption.export` | required | required | required | required | Floor-fixed: `required` (F3). Not configurable; Q41 "no passphrase" is rejected. |
| `remote_sync` | denied_by_default | explicit | explicit | explicit | User-configurable within floor: `denied_by_default` / `explicit`. Never implicit. |
| `git.mode` | off | off | off | off | User-configurable within floor: `off` / `local` / `remote`. Locked/Controlled SHOULD keep `off`; remote mode must document erasure limits (F7). |
| `git.sensitive_classes` | excluded | excluded | excluded | excluded | Floor-fixed: `excluded` (F12). Sensitive/restricted classes never enter Git. Not configurable. |
| `quarantine.ttl_days` | 30 | 30 | 30 | 30 | User-configurable within floor: 1–90 days (F12); expiry purges. |
| `approvals.ttl_hours` | 72 | 72 | 72 | 72 | User-configurable within floor: 4–168 hours (F8, U-10c); timeout = deny. |
| `approvals.rate_limit_per_actor_per_hour` | 60 | 60 | 60 | 60 | User-configurable within floor: 1–240 (F8, U-10b); anti approval-fatigue control. |
| `policy_changes.diff_display` | required | required | required | required | Floor-fixed: `required` (F8). Not configurable. |
| `policy_changes.downgrade_cooldown_hours` | 24 | 24 | 24 | 24 | User-configurable within floor: ≥ 24 hours (F8, U-10c); any key moving down the tighten lattice (`SECURITY_PROFILE_OVERVIEW.md` §1.1) is a downgrade. |
| `policy_changes.step_up_auth` | required | required | required | required | Floor-fixed: `required` (F8). Step-up = fresh operator assertion ≤ 5 min old (U-14). Not configurable. |
| `council.max_seats_per_actor` | 1 | 1 | 1 | 1 | Floor-fixed: `1` (F12, U-10e). Seats can never be stacked to reach quorum. Not configurable. |
| `council.quorum` | majority | majority | majority | majority | User-configurable within floor: `majority` / `two_thirds` / `unanimous`; may only be raised above majority, never lowered (council.md §5). |

---

## Floor invariants (F1–F12, one-liners)

Full clauses, rationale, enforcement, and acceptance tests: `SECURITY_PROFILE_OVERVIEW.md` §1.

- **F1** Sanitization is mandatory, synchronous, pre-spool, and fail-closed.
- **F2** Every actor is authenticated; registration is pairing-only; TCP rungs validate `Host`/`Origin` (anti-rebinding).
- **F3** Exports are always passphrase-encrypted and authenticated, with out-of-band head confirmation on import.
- **F4** Imports are path-allowlisted, staged, index-rebuilding, secret-rebind-first, and may only tighten policy.
- **F5** Memory is data, not authority: taint labels everywhere; external content never auto-promotes.
- **F6** Identity merges always require confirmation; automatic merging is forbidden; receipted unmerge always exists.
- **F7** Erasure is crypto-shredding: per-record data keys destroyed; fallback queries are redaction-aware.
- **F8** Approvals expire (deny-on-timeout), are rate-limited, show diffs, and policy changes require step-up auth plus downgrade cooldown.
- **F9** Chain integrity: seq-authoritative ordering, per-actor Ed25519 signatures, sealed checkpoints, duplicate keys rejected.
- **F10** Sensitive disclosures are always itemized; security events are always logged with actor identity.
- **F11** Secrets are excluded by value AND source in all profiles; exports are re-scanned.
- **F12** No model self-approval; LAN implies TLS + required auth; quarantine TTL ≤ 90 days; sensitive/restricted classes never enter Git; raw LLM transcripts stay off.

**Every cell value in the table above is defined in the normative glossary,
`SECURITY_PROFILE_OVERVIEW.md` §3.** If a term appears here or in any profile YAML
without a glossary entry, that is a package defect — report it.
