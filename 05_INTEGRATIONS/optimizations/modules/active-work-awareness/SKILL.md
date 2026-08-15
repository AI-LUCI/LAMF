---
name: active-work-awareness
description: Prevent duplicate work across LAMF-connected agents by registering current intent, checking active and paused work, and requiring explicit direction before transfer. Use at the start of substantive work, before external publication, when asking the user for blocking input, and when resuming or completing work.
---

# Active Work Awareness

1. After understanding a substantive goal, call `memory_activity` with
   `action=register`, a concise objective, project/workspace, concepts,
   artifacts, and current progress.
2. Treat registration overlap as operational evidence. For medium overlap,
   coordinate. For high overlap, stop before implementation and relay the
   returned `user_notice`.
3. Update the card after meaningful milestones. Do not store raw prompts,
   secrets, credentials, transcripts, or large logs in activity metadata.
4. Immediately before asking the user for required input, call `wait`. LAMF
   changes an unanswered wait to `paused_waiting_for_user` after 30 minutes;
   the card remains visible to other agents.
5. When the user returns, call `resume` before continuing. Before push, PR,
   release, publication, or another externally visible action, call
   `check_overlap` again.
6. A new agent that finds paused/inactive related work must ask whether to
   return to the original agent, transfer, collaborate, replace, or cancel.
   Transfer only with explicit user approval.
7. Call `complete` after verification. Durable results belong in LAMF memory;
   activity cards remain ephemeral operational awareness.

If `memory_activity` is unavailable, state that active-work awareness could not
be checked. Never translate tool absence into “no related work exists.”

Read [references/provenance.md](references/provenance.md) only when evaluating
or updating this optimization.
