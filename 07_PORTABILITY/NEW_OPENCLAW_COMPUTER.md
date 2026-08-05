# New OpenClaw Computer Installation

Commands below use exactly the CLI surface of `03_CONTRACTS/CLI_REFERENCE.md`.

## Fresh memory

```text
1. Install OpenClaw and complete onboarding.
2. Install LAMF native binary or Docker service.
3. Run: lamf init [--profile locked|controlled|trusted-local|open-local]
4. Choose one of the five security setup options (fixed profile above, or AI-Custom
   via 06_SETUP/AI_CUSTOM_QUESTIONNAIRE.md).
5. Run: lamf start --install-service
6. Run: lamf adapter install openclaw --apply
7. Run: openclaw plugins enable lamf-memory
8. Run: openclaw doctor
9. Run: lamf doctor --adapter openclaw --deep
10. Start a new OpenClaw conversation and verify memory_status + memory_orientation.
```

`--profile` on `adapter install` is valid only when no profile was set at
`lamf init`; otherwise it is an error (init profile wins).

## Restore existing memory

Canonical restore order (DECISIONS section C):

**Bootstrap note (identity is never imported):** a staged import into an EMPTY
data directory creates a NEW instance identity key and the well-known
`lamf-system` actor on the new machine — the old instance key is never exported
and never travels. When the import completes, a **bootstrap operator pairing**
issues the first operator credential for the new instance; every other actor
(humans and agents) **re-pairs** after `lamf activate`, because bearer tokens
are never exported either. Historical events keep their original actor
attribution.

```text
1. Install OpenClaw and LAMF.
2. Run: lamf import my-memory.lamf --staged
   (creates the new instance identity key + lamf-system actor in staging)
3. Rebind local secrets/keys when prompted (needs_rebind list; values were never
   exported).
4. Complete the bootstrap operator pairing to receive the first operator
   credential on this machine.
5. Run: lamf verify --deep
6. Run: lamf activate
7. Re-pair all other actors (lamf actor pair per actor; tokens are per-instance).
8. Run: lamf adapter install openclaw --apply
9. Run: openclaw plugins enable lamf-memory
10. Run: openclaw doctor
11. Run: lamf doctor --adapter openclaw --deep
12. Start OpenClaw; the first turn receives a bounded orientation capsule.
```

Bundle format, crypto, and the full import sequence:
`07_PORTABILITY/PORTABILITY_AND_TRANSFER.md`.

## Windows

Reference release should support a native Windows service / named pipe (the L0 auth
rung uses SO_PEERCRED-equivalent peer checks on Unix sockets and the named-pipe
equivalent on Windows). WSL2/Docker may be the initial stable path, but the exported
data format is identical across platforms.
