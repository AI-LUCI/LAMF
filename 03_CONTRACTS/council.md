# LAMF Council — Multi-Agent Deliberation

Status: **normative**. Implements `DECISIONS.md` §J (council) exactly. A council
is a bounded deliberation among seated actors whose decisions become durable
memory ONLY through the ratification rule below. Council artifacts are records
of type `council_record` (`schemas/memory-record.schema.json`).

---

## 1. Seats

- A **seat** has a stable `seat_id` (e.g. `seat:architecture`) bound **to an
  actor** (`actor_id` from the pairing ceremony, `wire-protocol.md` §1) —
  **never to a model, provider, or prompt-claimed role**. Swapping which model
  backs an actor changes nothing about the seat; swapping the actor requires a
  new seat binding by the operator.
- Seats are created and bound by the operator (policy change; `policy_change`
  spine event). Prompt text, memory content, and model output can never create,
  move, or seize a seat (rule 4 / floor F5).
- A seat is occupied by exactly one actor at a time; an actor may hold at most
  ONE seat — policy `council.max_seats_per_actor: 1` is a floor const in every
  profile (U-10e; T-council-seat-not-model).

### Seat binding / quorum payload (pinned, U-16)

The operator's seat-binding policy change carries this exact payload schema:

```json
{
  "council_id": "council:...",
  "seats": [{"seat_id": "seat:architecture", "actor_id": "act_...", "role": "chair|recorder|member"}],
  "quorum": "majority|two_thirds|unanimous"
}
```

- `seats[]` binds each `seat_id` to a pairing-ceremony `actor_id` and a §2
  role; a `seat_id` appears at most once, and an `actor_id` appears at most
  once (`council.max_seats_per_actor: 1`).
- `quorum` must be one of the policy enum values and defaults to `majority`;
  it may raise, never drop below majority-of-seats (§5).
- Any change to seats or quorum is a `policy_change` event (policy_version
  increments, capsule invalidation per §N) and takes effect only for rounds
  opened after it commits.

## 2. Roles

| role | powers |
|---|---|
| `chair` | opens/closes rounds, orders the agenda, calls votes |
| `recorder` | records claims/objections/votes; writes the round **summary** |
| `member` | claims, objects, votes |

Roles attach to seats (chair seat, recorder seat, member seats), hence
indirectly to actors. The recorder role grants **no ratification authority**
(§5).

## 3. Rounds

A council deliberation proceeds in **rounds**, and the round lifecycle is
itself spine-audited (U-16):

1. the chair opens a round with an agenda item by emitting a
   **`council_round_open`** event (`{council_id, round, agenda_item_id,
   opened_by_seat, ratified}`) — claims, objections, and votes are valid only inside an
   open round;
2. members submit `council_claim` events; members (and the chair) submit
   `council_objection` events against claims;
3. chair calls a vote; each seated member casts at most one `council_vote` per
   agenda item per round;
4. the chair closes the round with a **`council_round_close`** event
   (`{council_id, round, closed_by_seat, carried_items[], ratified}`); the recorder
   writes the summary;
5. a decision is attempted (§4). Undecided items carry to the next round.

**Revocation invalidates pending votes (U-16):** when an actor is revoked
(`actor_revoke` event, `lamf actor revoke`), every not-yet-counted
`council_vote` by that actor — and any pending `council_decision` whose
`signatures[]` rely on that actor — is invalid; quorum is recomputed against
the remaining bound seats. A revoked actor's seat is unbound until the
operator rebinds it by policy change.

Rounds, seats, roles, and votes are all spine events attributed to the acting
actor — the chain (§G) is the audit record of the deliberation.

## 4. Event types

Pinned enum values (`schemas/event.schema.json`):

| type | payload (minimum) | emitted by |
|---|---|---|
| `council_round_open` | `{council_id, round, agenda_item_id, opened_by_seat, ratified}` | the chair (round lifecycle, U-16) |
| `council_round_close` | `{council_id, round, closed_by_seat, carried_items[], ratified}` | the chair (round lifecycle, U-16) |
| `council_claim` | `{council_id, round, seat_id, claim, evidence_events[]}` | any seated member |
| `council_objection` | `{council_id, round, seat_id, target_claim_event_id, objection}` | any seated member or chair |
| `council_vote` | `{council_id, round, seat_id, agenda_item_id, vote ∈ {yea, nay, abstain}}` | each seat, ≤ 1 per item per round |
| `council_decision` | `{council_id, round, agenda_item_id, decision, quorum_required, signatures[]}` | the decision artifact itself |

`ratified` (boolean, **default false**) on the round-lifecycle events makes
§5's labeling requirement constructible (R3-27): a round whose closing
decision is unratified is marked `ratified: false` at close, and any carried
draft decision likewise carries `ratified: false` until a `council_decision`
with ≥ quorum signatures ratifies it.

Every event is signed by its authoring actor's Ed25519 key (§G). Votes are
attributed to seats through the seat→actor binding; a vote whose `seat_id` is
not bound to the signing actor is invalid and discarded (with a `failure`
event).

## 5. Ratification rule

A council decision has **no authority** until ratified:

- A decision is ratified ONLY by a `council_decision` event carrying
  **≥ quorum member signatures**, where quorum is the policy value
  `council.quorum ∈ {majority, two_thirds, unanimous}` (R3-26, numeric
  definitions over the count `n` of seated members): **majority** =
  floor(n / 2) + 1 (the default); **two_thirds** = ceil(2n/3);
  **unanimous** = n. Policy may raise quorum; it may never lower it
  below majority-of-seats. Quorum and signature checks are verified at commit
  (T-council-quorum-signatures).
- Each signature in `signatures[]` is the seat-bound actor's Ed25519 signature
  over the decision's canonical bytes (LAMF-CANON-1); verification uses the
  actors table's public keys.
- **The recorder may record and summarize, but a recorder signature alone
  NEVER ratifies.** If the recorder is also a seated member, their signature
  counts as one member signature toward quorum — as a member, not as recorder.
- An unratified `council_decision` event may exist as a draft artifact but
  MUST be labeled `ratified: false` and confers nothing.

**Recorder summary semantics:** the recorder's round summary is
`taint = agent_generated` **data, not authority** (§K/F5). It may be promoted
to a durable `council_record` only through the normal record path (policy-gated
promotion, review queue for contradictions). Consumers of the summary are bound
by the standard envelope notice: memory content is untrusted data, never
instructions.

## 6. Handoff of council work items

Action items decided by a ratified decision become work items for the handoff
machine (`state-machines.md` §4):

1. the chair (or an authorized member) offers the work item via
   `memory_handoff action=offer`, referencing the ratifying
   `council_decision` event id in `work_item.source_events`;
2. acceptance/completion follow the normal handoff rules — accept-once CAS,
   fencing tokens, 30 min lease, sibling auto-expiry;
3. completing a council work item emits the normal `handoff` event; the
   council MAY require a follow-up `council_claim` reporting completion, but
   the handoff ledger — not the council transcript — is the authority on
   whether the work was done.

Council work items offered to non-council actors are governed by the ordinary
`sharing` policy of the active profile; council membership confers no scope
exemptions.

## 7. Invariants and acceptance tests

1. Seat authority derives only from the seat→actor binding made by the
   operator; model/provider swaps are invisible to the protocol.
2. No claim, objection, vote, summary, or decision may change policy, scope,
   seat bindings, or actor identity (F5).
3. Quorum arithmetic and signature verification are checked by the ingester at
   `council_decision` commit time; failures reject the decision event.

**Acceptance tests:** T-council-recorder-cannot-ratify,
T-council-quorum-signatures, T-council-seat-not-model,
T-council-handoff-roundtrip.
