# Optional Git Adapter

Git is optional and disabled by default (`git.mode: off` in every fixed profile).
The Witness Spine is always the authority; Git is at most a read-only mirror.

The noob installer offers `--git none` (default for noninteractive runs) or
`--git vault`. Interactive runs ask. Vault mode initializes only the policy-filtered
Obsidian projection, writes a defensive `.gitignore`, and configures no remote. The
operator may later attach that repository to a cloud project. LAMF never pushes or
uploads on the operator's behalf.

## Modes

- `off`: LAMF journal, hashes, sealed checkpoints, snapshots, and export bundles
  provide history. This is the default everywhere; Locked and Controlled SHOULD keep
  `git.mode: off`.
- `local`: records are committed to a local Git repository; no remote is configured.
- `remote`: optional authenticated fetch/push, only when policy `remote_sync` allows
  it AND the operator has explicitly configured a remote. Remote mode never pushes
  sensitive or restricted classes and **documents erasure non-support**: once content
  has been pushed, crypto-shredding (floor F7) cannot retract it from clones — remote
  mode must display this limit at enable time.

## What Git may version

Human-readable memory records of the **ordinary** class only, security policy
revisions, session packs, schemas, and operator notes.

**Sensitive and restricted classes are excluded from Git in ALL modes** (floor F12:
`git.sensitive_classes: excluded`, schema-enforced const). Raw encrypted payloads,
secrets, quarantine, and spool contents remain outside Git.

## Conflict handling

Git is a **read-only mirror of records**; the Witness Spine is the authority.
Conflicts are resolved by the spine — never by merging Git history into authority:

1. the spine's current record state wins;
2. the Git working copy is reset to the spine's projection;
3. divergent Git-side edits are surfaced as ordinary events for operator review, not
   auto-applied.

There is no code path in which `git merge` changes current memory.

## Runtime independence

Search, capture, policy, handoff, export, and restore must pass all tests with
`git.mode: off` and Git absent from the machine. If the Git adapter is unavailable or
fails, events continue and a sync job catches up later; a Git failure never blocks
capture or retrieval (acceptance tests T-git-off-core-passes, T-git-failure-nonblocking
in `08_BUILD_PLAN/ACCEPTANCE_TESTS.md`).
