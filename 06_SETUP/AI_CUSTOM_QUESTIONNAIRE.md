# LAMF AI-Custom Security Questionnaire

> **Privacy notice.** Your completed answers are a security dossier: they describe
> your users, devices, sensitive data categories, network posture, and secrets
> handling. Prefer a **LOCAL model** to generate your policy from this file. If you
> use a remote model, redact identifying details (names, hostnames, account IDs,
> locations) first. Do not write actual secret values anywhere in your answers.

Complete this file, then give the entire Markdown file to your preferred AI together
with `06_SETUP/AI_CUSTOM_PROFILE_GENERATOR.md` and
`03_CONTRACTS/schemas/security-policy.schema.json`.

The AI must return a single YAML policy plus a plain-language explanation. The policy
must preserve the invariant floor F1–F12 (`02_SECURITY/SECURITY_PROFILE_OVERVIEW.md`);
the schema rejects anything weaker.

## A. People and devices

1. Who uses this computer?  
   Answer:
2. Are all operating-system accounts trusted?  
   Answer:
3. Could untrusted local software run on the machine?  
   Answer:
4. Is full-disk encryption enabled?  
   Answer:
5. Is this a laptop that can be lost or a stationary computer?  
   Answer:

## B. AI topology

6. One AI, several cooperating agents, or a council?  
   Answer:
7. List each agent/seat and what it should be able to read or write.  
   Answer:
8. Should private agent scratch memory be isolated?  
   Answer:
9. May agents hand work to one another automatically?  
   Answer:
10. May a model approve its own durable memory changes? Recommended answer: no.
    (Floor F12 pins `model_self_approval: false`; a "yes" answer is rejected.)  
    Answer:

## C. Channels and identity

11. Which channels will connect: local UI, terminal, voice, Discord, Slack, Telegram, email, other?  
    Answer:
12. Should the same person be recognized across channels?  
    Answer:
13. Should channel identities require confirmation to merge, be suggested on strong
    proof, or remain separate? (Automatic merging is forbidden in every profile —
    floor F6.)  
    Answer:
14. Are group channels allowed to access private user memory? (Group channels resolve
    at channel scope, never merged-principal scope.)  
    Answer:

## D. Memory capture

15. Capture every message, only explicit memories, or a mixture?  
    Answer:
16. Capture tool inputs and outputs? (Tool output is stored with taint `tool_output`
    and never auto-promotes to durable memory.)  
    Answer:
17. Capture full model prompts/responses, sanitized content, metadata only, or none?
    (Raw LLM transcripts are OFF in every profile — floor; at most sanitized content.)  
    Answer:
18. Should memory capture continue if the index or embedding model is unavailable?  
    Answer:
19. Which paths, file types, applications, or keywords must never be captured?  
    Answer:

## E. Sensitivity

20. Will memory include health, legal, financial, employee, credential, intimate, or minor-related information?  
    Answer:
21. Which categories require approval before reading?  
    Answer:
22. Which categories require approval before permanent storage?  
    Answer:
23. Should sensitive content be encrypted separately from ordinary memory?  
    Answer:
24. Should read disclosures be logged item by item, summarized, or not shown to the
    user? (Sensitive-category disclosures are always itemized — floor F10;
    aggregation is permitted only for ordinary reads.)  
    Answer:

## F. Automation and friction

25. How much approval friction is acceptable: every action, sensitive actions only, protected changes only, or almost none?  
    Answer:
26. Should context be injected automatically before every model turn?  
    Answer:
27. Should the AI automatically promote repeated preferences/facts into durable memory?  
    Answer:
28. Should contradictions trigger a user question, a review queue, or automatic
    coexistence? (Default when unanswered: **review queue** — pinned by the record
    state machine in `03_CONTRACTS/state-machines.md`.)  
    Answer:
29. Should failure warnings expire or require reconsideration tests?  
    Answer:

## G. Retention and deletion

30. Default retention period?  
    Answer:
31. Which records should never expire automatically?  
    Answer:
32. Should deleting a memory require confirmation?  
    Answer:
33. Should raw evidence be retained after a derived memory is deleted? (Erasure is
    crypto-shredding — floor F7; shredded evidence is unrecoverable by construction.)  
    Answer:
34. Are legal holds or audit retention needed?  
    Answer:

## H. Network, sync, and Git

35. Must the service remain loopback-only?  
    Answer:
36. Will another local computer access it over a LAN/VPN? (LAN requires TLS 1.3 +
    authenticated actors — floor F12.)  
    Answer:
37. May any content be sent to cloud models or embedding providers?  
    Answer:
38. Git mode: `off`, `local`, or `remote`? (Default is `off`; sensitive/restricted
    classes are excluded from Git in all modes — floor F12.)  
    Answer:
39. If remote Git is enabled, which memory classes may sync? (Never sensitive or
    restricted; remote mode documents erasure limits — see
    `07_PORTABILITY/OPTIONAL_GIT.md`.)  
    Answer:

## I. Portability and recovery

40. How often should backups run?  
    Answer:
41. Should exported bundles require a passphrase? (Floor F3: **a passphrase is
    mandatory** — exports are always encrypted and MACed. A "no" answer will be
    rejected.)  
    Answer:
42. Should indexes be included for fast restore or rebuilt on import? (Indexes and
    vector caches are never exported; they are always rebuilt from the spine — floor
    F4.)  
    Answer:
43. Who may import, export, or change policy? (Policy changes require step-up
    authentication and show an effective diff — floor F8.)  
    Answer:

## J. Final priorities

44. Rank these: privacy, convenience, automatic recall, collaboration, auditability, speed.  
    Answer:
45. Describe anything the AI must never disclose or remember.  
    Answer:
46. Describe the most important behavior you want the memory system to enable.  
    Answer:
