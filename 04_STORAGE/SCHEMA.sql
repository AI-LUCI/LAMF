-- ============================================================================
-- LAMF 2.0.0 — SQLite storage schema (04_STORAGE/SCHEMA.sql)
-- Normative per DECISIONS.md §G/§H/§J/§L/§M/§N, amended by §U (Round-2):
--   U-02 events_fts contentless; U-05 payload_json never SQL-NULL;
--   U-06 identity_links partial-unique; U-07 actors.kind 'system';
--   U-08 body_enc / sensitivity CHECK / FTS+tombstone purge / embedding_cache
--       record_id / quarantine keys in record_keys;
--   U-15 secrets_registry value_enc/salt/value_len;
--   U-16 council_round_open/close; U-17 new tables/columns/FKs.
--
-- Runtime pragmas (single writer, WAL):
--   PRAGMA journal_mode = WAL;        -- one writer, concurrent readers
--   PRAGMA foreign_keys = ON;         -- enforced by validate harness
--   PRAGMA busy_timeout = 5000;       -- single-writer contention backoff
--   PRAGMA synchronous = NORMAL;      -- WAL durability vs ack budget (§F)
--
-- Rebuildability legend (DECISIONS.md: all indexes/caches rebuildable from the
-- Witness Spine + memory records):
--   [SPINE]      authoritative, never rebuilt (events, payload_store)
--   [INSTANCE]   instance-local authority, NOT rebuildable from spine
--                (actors — pairing ceremony; record_keys — crypto material;
--                 secrets_registry — salted refs; schema_migrations)
--   [REBUILDABLE] derived from spine events; may be dropped and rebuilt
--                (records, record_versions, edges, approvals, quarantine,
--                 handoffs, capsules, checkpoints, receipts, identity_links,
--                 embedding_cache, all FTS tables and indexes)
-- Enum spellings are pinned to schemas/event.schema.json and
-- schemas/memory-record.schema.json. Event field names match §G exactly.
-- ============================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- [INSTANCE] schema_migrations — migration ledger (DECISIONS.md §Q)
-- ----------------------------------------------------------------------------
CREATE TABLE schema_migrations (
    version      INTEGER PRIMARY KEY,
    applied_at   INTEGER NOT NULL,             -- unix ms
    description  TEXT    NOT NULL
);

-- ----------------------------------------------------------------------------
-- [INSTANCE] actors — pairing-created principals (wire-protocol.md §1/§3)
-- NOT rebuildable from spine: actor registration is the pairing ceremony.
-- kind 'system' (U-07): the well-known actor 'lamf-system' is created at
-- `lamf init` and authors autonomous events (checkpoint, spool_gap,
-- capture_dropped, TTL/lease sweeps), signed by the instance key.
-- ----------------------------------------------------------------------------
CREATE TABLE actors (
    actor_id     TEXT PRIMARY KEY,
    kind         TEXT NOT NULL CHECK (kind IN ('human', 'agent', 'operator', 'system')),
    public_key   BLOB NOT NULL,                -- Ed25519, 32 bytes
    token_sha256 TEXT UNIQUE,                  -- SHA-256(token); NULL after revoke
    scopes       TEXT NOT NULL DEFAULT '[]',   -- JSON array of scope strings
    created_at   INTEGER NOT NULL,             -- unix ms
    revoked_at   INTEGER,                      -- unix ms; NULL = active
    CHECK (token_sha256 IS NULL OR (length(token_sha256) = 64
         AND NOT (token_sha256 GLOB '*[^0-9a-f]*')))
);

-- ----------------------------------------------------------------------------
-- [INSTANCE] payload_store — encrypted payload blobs addressed by content hash
-- [SPINE-adjacent]: blobs are content-addressed evidence; crypto-shredded on
-- erasure (DECISIONS.md §L). Encrypted with per-record data keys (record_keys).
-- ----------------------------------------------------------------------------
CREATE TABLE payload_store (
    sha256       TEXT PRIMARY KEY
                 CHECK (length(sha256) = 64 AND NOT (sha256 GLOB '*[^0-9a-f]*')),
    blob_enc     BLOB NOT NULL,                -- AES-256-GCM ciphertext
    nonce        BLOB NOT NULL,                -- random 96-bit GCM nonce, unique per blob, never reused (U-08a)
    bytes        INTEGER NOT NULL CHECK (bytes >= 0),
    created_seq  INTEGER NOT NULL CHECK (created_seq >= 1)
);

-- ----------------------------------------------------------------------------
-- [SPINE] events — the Witness Spine. Append-only; never updated or deleted.
-- All §G fields; payload inline (canonical JSON text, ≤ 4 KiB) XOR by reference.
-- seq is the ordering authority (UNIQUE, strictly monotonic); ts advisory.
-- ----------------------------------------------------------------------------
CREATE TABLE events (
    id             TEXT NOT NULL UNIQUE,       -- UUIDv7
    seq            INTEGER NOT NULL UNIQUE CHECK (seq >= 1),
    ts             INTEGER NOT NULL,           -- unix ms; advisory only
    actor          TEXT NOT NULL REFERENCES actors(actor_id),
    session        TEXT,                       -- string | NULL
    type           TEXT NOT NULL CHECK (type IN (
                       'message', 'response', 'tool_call', 'tool_result',
                       'session_start', 'session_end', 'memory_request', 'handoff',
                       'policy_change', 'correction', 'failure', 'recovery',
                       'checkpoint', 'import', 'export', 'approval', 'quarantine',
                       'council_claim', 'council_objection', 'council_vote',
                       'council_decision', 'council_round_open',
                       'council_round_close',
                       'capture_dropped', 'spool_gap',
                       'identity_merge', 'identity_split', 'record_tombstoned',
                       'actor_pair', 'actor_revoke')),
    scope          TEXT NOT NULL,
    sensitivity    TEXT NOT NULL CHECK (sensitivity IN ('ordinary', 'sensitive', 'restricted')),
    taint          TEXT NOT NULL CHECK (taint IN ('user_direct', 'agent_generated',
                       'tool_output', 'external_content', 'system')),
    payload_json   TEXT,                       -- canonical JSON inline ≤ 4 KiB;
                                               -- a JSON null payload is stored as
                                               -- the 4-byte text 'null' (U-05),
                                               -- NEVER as SQL NULL: SQL NULL here
                                               -- unambiguously means "by reference"
    payload_ref    TEXT REFERENCES payload_store(sha256),
    payload_sha256 TEXT NOT NULL
                   CHECK (length(payload_sha256) = 64
                          AND NOT (payload_sha256 GLOB '*[^0-9a-f]*')),
    prev_hash      TEXT NOT NULL
                   CHECK (length(prev_hash) = 64 AND NOT (prev_hash GLOB '*[^0-9a-f]*')),
    hash           TEXT NOT NULL UNIQUE
                   CHECK (length(hash) = 64 AND NOT (hash GLOB '*[^0-9a-f]*')),
    sig            TEXT NOT NULL,              -- Ed25519 over raw hash bytes, base64url
    channel_json   TEXT,                       -- U-17: canonical JSON of the optional
                                               -- channel object {channel,
                                               -- channel_identity, thread} (T-channel-identity)
    sanitizer_note TEXT,                       -- U-15: optional sanitizer annotation
                                               -- (e.g. detector hit beyond stored bound)
    capture_sig    TEXT,                       -- U-04: optional hook-side Ed25519 sig
                                               -- at capture, base64url (spool-format.md §2)
    -- §G/U-05: payload (inline, possibly the canonical text 'null') XOR payload_ref
    CHECK ((payload_json IS NOT NULL AND payload_ref IS NULL)
        OR (payload_json IS NULL AND payload_ref IS NOT NULL)),
    -- U-08(b): sensitive/restricted events NEVER carry inline payload_json;
    -- they MUST reference an encrypted blob in payload_store
    CHECK (sensitivity = 'ordinary' OR payload_ref IS NOT NULL)
);

-- ----------------------------------------------------------------------------
-- [REBUILDABLE] records — current memory record heads (state-machines.md §1)
-- ----------------------------------------------------------------------------
CREATE TABLE records (
    id            TEXT PRIMARY KEY,
    type          TEXT NOT NULL CHECK (type IN (
                      'fact', 'preference', 'identity', 'relationship',
                      'decision', 'task', 'procedure', 'failure_lesson',
                      'episode', 'handoff_record', 'council_record')),
    title         TEXT NOT NULL,
    -- U-08(a): body is encrypted at the field level so per-record erasure
    -- (crypto-shredding the data key in record_keys) makes it unrecoverable.
    -- Construction: AES-256-GCM under the record's per-record data key;
    -- a random 96-bit nonce per message, NEVER reused under the same key,
    -- is prepended to the ciphertext: body_enc = nonce(12) || ct || tag(16).
    body_enc      BLOB NOT NULL,
    tags          TEXT NOT NULL DEFAULT '[]',  -- JSON array
    entities      TEXT NOT NULL DEFAULT '[]',  -- JSON array
    scope         TEXT NOT NULL,
    owner_actor   TEXT NOT NULL REFERENCES actors(actor_id),
    sensitivity   TEXT NOT NULL CHECK (sensitivity IN ('ordinary', 'sensitive', 'restricted')),
    taint         TEXT NOT NULL CHECK (taint IN ('user_direct', 'agent_generated',
                      'tool_output', 'external_content', 'system')),
    state         TEXT NOT NULL DEFAULT 'draft' CHECK (state IN (
                      'draft', 'active', 'superseded', 'contradicted',
                      'expired', 'tombstoned')),
    version       INTEGER NOT NULL CHECK (version >= 1),
    supersedes    TEXT REFERENCES records(id),
    source_events TEXT NOT NULL DEFAULT '[]',  -- JSON array of event ids (citations)
    confidence    TEXT NOT NULL DEFAULT 'medium'
                  CHECK (confidence IN ('low', 'medium', 'high')),  -- metadata only, NEVER authority (F5)
    created_seq   INTEGER NOT NULL CHECK (created_seq >= 1),
    updated_seq   INTEGER NOT NULL CHECK (updated_seq >= 1),
    expires_at    INTEGER                      -- unix ms; NULL = no expiry
);

-- ----------------------------------------------------------------------------
-- [REBUILDABLE] record_versions — immutable per-version snapshots
-- ----------------------------------------------------------------------------
CREATE TABLE record_versions (
    record_id   TEXT NOT NULL REFERENCES records(id),
    version     INTEGER NOT NULL CHECK (version >= 1),
    title       TEXT NOT NULL,
    body_enc    BLOB NOT NULL,                 -- U-08(a): same AES-256-GCM
                                               -- construction as records.body_enc
                                               -- (random 96-bit nonce per message,
                                               -- never reused)
    tags        TEXT NOT NULL DEFAULT '[]',
    entities    TEXT NOT NULL DEFAULT '[]',
    state       TEXT NOT NULL CHECK (state IN (
                    'draft', 'active', 'superseded', 'contradicted',
                    'expired', 'tombstoned')),
    sensitivity TEXT NOT NULL CHECK (sensitivity IN ('ordinary', 'sensitive', 'restricted')),
    taint       TEXT NOT NULL CHECK (taint IN ('user_direct', 'agent_generated',
                    'tool_output', 'external_content', 'system')),
    changed_seq INTEGER NOT NULL CHECK (changed_seq >= 1),
    PRIMARY KEY (record_id, version)
);

-- ----------------------------------------------------------------------------
-- [REBUILDABLE] edges — memory graph adjacency
-- ----------------------------------------------------------------------------
CREATE TABLE edges (
    src_record  TEXT NOT NULL REFERENCES records(id),
    dst_record  TEXT NOT NULL REFERENCES records(id),
    type        TEXT NOT NULL CHECK (type IN (
                    'supports', 'contradicts', 'supersedes',
                    'depends_on', 'belongs_to', 'related_to')),
    created_seq INTEGER NOT NULL CHECK (created_seq >= 1),
    PRIMARY KEY (src_record, dst_record, type)
);

-- ----------------------------------------------------------------------------
-- [REBUILDABLE] approvals — pending → {approved, denied, expired} (§J)
-- timeout = deny; every transition receipted (F8)
-- ----------------------------------------------------------------------------
CREATE TABLE approvals (
    id           TEXT PRIMARY KEY,
    kind         TEXT NOT NULL CHECK (kind IN (
                     'capture_sensitive', 'cross_scope_read', 'deletion',
                     'promotion', 'cross_agent_read', 'step_up')),  -- step_up (U-14):
                     -- a fresh (≤ 5 min) operator-credential assertion, recorded
                     -- as an approval event of kind step_up (T-step-up-receipt)
    requester    TEXT NOT NULL REFERENCES actors(actor_id),
    scope        TEXT NOT NULL,
    sensitivity  TEXT NOT NULL CHECK (sensitivity IN ('ordinary', 'sensitive', 'restricted')),
    summary      TEXT NOT NULL,
    state        TEXT NOT NULL DEFAULT 'pending'
                 CHECK (state IN ('pending', 'approved', 'denied', 'expired')),
    reason       TEXT,
    created_at   INTEGER NOT NULL,             -- unix ms
    expires_at   INTEGER NOT NULL,             -- created_at + approvals.ttl_hours
    decided_at   INTEGER,
    decided_by   TEXT REFERENCES actors(actor_id),
    receipt_id   TEXT REFERENCES receipts(receipt_id)  -- U-17 (V1-22)
);

-- ----------------------------------------------------------------------------
-- [REBUILDABLE] quarantine — quarantined → {ingested, purged, expired→purged}
-- encrypted at rest (payload via payload_store), excluded from search & export
-- ----------------------------------------------------------------------------
CREATE TABLE quarantine (
    id              TEXT PRIMARY KEY,
    source_event_id TEXT,                      -- originating event id, if any
    reason          TEXT NOT NULL,             -- e.g. capture.sensitive=quarantine, replay_anomaly
    state           TEXT NOT NULL DEFAULT 'quarantined'
                    CHECK (state IN ('quarantined', 'ingested', 'purged', 'expired')),
    scope           TEXT NOT NULL,
    sensitivity     TEXT NOT NULL CHECK (sensitivity IN ('ordinary', 'sensitive', 'restricted')),
    taint           TEXT NOT NULL CHECK (taint IN ('user_direct', 'agent_generated',
                        'tool_output', 'external_content', 'system')),
    payload_ref     TEXT REFERENCES payload_store(sha256),
    created_at      INTEGER NOT NULL,          -- unix ms
    expires_at      INTEGER NOT NULL,          -- created_at + quarantine.ttl_days
    decided_by      TEXT REFERENCES actors(actor_id),
    decided_at      INTEGER
);

-- ----------------------------------------------------------------------------
-- [REBUILDABLE] handoffs — offered → {accepted, cancelled, expired};
-- accepted → {completed, released, failed}; lease TTL 30 min; fencing (§J)
-- ----------------------------------------------------------------------------
CREATE TABLE handoffs (
    id            TEXT PRIMARY KEY,
    work_item     TEXT NOT NULL,               -- canonical JSON {summary, scope, ...}
    scope         TEXT NOT NULL,
    offerer       TEXT NOT NULL REFERENCES actors(actor_id),
    state         TEXT NOT NULL DEFAULT 'offered' CHECK (state IN (
                      'offered', 'accepted', 'cancelled', 'expired',
                      'completed', 'released', 'failed')),
    fencing_token INTEGER NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
    holder        TEXT REFERENCES actors(actor_id),
    lease_expires INTEGER,                     -- unix ms; 30 min lease, renewable
    created_at    INTEGER NOT NULL,
    updated_at    INTEGER NOT NULL,
    result        TEXT                         -- completion metadata (JSON)
);
-- Accept-once is enforced transactionally by the ingester:
--   UPDATE handoffs SET state='accepted', holder=?, fencing_token=fencing_token+1,
--          lease_expires=? WHERE id=? AND state='offered';
-- rowcount==1 wins; rowcount==0 loses (conflict). Fencing tokens are strictly
-- monotonic; stale-token complete/release MUST fail.

-- ----------------------------------------------------------------------------
-- [REBUILDABLE] capsules — compiled context capsules (state-machines.md §5)
-- validity key = (policy_version, scope_set, record_watermark); stale never served
-- ----------------------------------------------------------------------------
CREATE TABLE capsules (
    id               TEXT PRIMARY KEY,
    kind             TEXT NOT NULL DEFAULT 'context'
                     CHECK (kind IN ('context', 'orientation')),
    policy_version   INTEGER NOT NULL CHECK (policy_version >= 1),
    scope_set        TEXT NOT NULL,            -- canonical JSON array of scopes
    record_watermark INTEGER NOT NULL CHECK (record_watermark >= 0),
    purpose          TEXT NOT NULL,
    body_enc         BLOB NOT NULL,            -- compiled capsule, encrypted at rest
    token_count      INTEGER NOT NULL CHECK (token_count >= 0),
    compiled_at_seq  INTEGER NOT NULL CHECK (compiled_at_seq >= 1),
    stale            INTEGER NOT NULL DEFAULT 0 CHECK (stale IN (0, 1)),
    created_at       INTEGER NOT NULL
);
-- Invalidation (§N): supersession/tombstone/contradiction/expiry/quarantine and
-- ANY policy event set stale=1 for affected rows synchronously, inside the
-- committing transaction.

-- ----------------------------------------------------------------------------
-- [REBUILDABLE] checkpoints — sealed chain checkpoints (DECISIONS.md §H)
-- every 1,000 events OR 24 h; startup verifies latest row + bounded tail only
-- ----------------------------------------------------------------------------
CREATE TABLE checkpoints (
    id              INTEGER PRIMARY KEY,
    seq_hi          INTEGER NOT NULL UNIQUE CHECK (seq_hi >= 1),
    chain_head_hash TEXT NOT NULL
                    CHECK (length(chain_head_hash) = 64
                           AND NOT (chain_head_hash GLOB '*[^0-9a-f]*')),
    event_count     INTEGER NOT NULL CHECK (event_count >= 0),
    instance_sig    TEXT NOT NULL,             -- instance Ed25519 sig, base64url
    created_at      INTEGER NOT NULL           -- unix ms
);

-- ----------------------------------------------------------------------------
-- [REBUILDABLE] receipts — read/decision receipts (floor F10 itemization)
-- U-08(f): items carry ids + content hashes ONLY (never titles/bodies);
-- receipts are operator-read-only and EXCLUDED from export bundles.
-- ----------------------------------------------------------------------------
CREATE TABLE receipts (
    receipt_id TEXT PRIMARY KEY,               -- U-17: PK name pinned for FK targets
    actor      TEXT NOT NULL REFERENCES actors(actor_id),
    action     TEXT NOT NULL,                  -- e.g. read, approve, export, purge
    subject    TEXT NOT NULL,                  -- record/approval/export id
    items      TEXT,                           -- JSON [{id, sha256}, ...] ids+hashes
                                               -- only (NULL = aggregate ordinary
                                               -- read only, F10)
    event_seq  INTEGER,                        -- spine seq of the receipted action
    created_at INTEGER NOT NULL                -- unix ms
);

-- ----------------------------------------------------------------------------
-- [REBUILDABLE] identity_links — cross-channel identity merge state (§J, F6)
-- proposed → {confirmed→merged, rejected}; merged → split (receipted)
-- U-06: uniqueness applies ONLY to the 'proposed' state (partial unique index
-- below) — a rejected/split link may be re-proposed; history is append-only rows.
-- ----------------------------------------------------------------------------
CREATE TABLE identity_links (
    id                TEXT PRIMARY KEY,
    actor_id          TEXT NOT NULL REFERENCES actors(actor_id),
    channel           TEXT NOT NULL,           -- e.g. telegram, slack, cli
    channel_identity  TEXT NOT NULL,           -- identity as seen on that channel
    state             TEXT NOT NULL DEFAULT 'proposed'
                      CHECK (state IN ('proposed', 'merged', 'rejected', 'split')),
    proof             TEXT,                    -- strong-id proof reference (F6 glossary)
    created_seq       INTEGER NOT NULL CHECK (created_seq >= 1),
    decided_seq       INTEGER,
    receipt_id        TEXT REFERENCES receipts(receipt_id)  -- U-17 (V1-22)
);

-- ----------------------------------------------------------------------------
-- [INSTANCE] secrets_registry — operator-registered secret values (U-15) and
-- salted-hash secret REFERENCES (§M.7). Values are stored ONLY as value_enc
-- (AES-256-GCM under the instance key, random 96-bit nonce per registration,
-- nonce prepended) with a random per-value salt and value_len for bounded
-- in-memory matching; plaintext is decrypted into memory at service start for
-- exact-substring matching and is NEVER logged, spooled, or exported.
-- ref_name_salted_hash remains for display/export (values never export, §M.7);
-- needs_rebind drives the import rebind step (§M.3/§M.6).
-- ----------------------------------------------------------------------------
CREATE TABLE secrets_registry (
    id                  TEXT PRIMARY KEY,
    ref_name_salted_hash TEXT NOT NULL UNIQUE, -- salted hash of the reference name
    value_enc           BLOB,                  -- secret value encrypted under the
                                               -- instance key (U-15); NULL for
                                               -- imported refs awaiting rebind
    salt                BLOB,                  -- random per-value salt (U-15)
    value_len           INTEGER CHECK (value_len >= 0),  -- plaintext length (U-15)
    needs_rebind        INTEGER NOT NULL DEFAULT 0 CHECK (needs_rebind IN (0, 1)),
    registered_by       TEXT REFERENCES actors(actor_id),
    created_at          INTEGER NOT NULL,
    rebound_at          INTEGER
);

-- ----------------------------------------------------------------------------
-- [INSTANCE] record_keys — per-record wrapped data keys (crypto-shredding, §L/F7)
-- AES-256-GCM data key wrapped by the instance key (envelope encryption).
-- Erasure = tombstone record + destroy this row's key + record_tombstoned event.
-- U-08(g): rows ALSO serve quarantine items — the owner id is polymorphic
-- (records.id OR quarantine.id), so no FK is declared; ownership is enforced by
-- the ingester. Quarantine purge shreds the item's key + payload blob.
-- ----------------------------------------------------------------------------
CREATE TABLE record_keys (
    -- Ownership: record_id may name a records.id, a quarantine.id (U-08g),
    -- OR an events.id — event payloads referenced by non-ordinary events
    -- (U-08b) are encrypted under a per-owner data key held here, so
    -- crypto-shredding the key erases the event payload blob as well.
    record_id    TEXT PRIMARY KEY,             -- owner id: records.id OR quarantine.id (U-08g) OR events.id (U-08b)
    wrapped_key  BLOB NOT NULL,                -- data key wrapped by instance key
    alg          TEXT NOT NULL DEFAULT 'AES-256-GCM',
    created_seq  INTEGER NOT NULL CHECK (created_seq >= 1),
    destroyed_at INTEGER                       -- unix ms; set = crypto-shredded
);

-- ----------------------------------------------------------------------------
-- [REBUILDABLE] embedding_cache — optional local vectors (INDEXING_AND_SEARCH.md)
-- key = model ID + canonical text hash; provider/model change invalidates only
-- affected rows; system remains fully functional with this table empty
-- ----------------------------------------------------------------------------
CREATE TABLE embedding_cache (
    model_id    TEXT NOT NULL,
    source_hash TEXT NOT NULL,                 -- hash of canonical chunk text
    record_id   TEXT REFERENCES records(id),   -- U-08(d): owning record for
                                               -- tombstone purge; NULL only for
                                               -- non-record embeddings — record
                                               -- embeddings MUST set it
    dim         INTEGER NOT NULL CHECK (dim > 0),
    version     INTEGER NOT NULL CHECK (version >= 1),  -- embedding generation version
    vector      BLOB NOT NULL,                 -- float32[dims], little-endian
    created_at  INTEGER NOT NULL,
    PRIMARY KEY (model_id, source_hash, version)
);

-- ----------------------------------------------------------------------------
-- Indexes — [REBUILDABLE] candidate generators (§N: never authority)
-- scope / owner / type / sensitivity / state / time coverage
-- ----------------------------------------------------------------------------
CREATE INDEX idx_events_scope          ON events(scope);
CREATE INDEX idx_events_actor          ON events(actor);
CREATE INDEX idx_events_type           ON events(type);
CREATE INDEX idx_events_sensitivity    ON events(sensitivity);
CREATE INDEX idx_events_session        ON events(session);
CREATE INDEX idx_events_ts             ON events(ts);
CREATE INDEX idx_events_scope_ts       ON events(scope, ts);

CREATE INDEX idx_records_scope         ON records(scope);
CREATE INDEX idx_records_owner         ON records(owner_actor);
CREATE INDEX idx_records_type          ON records(type);
CREATE INDEX idx_records_sensitivity   ON records(sensitivity);
CREATE INDEX idx_records_state         ON records(state);
CREATE INDEX idx_records_updated_seq   ON records(updated_seq);
CREATE INDEX idx_records_expires_at    ON records(expires_at);
CREATE INDEX idx_records_supersedes    ON records(supersedes);

CREATE INDEX idx_edges_dst             ON edges(dst_record);
CREATE INDEX idx_edges_type            ON edges(type);

CREATE INDEX idx_approvals_state       ON approvals(state);
CREATE INDEX idx_approvals_requester   ON approvals(requester);
CREATE INDEX idx_quarantine_state      ON quarantine(state);
CREATE INDEX idx_handoffs_state        ON handoffs(state);
CREATE INDEX idx_handoffs_scope        ON handoffs(scope, state);
CREATE INDEX idx_capsules_key          ON capsules(policy_version, record_watermark, stale);
CREATE INDEX idx_receipts_actor        ON receipts(actor, created_at);
CREATE INDEX idx_identity_links_actor  ON identity_links(actor_id, state);
-- U-06: at most one PROPOSED link per (actor, channel, channel_identity);
-- decided links (merged/rejected/split) never block re-proposal.
CREATE UNIQUE INDEX idx_identity_links_one_proposed
    ON identity_links(actor_id, channel, channel_identity)
    WHERE state = 'proposed';
CREATE INDEX idx_embedding_cache_record ON embedding_cache(record_id);  -- U-08(d)

-- ----------------------------------------------------------------------------
-- [INSTANCE] instance_identity — the instance key's public half (U-13a)
-- Created at `lamf init`; the private part lives in the OS keychain or a 0600
-- file and is NEVER exported. Import anchors checkpoint verification on this
-- pubkey (pinned in the export manifest) + operator out-of-band fingerprint
-- confirmation (T-instance-key-anchored). Single row.
-- ----------------------------------------------------------------------------
CREATE TABLE instance_identity (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    pubkey      TEXT NOT NULL,                 -- instance Ed25519 public key, base64url
    fingerprint TEXT NOT NULL,                 -- display fingerprint (out-of-band confirm)
    created_at  INTEGER NOT NULL               -- unix ms
);

-- ----------------------------------------------------------------------------
-- [REBUILDABLE] ingester_state — spool-replay high-water mark (U-17, V1-23)
-- Single row. The ingester's durable watermark: highest spine seq assigned from
-- spool replay; drives incremental indexing and the spool_gap drop window.
-- ----------------------------------------------------------------------------
CREATE TABLE ingester_state (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    high_water_seq INTEGER NOT NULL DEFAULT 0 CHECK (high_water_seq >= 0),
    updated_ts    INTEGER NOT NULL             -- unix ms
);

-- ----------------------------------------------------------------------------
-- [REBUILDABLE] policy_state — committed policy head (U-12, V2-21)
-- Single row, updated transactionally on `lamf security apply`. version =
-- count of policy_change spine events (capsule validity key part);
-- updated_seq = spine seq of the last policy_change. Capsule serve-time
-- re-check compares against THIS committed head (never a WAL reader snapshot).
-- ----------------------------------------------------------------------------
CREATE TABLE policy_state (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    version     INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    updated_seq INTEGER NOT NULL DEFAULT 0 CHECK (updated_seq >= 0)
);

-- ----------------------------------------------------------------------------
-- [REBUILDABLE] FTS5 full-text indexes — droppable and rebuildable at any time.
-- U-02/U-08 layout:
--   * events_fts is CONTENTLESS (content=''); triggers own ALL sync. Because
--     U-08(b) forces sensitive/restricted payloads into encrypted payload_ref
--     blobs, events_fts only ever indexes ordinary inline payload text.
--   * records_fts stores its own content (no external-content table): records
--     .body is now body_enc (AES-256-GCM, U-08a), so SQL triggers cannot index
--     the body. The INGESTER (which holds the per-record data key inside the
--     write transaction) owns records_fts row INSERT/refresh; SQL triggers own
--     the DELETE paths so erasure can never leave FTS residue (U-08c). An FTS
--     index inherently contains searchable terms, which is exactly why the
--     tombstone-purge triggers below are mandatory.
-- ----------------------------------------------------------------------------

-- records_fts: app-maintained inserts; trigger-maintained deletes.
CREATE VIRTUAL TABLE records_fts USING fts5(
    title, body, tags, entities,
    tokenize = 'unicode61'
);

-- Row deletion always drops the FTS row.
CREATE TRIGGER records_fts_ad AFTER DELETE ON records BEGIN
    DELETE FROM records_fts WHERE rowid = old.rowid;
END;
-- U-08(c) purge-on-tombstone: the moment a record is tombstoned its FTS row is
-- removed, so crypto-shredded content is never searchable.
CREATE TRIGGER records_fts_purge_tombstone
AFTER UPDATE OF state ON records WHEN new.state = 'tombstoned' BEGIN
    DELETE FROM records_fts WHERE rowid = old.rowid;
END;
-- U-08(d): tombstone also purges the record's cached embeddings.
CREATE TRIGGER embedding_cache_purge_tombstone
AFTER UPDATE OF state ON records WHEN new.state = 'tombstoned' BEGIN
    DELETE FROM embedding_cache WHERE record_id = old.id;
END;
-- records_fts insert/refresh (ingester, same write transaction as the record
-- write, body decrypted with the record's data key):
--   DELETE FROM records_fts WHERE rowid = :rowid;   -- refresh path
--   INSERT INTO records_fts(rowid, title, body, tags, entities)
--   VALUES (:rowid, :title, :body_plaintext, :tags, :entities);
-- records_fts rebuild: DELETE FROM records_fts; then the ingester re-indexes
-- every non-tombstoned record from decrypted content (requires data keys, so
-- repopulation is application-side, not a SQL statement).

CREATE VIRTUAL TABLE events_fts USING fts5(
    payload_text, actor, type, scope, session,
    content = '',
    tokenize = 'unicode61'
);

CREATE TRIGGER events_fts_ai AFTER INSERT ON events BEGIN
    INSERT INTO events_fts(rowid, payload_text, actor, type, scope, session)
    VALUES (new.rowid, coalesce(new.payload_json, ''), new.actor, new.type,
            new.scope, coalesce(new.session, ''));
END;
-- events are append-only: no UPDATE/DELETE triggers by design (F9).
-- U-02 documented events_fts rebuild — DELETE + INSERT..SELECT (one
-- transaction). NOTE: SQLite forbids `DELETE FROM` on a contentless FTS5
-- table before 3.43's contentless_delete option, so the portable form of the
-- pinned "DELETE FROM events_fts" step is the FTS5 delete-all command:
--   INSERT INTO events_fts(events_fts) VALUES('delete-all');
--   INSERT INTO events_fts(rowid, payload_text, actor, type, scope, session)
--   SELECT rowid, coalesce(payload_json, ''), actor, type, scope,
--          coalesce(session, '') FROM events;
-- (Same wipe+repopulate semantics as U-02's DELETE+INSERT..SELECT.)

-- ----------------------------------------------------------------------------
-- Migration head
-- ----------------------------------------------------------------------------
INSERT INTO schema_migrations (version, applied_at, description)
VALUES (1, 0, 'LAMF 2.0.0 base schema (DECISIONS.md §A/§G/§H/§J/§L/§N + §U Round-2)');

-- Single-row state seeds (U-17): the ingester watermark starts at 0 and the
-- policy head at version 1 (init policy, no policy_change events yet).
INSERT INTO ingester_state (id, high_water_seq, updated_ts) VALUES (1, 0, 0);
INSERT INTO policy_state (id, version, updated_seq) VALUES (1, 1, 0);
