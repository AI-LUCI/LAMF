# Instructions for the AI Generating a Custom Security Profile

You are configuring Local Agent Memory Fabric from a completed questionnaire.

## Inputs

- completed `06_SETUP/AI_CUSTOM_QUESTIONNAIRE.md`;
- `03_CONTRACTS/schemas/security-policy.schema.json`;
- the invariant floor F1–F12 in `02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`.

## Required output

Return exactly two fenced blocks:

1. `yaml` containing a complete policy compliant with
   `03_CONTRACTS/schemas/security-policy.schema.json`.
2. `markdown` containing: selected risks, major tradeoffs, prompts the user will see,
   a comparison to the nearest fixed profile, and **an explicit restatement of every
   invariant-floor clause (F1–F12) you preserved** — name each clause and state how
   the generated policy satisfies it.

## Rules

- Do not weaken the invariant floor; restate the floor clauses you preserved (above).
- Do not infer that every local process is trusted merely because the AI is local.
- Set `model_self_approval: false` (floor F12; schema-enforced const).
- Keep network bind loopback unless the questionnaire explicitly requests LAN access.
- AI-Custom policies MAY set `network.bind: "socket_only"` (tightest; no TCP
  listener at all, U-10d). The generator emits `socket_only` ONLY when the
  operator, in the AI-Custom flow, explicitly selects and confirms socket-only
  operation; otherwise the default stays `loopback`. (For reference: the fixed
  `locked` profile defaults to `socket_only`; the other fixed profiles use
  `loopback`.)
- Require authentication and TLS for LAN (floor F12).
- Exclude credentials, private keys, tokens, `.env`, browser credential stores, and
  OS key stores from capture, by value AND by source (floor F11).
- Exports always require a passphrase and are encrypted + MACed (floor F3); a
  questionnaire answer of "no passphrase" must be overridden and flagged to the user.
- Raw LLM transcripts stay off (`capture.llm_transcript: off`, floor).
- Channel identity merges require confirmation (floor F6); never emit an automatic
  merge setting.
- Prefer local embeddings and local consolidation when cloud transmission is
  disallowed.
- Separate ordinary sharing from private/sensitive sharing.
- Describe unanswered questions as conservative defaults, not guesses (contradiction
  handling defaults to the review queue).
- Do not output secret values.

## Application

The operator saves the YAML as security.custom.yaml and runs:

```text
lamf security validate security.custom.yaml
lamf security explain security.custom.yaml
lamf security apply security.custom.yaml --require-confirmation
```

LAMF must display the effective changes as a diff, require step-up confirmation, and
refuse an invalid or weaker-than-floor policy. The applied policy is recorded as a
versioned event on the Witness Spine.
