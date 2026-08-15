"""LAMF SQLite store — executes 04_STORAGE/SCHEMA.sql as-is (W-02).

Wraps the validator-proven schema: events (spine mirror + contentless
events_fts), records/record_versions with field-level encrypted bodies,
content-addressed payload_store, per-owner wrapped data keys (record_keys),
approvals, checkpoints, ingester_state, policy_state.

Envelope encryption (DECISIONS.md §L/U-08, U-13a):
  * per-owner random 256-bit data key, wrapped to the instance key's X25519
    counterpart (crypto.InstanceKey.wrap_key); erasure = destroy the
    record_keys row (crypto-shredding, F7) — implemented by the api layer,
    the primitives live here.
  * DEVIATION (documented): SCHEMA.sql's comments describe AES-256-GCM, but
    the pinned dependency set (pyyaml + pynacl, W-02) has no AES-GCM. The
    reference runtime substitutes XChaCha20-Poly1305 (also AEAD, also random
    nonce per message, never reused): body_enc = nonce(24) || ct || tag(16)
    and record_keys.alg = 'XChaCha20-Poly1305'. Erasure semantics (shred the
    wrapped key) are identical. Interop with an AES-GCM implementation
    requires reading record_keys.alg.

Pinned interface (runtime/README.md):
    Store.open(db_path, schema_path='04_STORAGE/SCHEMA.sql') -> Store
    .upsert_record(rec: dict) -> str
    .supersede(record_id, new_rec: dict, reason: str) -> str
    .get_record(record_id, include_history=False) -> dict
    .search_fts(query, limit=20, filters=None) -> list[dict]
    .stats() -> dict
    .close()
Additional storage primitives used by ingest/api: insert_event, put_payload,
get_payload, ensure_actor, set_high_water, list_approvals, decide_approval.
"""

from __future__ import annotations

import json
import base64
import hashlib
import hmac
import os
import re
import sqlite3
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import canon
from .crypto import InstanceKey

_DATA_KEY_BYTES = 32
_AEAD_NONCE_BYTES = 24          # XChaCha20-Poly1305 (see module docstring)
_AEAD_ALG = "XChaCha20-Poly1305"

# memory-record.schema.json enums (write-side validation; the DB CHECKs pin
# the same domains)
RECORD_TYPES = ("fact", "preference", "identity", "relationship", "decision",
                "task", "procedure", "failure_lesson", "episode",
                "handoff_record", "council_record")
SENSITIVITIES = ("ordinary", "sensitive", "restricted")
TAINTS = ("user_direct", "agent_generated", "tool_output", "external_content", "system")
RECORD_STATES = ("draft", "active", "superseded", "contradicted", "expired", "tombstoned")
CONFIDENCES = ("low", "medium", "high")
_QUERY_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "for", "from", "how",
    "in", "is", "it", "of", "on", "or", "plan", "planning", "project",
    "projects", "the", "this", "to", "what", "with",
})
_BLIND_TOKEN_HEX_CHARS = 24  # 96 keyed bits; collision floor exceeds record-id UUIDs
_BLIND_TOKEN_CACHE_MAX = 65536


def natural_index_words(value: str) -> list[str]:
    """Normalize the complete token stream for keyed contentless FTS."""
    value = unicodedata.normalize("NFKC", str(value or ""))
    return [word.casefold() for word in
            re.findall(r"[^\W_]+", value, flags=re.UNICODE)]


def natural_search_terms(query: str) -> list[str]:
    """Normalize a query into bounded blind-index terms."""
    query = unicodedata.normalize("NFKC", str(query or ""))
    words = re.findall(r"[^\W_]+", str(query or ""), flags=re.UNICODE)
    useful = []
    for word in words:
        folded = word.casefold()
        if len(folded) < 2 or folded in _QUERY_STOPWORDS or folded in useful:
            continue
        useful.append(folded)
    if not useful:
        useful = [w.casefold() for w in words if len(w) >= 2]
    return useful[:24]


class StoreError(Exception):
    pass


class MigrationRequired(StoreError):
    """Raised when a protocol-2 database needs the explicit v3 migration."""


def _now_ms() -> int:
    return int(time.time() * 1000)


def _resolve_schema_path(schema_path: str) -> Path:
    p = Path(schema_path)
    if p.is_absolute() and p.exists():
        return p
    # package root is parents[2] of runtime/lamf/store.py
    candidate = Path(__file__).resolve().parents[2] / schema_path
    if candidate.exists():
        return candidate
    if p.exists():
        return p
    raise FileNotFoundError(f"schema not found: {schema_path}")


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def needs_protocol3_migration(db_path) -> bool:
    """Return whether an initialized database still uses plaintext metadata."""
    path = Path(db_path)
    if not path.exists() or path.stat().st_size == 0:
        return False
    conn = sqlite3.connect(str(path))
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        return "records" in tables and "metadata_enc" not in _column_names(conn, "records")
    finally:
        conn.close()


def migrate_protocol3(db_path, instance_key: InstanceKey, backup_path=None) -> Path:
    """Atomically migrate a protocol-2 database to encrypted metadata/search.

    A verified SQLite backup is created before any schema or data mutation.
    The instance key is reused so existing encrypted bodies and wrapped record
    keys remain valid. The function is idempotent for an already-v3 database.
    """
    db_path = Path(db_path)
    if not needs_protocol3_migration(db_path):
        return Path(backup_path) if backup_path else db_path
    if instance_key is None:
        raise StoreError("protocol-3 migration requires the instance key")
    backup = Path(backup_path) if backup_path else db_path.with_name(
        f"{db_path.name}.pre-v3.{_now_ms()}.sqlite")
    if backup.exists():
        raise StoreError(f"migration backup already exists: {backup}")
    backup.parent.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(str(db_path))
    target = sqlite3.connect(str(backup))
    try:
        source.backup(target)
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise StoreError("pre-migration backup failed integrity_check")
    finally:
        target.close()
        source.close()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    store = Store(conn, db_path, instance_key)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ALTER TABLE records ADD COLUMN metadata_enc BLOB")
        conn.execute("ALTER TABLE record_versions ADD COLUMN metadata_enc BLOB")
        conn.execute("DROP TABLE IF EXISTS records_fts")
        conn.execute("""CREATE VIRTUAL TABLE record_search_fts USING fts5(
            title, body, tags, entities, content='',
            tokenize='unicode61')""")

        rows = conn.execute("SELECT * FROM records").fetchall()
        for row in rows:
            data_key = store._data_key_for(row["id"])
            tags = json.loads(row["tags"] or "[]")
            entities = json.loads(row["entities"] or "[]")
            metadata = json.dumps({"title": row["title"], "tags": tags,
                                   "entities": entities}, ensure_ascii=False,
                                  separators=(",", ":")).encode("utf-8")
            metadata_enc = store._aead_encrypt(data_key, metadata)
            body = store._aead_decrypt(data_key, row["body_enc"]).decode("utf-8")
            conn.execute("UPDATE records SET title='[encrypted]', tags='[]', "
                         "entities='[]', metadata_enc=? WHERE id=?",
                         (metadata_enc, row["id"]))
            if row["state"] != "tombstoned":
                store._search_refresh(row["id"], row["title"], body, tags, entities)

        versions = conn.execute("SELECT * FROM record_versions").fetchall()
        for row in versions:
            data_key = store._data_key_for(row["record_id"])
            metadata = json.dumps({
                "title": row["title"],
                "tags": json.loads(row["tags"] or "[]"),
                "entities": json.loads(row["entities"] or "[]"),
            }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            conn.execute("UPDATE record_versions SET title='[encrypted]', tags='[]', "
                         "entities='[]', metadata_enc=? WHERE record_id=? AND version=?",
                         (store._aead_encrypt(data_key, metadata), row["record_id"],
                          row["version"]))
        nulls = conn.execute("SELECT COUNT(*) FROM records WHERE metadata_enc IS NULL").fetchone()[0]
        nulls += conn.execute(
            "SELECT COUNT(*) FROM record_versions WHERE metadata_enc IS NULL").fetchone()[0]
        if nulls:
            raise StoreError("protocol-3 migration left unencrypted metadata")
        conn.execute("INSERT OR REPLACE INTO schema_migrations "
                     "(version, applied_at, description) VALUES (3, ?, ?)",
                     (_now_ms(), "protocol 3 encrypted metadata and keyed FTS"))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return backup


def needs_keyed_fts_migration(db_path) -> bool:
    """Return whether an encrypted protocol-3 store uses the legacy term table."""
    path = Path(db_path)
    if not path.exists() or path.stat().st_size == 0:
        return False
    conn = sqlite3.connect(str(path))
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        return ("records" in tables and "metadata_enc" in _column_names(conn, "records")
                and "record_search_fts" not in tables)
    finally:
        conn.close()


def migrate_keyed_fts(db_path, instance_key: InstanceKey, backup_path=None) -> Path:
    """Back up and replace the legacy blind-term table with keyed FTS5."""
    db_path = Path(db_path)
    if not needs_keyed_fts_migration(db_path):
        return Path(backup_path) if backup_path else db_path
    if instance_key is None:
        raise StoreError("keyed-FTS migration requires the instance key")
    backup = Path(backup_path) if backup_path else db_path.with_name(
        f"{db_path.name}.pre-keyed-fts.{_now_ms()}.sqlite")
    if backup.exists():
        raise StoreError(f"migration backup already exists: {backup}")
    backup.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(db_path))
    target = sqlite3.connect(str(backup))
    try:
        source.backup(target)
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise StoreError("pre-migration backup failed integrity_check")
    finally:
        target.close()
        source.close()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    store = Store(conn, db_path, instance_key)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""CREATE VIRTUAL TABLE record_search_fts USING fts5(
            title, body, tags, entities, content='',
            tokenize='unicode61')""")
        for row in conn.execute("SELECT * FROM records").fetchall():
            if row["state"] == "tombstoned":
                continue
            public = store._row_to_record(row)
            store._search_refresh(row["id"], public["title"], public["body"],
                                  public["tags"], public["entities"])
        conn.execute("DROP TRIGGER IF EXISTS record_search_terms_purge_tombstone")
        conn.execute("DROP TABLE IF EXISTS record_search_terms")
        conn.execute("INSERT OR REPLACE INTO schema_migrations "
                     "(version, applied_at, description) VALUES (4, ?, ?)",
                     (_now_ms(), "contentless keyed FTS5 search index"))
        conn.commit()
        # Reclaim pages formerly owned by the legacy term table. The verified
        # backup above remains the rollback boundary if compaction is interrupted.
        conn.execute("VACUUM")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return backup


class Store:
    # -- lifecycle -----------------------------------------------------------
    @classmethod
    def open(cls, db_path, schema_path: str = "04_STORAGE/SCHEMA.sql",
             instance_key: Optional[InstanceKey] = None) -> "Store":
        """Open (creating + migrating if fresh) the LAMF database. PINNED.

        instance_key: explicit InstanceKey, or None to auto-load
        <db_dir>/instance.key (the `lamf init` layout). Required for any
        operation that encrypts/decrypts (records, payloads); absent it,
        those operations fail closed.
        """
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        fresh = not db_path.exists() or db_path.stat().st_size == 0
        # check_same_thread=False: the HTTP layer serves from handler threads;
        # callers must serialize writes (WAL + single-writer discipline upstream).
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA synchronous = NORMAL")
        has_schema = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        # journal_mode=DELETE pinned: WAL needs mmap semantics that Windows-drive
        # mounts in WSL (drvfs/9p, e.g. /mnt/y) do not reliably provide. The mode
        # persists in the db header, so it only has to be set once, at creation —
        # later opens inherit it. For pre-existing dbs we try best-effort: a
        # concurrent reader makes journal-mode changes fail with SQLITE_BUSY
        # regardless of busy_timeout, and that is fine (persisted mode applies).
        if fresh or not has_schema:
            conn.execute("PRAGMA journal_mode = DELETE")
            sql = _resolve_schema_path(schema_path).read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.commit()
        else:
            try:
                conn.execute("PRAGMA journal_mode = DELETE")
            except sqlite3.OperationalError:
                pass
            if "metadata_enc" not in _column_names(conn, "records"):
                conn.close()
                raise MigrationRequired(
                    f"protocol-2 database at {db_path} requires explicit "
                    "`lamf migrate-v3 --data-dir ...` before use")
            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
            if "record_search_fts" not in tables:
                conn.close()
                raise MigrationRequired(
                    f"protocol-3 database at {db_path} requires explicit "
                    "`lamf migrate-v3 --data-dir ...` to build keyed FTS")
        if instance_key is None:
            key_path = db_path.parent / "instance.key"
            if key_path.exists():
                instance_key = InstanceKey.load(key_path)
        store = cls(conn, db_path, instance_key)
        if instance_key is not None:
            store.ensure_search_index()
        return store

    def __init__(self, conn: sqlite3.Connection, db_path: Path,
                 instance_key: Optional[InstanceKey]):
        self.conn = conn
        self.db_path = db_path
        self.key = instance_key
        self._blind_token_cache: Dict[str, str] = {}

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- crypto helpers -------------------------------------------------------
    def _require_key(self) -> InstanceKey:
        if self.key is None:
            raise StoreError("operation requires the instance key (encrypted at rest)")
        return self.key

    def _new_data_key(self, owner_id: str, created_seq: int) -> bytes:
        """Create + wrap a fresh data key for an owner id (records.id,
        quarantine.id or events.id — V-07). Returns the plaintext data key
        (lives only in memory for the duration of the write)."""
        key = self._require_key()
        data_key = os.urandom(_DATA_KEY_BYTES)
        import nacl.bindings  # local import: keep module import cheap
        wrapped = key.wrap_key(data_key)
        self.conn.execute(
            "INSERT INTO record_keys (record_id, wrapped_key, alg, created_seq)"
            " VALUES (?, ?, ?, ?)",
            (owner_id, wrapped, _AEAD_ALG, created_seq))
        return data_key

    def _data_key_for(self, owner_id: str) -> bytes:
        row = self.conn.execute(
            "SELECT wrapped_key, destroyed_at FROM record_keys WHERE record_id = ?",
            (owner_id,)).fetchone()
        if row is None:
            raise StoreError(f"no data key for {owner_id}")
        if row["destroyed_at"] is not None:
            raise StoreError(f"data key for {owner_id} is crypto-shredded (F7 erasure)")
        return self._require_key().unwrap_key(row["wrapped_key"])

    @staticmethod
    def _aead_encrypt(data_key: bytes, plaintext: bytes) -> bytes:
        import nacl.bindings
        nonce = os.urandom(_AEAD_NONCE_BYTES)
        ct = nacl.bindings.crypto_aead_xchacha20poly1305_ietf_encrypt(
            plaintext, None, nonce, data_key)
        return nonce + ct

    @staticmethod
    def _aead_decrypt(data_key: bytes, blob: bytes) -> bytes:
        import nacl.bindings
        nonce, ct = blob[:_AEAD_NONCE_BYTES], blob[_AEAD_NONCE_BYTES:]
        return nacl.bindings.crypto_aead_xchacha20poly1305_ietf_decrypt(
            ct, None, nonce, data_key)

    # -- spine mirror ---------------------------------------------------------
    def head_seq(self) -> int:
        row = self.conn.execute("SELECT COALESCE(MAX(seq), 0) AS s FROM events").fetchone()
        return int(row["s"])

    def insert_event(self, ev: Dict[str, Any]) -> None:
        """Mirror a finalized spine event into SQLite (ingester step).
        The events_fts sync trigger fires automatically (SCHEMA.sql).
        Updates the ingester high-water mark transactionally (U-17).

        Exact retries are idempotent.  This matters because the Witness Spine
        is authoritative and durable before its rebuildable SQLite mirror is
        advanced: after a crash, or when two local MCP processes race to
        reconcile the same tail event, replaying the same finalized event must
        succeed without weakening conflict detection.
        """
        payload_json = ev.get("payload_json", None)
        if payload_json is None and "payload" in ev:
            # canonical inline text; a JSON null payload is the text 'null' (U-05)
            payload_json = canon.canonicalize(ev["payload"])
        channel_json = ev.get("channel_json")
        if channel_json is None and ev.get("channel") is not None:
            channel_json = canon.canonicalize(ev["channel"])
        values = (ev["id"], ev["seq"], ev["ts"], ev["actor"], ev.get("session"),
                  ev["type"], ev["scope"], ev["sensitivity"], ev["taint"],
                  payload_json, ev.get("payload_ref"), ev["payload_sha256"],
                  ev["prev_hash"], ev["hash"], ev["sig"], channel_json,
                  ev.get("sanitizer_note"), ev.get("capture_sig"))

        def exact_existing() -> bool:
            row = self.conn.execute(
                "SELECT id, seq, hash, payload_sha256 FROM events "
                "WHERE id = ? OR seq = ?", (ev["id"], ev["seq"])).fetchone()
            if row is None:
                return False
            if (row["id"] == ev["id"] and int(row["seq"]) == int(ev["seq"])
                    and row["hash"] == ev["hash"]
                    and row["payload_sha256"] == ev["payload_sha256"]):
                return True
            raise StoreError(
                "event mirror conflict: existing id/seq does not match "
                f"finalized spine event {ev['id']} at seq {ev['seq']}")

        with self.conn:
            if not exact_existing():
                try:
                    self.conn.execute(
                        "INSERT INTO events (id, seq, ts, actor, session, type, scope,"
                        " sensitivity, taint, payload_json, payload_ref, payload_sha256,"
                        " prev_hash, hash, sig, channel_json, sanitizer_note, capture_sig)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
                except sqlite3.IntegrityError:
                    # A concurrent reconciler may have inserted this exact
                    # event after the preflight query.  Accept only exact
                    # identity; every other collision remains fail-closed.
                    if not exact_existing():
                        raise
            self.conn.execute(
                "UPDATE ingester_state SET high_water_seq = MAX(high_water_seq, ?),"
                " updated_ts = ? WHERE id = 1",
                (ev["seq"], _now_ms()))

    # -- sealed checkpoints -------------------------------------------------
    @staticmethod
    def _checkpoint_bytes(seq_hi: int, chain_head_hash: str,
                          event_count: int, created_at: int) -> bytes:
        return canon.canonicalize({
            "chain_head_hash": chain_head_hash,
            "created_at": created_at,
            "event_count": event_count,
            "seq_hi": seq_hi,
        }).encode("utf-8")

    def checkpoint_due(self, now_ms: Optional[int] = None) -> bool:
        """True at the first non-empty head, then every 1,000 events or 24h."""
        now = now_ms or _now_ms()
        head = self.head_seq()
        if head < 1:
            return False
        row = self.conn.execute(
            "SELECT seq_hi, created_at FROM checkpoints ORDER BY seq_hi DESC LIMIT 1"
        ).fetchone()
        return (row is None or head - int(row["seq_hi"]) >= 1000
                or now - int(row["created_at"]) >= 24 * 60 * 60 * 1000)

    def seal_checkpoint_row(self, seq_hi: int, chain_head_hash: str,
                            created_at: Optional[int] = None) -> dict:
        if self.key is None:
            raise StoreError("instance key required to seal checkpoint")
        created = created_at or _now_ms()
        count = int(self.conn.execute(
            "SELECT COUNT(*) AS n FROM events WHERE seq <= ?", (seq_hi,)
        ).fetchone()["n"])
        raw = self._checkpoint_bytes(seq_hi, chain_head_hash, count, created)
        sig = base64.urlsafe_b64encode(self.key.sign(raw)).decode("ascii")
        with self.conn:
            self.conn.execute(
                "INSERT INTO checkpoints (seq_hi, chain_head_hash, event_count, instance_sig, created_at)"
                " VALUES (?,?,?,?,?)",
                (seq_hi, chain_head_hash, count, sig, created))
        return {"seq_hi": seq_hi, "chain_head_hash": chain_head_hash,
                "event_count": count, "instance_sig": sig,
                "created_at": created}

    def verify_latest_checkpoint(self) -> bool:
        row = self.conn.execute(
            "SELECT seq_hi, chain_head_hash, event_count, instance_sig, created_at"
            " FROM checkpoints ORDER BY seq_hi DESC LIMIT 1"
        ).fetchone()
        if row is None or self.key is None:
            return False
        event = self.conn.execute(
            "SELECT hash FROM events WHERE seq = ?", (row["seq_hi"],)
        ).fetchone()
        count = self.conn.execute(
            "SELECT COUNT(*) AS n FROM events WHERE seq <= ?", (row["seq_hi"],)
        ).fetchone()["n"]
        try:
            sig = base64.urlsafe_b64decode(row["instance_sig"])
        except Exception:
            return False
        raw = self._checkpoint_bytes(int(row["seq_hi"]),
                                     row["chain_head_hash"],
                                     int(row["event_count"]),
                                     int(row["created_at"]))
        return (event is not None and event["hash"] == row["chain_head_hash"]
                and int(count) == int(row["event_count"])
                and self.key.verify(raw, sig))

    def event_exists(self, event_id: str) -> Optional[str]:
        """Return payload_sha256 for an event id, or None (replay dedup key
        is (id, payload_sha256) — spool-format.md §6)."""
        row = self.conn.execute("SELECT payload_sha256 FROM events WHERE id = ?",
                                (event_id,)).fetchone()
        return row["payload_sha256"] if row else None

    def event_identity(self, event_id: str, seq: int) -> Optional[Dict[str, Any]]:
        """Return the minimal identity for an id/sequence mirror collision."""
        row = self.conn.execute(
            "SELECT id, seq, hash, payload_sha256 FROM events "
            "WHERE id = ? OR seq = ?", (event_id, seq)).fetchone()
        return dict(row) if row is not None else None

    def set_high_water(self, seq: int) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE ingester_state SET high_water_seq = ?, updated_ts = ? WHERE id = 1",
                (seq, _now_ms()))

    # -- payload store (U-04 spill; V-07 key model) -----------------------------
    def put_payload(self, blob: bytes, owner_id: str, created_seq: Optional[int] = None) -> str:
        """Encrypt + store a payload blob, content-addressed by the SHA-256 of
        its plaintext bytes (= payload_sha256 of the canonical payload). The
        owner (event id) owns the data key so erasure shreds the blob (V-07).
        Idempotent: an existing blob with the same hash is reused."""
        sha = canon.sha256_bytes_hex(blob)
        existing = self.conn.execute(
            "SELECT sha256 FROM payload_store WHERE sha256 = ?", (sha,)).fetchone()
        if existing:
            return sha
        seq = created_seq or max(self.head_seq(), 1)
        with self.conn:
            data_key = self._new_data_key(owner_id, seq)
            enc = self._aead_encrypt(data_key, blob)
            self.conn.execute(
                "INSERT INTO payload_store (sha256, blob_enc, nonce, bytes, created_seq)"
                " VALUES (?,?,?,?,?)",
                (sha, enc, enc[:_AEAD_NONCE_BYTES], len(blob), seq))
        return sha

    def discard_unreferenced_payload(self, sha256: str, owner_id: str) -> bool:
        """Remove a payload created for an event that never reached the spine.

        The operation is deliberately conservative: it acts only when no
        mirrored event references the blob *and* ``owner_id`` owns a wrapped
        key.  Content-addressed blobs reused from another owner are therefore
        never removed by another event's failed append.
        """
        with self.conn:
            referenced = self.conn.execute(
                "SELECT 1 FROM events WHERE payload_ref = ? LIMIT 1",
                (sha256,)).fetchone()
            owns_key = self.conn.execute(
                "SELECT 1 FROM record_keys WHERE record_id = ? LIMIT 1",
                (owner_id,)).fetchone()
            if referenced is not None or owns_key is None:
                return False
            self.conn.execute("DELETE FROM payload_store WHERE sha256 = ?", (sha256,))
            self.conn.execute("DELETE FROM record_keys WHERE record_id = ?", (owner_id,))
            return True

    def get_payload(self, sha256: str) -> bytes:
        """Decrypt a payload blob. The owning key is found via the event that
        references it (V-07: record_keys row keyed by the event id)."""
        row = self.conn.execute(
            "SELECT blob_enc FROM payload_store WHERE sha256 = ?", (sha256,)).fetchone()
        if row is None:
            raise StoreError(f"no payload {sha256}")
        owner = self.conn.execute(
            "SELECT id FROM events WHERE payload_ref = ? LIMIT 1", (sha256,)).fetchone()
        if owner is None:
            raise StoreError(f"no owner event for payload {sha256}")
        return self._aead_decrypt(self._data_key_for(owner["id"]), row["blob_enc"])

    # -- actors ------------------------------------------------------------------
    def ensure_actor(self, actor_id: str, kind: str, public_key: bytes,
                     scopes: Optional[List[str]] = None,
                     token_sha256: Optional[str] = None) -> None:
        """Insert an actor if absent (init seeds lamf-system + the bootstrap
        operator; pairing ceremonies live in the api layer)."""
        exists = self.conn.execute("SELECT actor_id FROM actors WHERE actor_id = ?",
                                   (actor_id,)).fetchone()
        if exists:
            return
        with self.conn:
            self.conn.execute(
                "INSERT INTO actors (actor_id, kind, public_key, token_sha256, scopes,"
                " created_at) VALUES (?,?,?,?,?,?)",
                (actor_id, kind, public_key, token_sha256,
                 json.dumps(scopes or []), _now_ms()))

    def actor_exists(self, actor_id: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM actors WHERE actor_id = ?", (actor_id,)).fetchone() is not None

    # -- memory records --------------------------------------------------------
    def _validate_rec(self, rec: Dict[str, Any]) -> None:
        if rec.get("type") not in RECORD_TYPES:
            raise StoreError(f"record type must be one of {RECORD_TYPES}")
        if rec.get("sensitivity", "ordinary") not in SENSITIVITIES:
            raise StoreError(f"sensitivity must be one of {SENSITIVITIES}")
        if rec.get("taint", "user_direct") not in TAINTS:
            raise StoreError(f"taint must be one of {TAINTS}")
        if rec.get("state", "active") not in RECORD_STATES:
            raise StoreError(f"state must be one of {RECORD_STATES}")
        if rec.get("confidence", "medium") not in CONFIDENCES:
            raise StoreError(f"confidence must be one of {CONFIDENCES}")

    def _blind_hash(self, term: str) -> str:
        cached = self._blind_token_cache.get(term)
        if cached is not None:
            return cached
        key = self._require_key().derive_key("blind-search-v1")
        token = hmac.new(key, term.encode("utf-8"), hashlib.sha256).hexdigest()[
            :_BLIND_TOKEN_HEX_CHARS]
        if len(self._blind_token_cache) >= _BLIND_TOKEN_CACHE_MAX:
            self._blind_token_cache.clear()
        self._blind_token_cache[term] = token
        return token

    def _blind_text(self, value: str) -> str:
        return " ".join(self._blind_hash(term)
                        for term in natural_index_words(value))

    def _search_refresh(self, record_id: str, title: str, body: str,
                        tags: list, entities: list) -> None:
        """Refresh contentless keyed FTS without persisting plaintext terms."""
        row = self.conn.execute("SELECT rowid FROM records WHERE id = ?",
                                (record_id,)).fetchone()
        if row is None:
            raise StoreError(f"cannot index unknown record {record_id}")
        rowid = int(row["rowid"])
        self.conn.execute(
            "INSERT INTO record_search_fts(rowid,title,body,tags,entities) "
            "VALUES (?,?,?,?,?)",
            (rowid, self._blind_text(title), self._blind_text(body),
             self._blind_text(" ".join(str(v) for v in tags)),
             self._blind_text(" ".join(str(v) for v in entities))))

    def upsert_record(self, rec: Dict[str, Any]) -> str:
        """Insert or replace a memory record head. PINNED SIGNATURE.

        `rec` follows schemas/memory-record.schema.json. `body` is plaintext;
        it is stored as body_enc under a per-record data key (U-08a) and the
        plaintext feeds records_fts only inside this transaction. Returns the
        record id. Re-upserting an existing id bumps `version` and snapshots
        the new version into record_versions.
        """
        self._validate_rec(rec)
        rec_id = rec.get("id")
        if not rec_id:
            from .spine import uuid7
            rec_id = "rec_" + uuid7().replace("-", "")
        body = rec.get("body", "")
        if not isinstance(body, str):
            raise StoreError("record body must be text")
        title = rec.get("title")
        if not title:
            raise StoreError("record title is required")
        tags_value = rec.get("tags") or []
        entities_value = rec.get("entities") or []
        if not isinstance(tags_value, list) or not isinstance(entities_value, list):
            raise StoreError("record tags and entities must be arrays")
        tags = json.dumps(tags_value)
        entities = json.dumps(entities_value)
        scope = rec.get("scope") or "user:default"
        owner = rec.get("owner_actor") or "lamf-system"
        sensitivity = rec.get("sensitivity", "ordinary")
        taint = rec.get("taint", "user_direct")
        state = rec.get("state", "active")
        confidence = rec.get("confidence", "medium")
        source_events = json.dumps(rec.get("source_events") or [])
        seq = rec.get("updated_seq") or max(self.head_seq(), 1)
        created_seq = rec.get("created_seq") or seq
        expires_at = rec.get("expires_at")

        with self.conn:
            old = self.conn.execute("SELECT rowid, version FROM records WHERE id = ?",
                                    (rec_id,)).fetchone()
            version = int(rec.get("version") or (old["version"] + 1 if old else 1))
            if old is None:
                data_key = self._new_data_key(rec_id, created_seq)
            else:
                data_key = self._data_key_for(rec_id)
            body_enc = self._aead_encrypt(data_key, body.encode("utf-8"))
            metadata_enc = self._aead_encrypt(data_key, json.dumps({
                "title": title, "tags": tags_value, "entities": entities_value,
            }, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            if old is None:
                cur = self.conn.execute(
                    "INSERT INTO records (id, type, title, body_enc, metadata_enc, tags, entities,"
                    " scope, owner_actor, sensitivity, taint, state, version,"
                    " supersedes, source_events, confidence, created_seq, updated_seq,"
                    " expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (rec_id, rec["type"], "[encrypted]", body_enc, metadata_enc, "[]", "[]", scope,
                     owner, sensitivity, taint, state, version,
                     rec.get("supersedes"), source_events, confidence,
                     created_seq, seq, expires_at))
                rowid = cur.lastrowid
            else:
                rowid = old["rowid"]
                self.conn.execute(
                    "UPDATE records SET type=?, title=?, body_enc=?, metadata_enc=?, tags=?, entities=?,"
                    " scope=?, owner_actor=?, sensitivity=?, taint=?, state=?, version=?,"
                    " supersedes=?, source_events=?, confidence=?, updated_seq=?,"
                    " expires_at=? WHERE id = ?",
                    (rec["type"], "[encrypted]", body_enc, metadata_enc, "[]", "[]", scope, owner,
                     sensitivity, taint, state, version, rec.get("supersedes"),
                     source_events, confidence, seq, expires_at, rec_id))
            self.conn.execute(
                "INSERT OR REPLACE INTO record_versions (record_id, version, title,"
                " body_enc, metadata_enc, tags, entities, state, sensitivity, taint, changed_seq)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (rec_id, version, "[encrypted]", body_enc, metadata_enc, "[]", "[]", state,
                 sensitivity, taint, seq))
            if old is None and state != "tombstoned":
                self._search_refresh(rec_id, title, body, tags_value, entities_value)
            elif old is not None:
                # Portable contentless FTS5 (SQLite <3.43 included) cannot
                # delete a row without its prior token columns. Rebuild the
                # disposable index on the uncommon update/tombstone path.
                self.rebuild_search_index()
        return rec_id

    def supersede(self, record_id: str, new_rec: Dict[str, Any], reason: str) -> str:
        """Supersede a record: old head is marked 'superseded'; the new
        record (new id, supersedes=record_id, version=old+1) becomes the
        head. Returns the NEW record id. PINNED SIGNATURE."""
        old = self.conn.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
        if old is None:
            raise StoreError(f"unknown record {record_id}")
        if old["state"] == "tombstoned":
            raise StoreError(f"record {record_id} is tombstoned (terminal)")
        from .spine import uuid7
        new_id = new_rec.get("id") or "rec_" + uuid7().replace("-", "")
        old_public = self._row_to_record(old)
        merged = {
            "id": new_id,
            "type": new_rec.get("type", old["type"]),
            "title": new_rec.get("title", old_public["title"]),
            "body": new_rec.get("body", self._decrypt_body(old)),
            "tags": new_rec.get("tags", old_public["tags"]),
            "entities": new_rec.get("entities", old_public["entities"]),
            "scope": new_rec.get("scope", old["scope"]),
            "owner_actor": new_rec.get("owner_actor", old["owner_actor"]),
            "sensitivity": new_rec.get("sensitivity", old["sensitivity"]),
            "taint": new_rec.get("taint", old["taint"]),
            "state": "active",
            "version": int(old["version"]) + 1,
            "supersedes": record_id,
            "source_events": new_rec.get("source_events", json.loads(old["source_events"])),
            "confidence": new_rec.get("confidence", old["confidence"]),
            "created_seq": new_rec.get("created_seq", max(self.head_seq(), 1)),
            "updated_seq": new_rec.get("updated_seq", max(self.head_seq(), 1)),
            "expires_at": new_rec.get("expires_at", old["expires_at"]),
        }
        with self.conn:
            self.conn.execute(
                "UPDATE records SET state = 'superseded', updated_seq = ? WHERE id = ?",
                (merged["updated_seq"], record_id))
        self.upsert_record(merged)
        return new_id

    def _decrypt_body(self, row: sqlite3.Row) -> str:
        return self._aead_decrypt(self._data_key_for(row["id"]), row["body_enc"]).decode("utf-8")

    def _row_to_record(self, row: sqlite3.Row) -> Dict[str, Any]:
        data_key = self._data_key_for(row["id"])
        metadata = json.loads(self._aead_decrypt(
            data_key, row["metadata_enc"]).decode("utf-8"))
        return {
            "id": row["id"], "type": row["type"], "title": metadata["title"],
            "body": self._aead_decrypt(data_key, row["body_enc"]).decode("utf-8"),
            "tags": metadata.get("tags", []), "entities": metadata.get("entities", []),
            "scope": row["scope"], "owner_actor": row["owner_actor"],
            "sensitivity": row["sensitivity"], "taint": row["taint"],
            "state": row["state"], "version": row["version"],
            "supersedes": row["supersedes"],
            "source_events": json.loads(row["source_events"]),
            "confidence": row["confidence"],
            "created_seq": row["created_seq"], "updated_seq": row["updated_seq"],
            "expires_at": row["expires_at"],
        }

    def get_record(self, record_id: str, include_history: bool = False) -> Dict[str, Any]:
        """Fetch a record with its body decrypted. PINNED SIGNATURE.
        include_history=True adds 'history': all record_versions snapshots
        (bodies decrypted), newest first."""
        row = self.conn.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            raise StoreError(f"unknown record {record_id}")
        rec = self._row_to_record(row)
        if include_history:
            data_key = self._data_key_for(record_id)
            hist = []
            for v in self.conn.execute(
                    "SELECT * FROM record_versions WHERE record_id = ? ORDER BY version DESC",
                    (record_id,)):
                hist.append({
                    "version": v["version"],
                    **json.loads(self._aead_decrypt(
                        data_key, v["metadata_enc"]).decode("utf-8")),
                    "body": self._aead_decrypt(data_key, v["body_enc"]).decode("utf-8"),
                    "state": v["state"], "sensitivity": v["sensitivity"],
                    "taint": v["taint"], "changed_seq": v["changed_seq"],
                })
            rec["history"] = hist
        # lineage: follow supersedes chain for prior record ids (cycle-guarded:
        # a malformed self-loop or cycle must degrade, never spin)
        lineage = []
        seen = set()
        cur = row["supersedes"]
        while cur and cur not in seen:
            seen.add(cur)
            lineage.append(cur)
            prow = self.conn.execute("SELECT supersedes FROM records WHERE id = ?",
                                     (cur,)).fetchone()
            cur = prow["supersedes"] if prow else None
        rec["superseded_chain"] = lineage
        return rec

    # -- search ------------------------------------------------------------------
    def search_fts(self, query: str, limit: int = 20,
                   filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Full-text search over records. PINNED SIGNATURE.

        The FTS index is a candidate generator, never authority (§N): every
        hit is re-checked against state/scope/sensitivity filters at read
        time; superseded and tombstoned records are excluded by default.
        Returns record dicts (bodies decrypted) with a 'score' (higher =
        better, -bm25).
        """
        filters = dict(filters or {})
        state = filters.pop("state", "active")
        where, params = [], []
        if state is not None:
            where.append("r.state = ?")
            params.append(state)
        for col in ("scope", "sensitivity", "type", "owner_actor"):
            if col in filters and filters[col] is not None:
                where.append(f"r.{col} = ?")
                params.append(filters[col])
        scopes = filters.get("scopes")
        if scopes:
            where.append("r.scope IN (%s)" % ",".join("?" for _ in scopes))
            params.extend(scopes)
        record_types = filters.get("record_types")
        if record_types:
            where.append("r.type IN (%s)" % ",".join("?" for _ in record_types))
            params.extend(record_types)
        sensitivity_max = filters.get("sensitivity_max", "ordinary")
        sensitivity_rank = {"ordinary": 0, "sensitive": 1, "restricted": 2}
        if sensitivity_max not in sensitivity_rank:
            raise StoreError(f"invalid sensitivity ceiling: {sensitivity_max}")
        where.append("CASE r.sensitivity WHEN 'ordinary' THEN 0 "
                     "WHEN 'sensitive' THEN 1 WHEN 'restricted' THEN 2 "
                     "ELSE 99 END <= ?")
        params.append(sensitivity_rank[sensitivity_max])
        cond = ("AND " + " AND ".join(where)) if where else ""
        terms = natural_search_terms(query)
        if not terms:
            return []
        hashes = [self._blind_hash(term) for term in terms]
        candidate_query = " OR ".join(f'"{token}"' for token in hashes)
        # Identifiers are fixed above; every external value uses a placeholder.
        # Rank narrow rows first, then fetch the encrypted record payloads for
        # only the winners.  Grouping ``r.*`` made SQLite carry large encrypted
        # body/metadata blobs through its temporary GROUP BY and ORDER BY
        # B-trees; on the LongMemEval fixture that dominated query latency.
        # The CTE preserves the same score, filters, ordering, and limit while
        # keeping the ranking working set to (record_id, score, updated_seq).
        sql = (  # nosec B608
            "WITH ranked AS (SELECT f.rowid, -bm25(record_search_fts) AS score "
            "FROM record_search_fts f JOIN records r ON r.rowid = f.rowid "
            "WHERE record_search_fts MATCH ? " + cond +
            " ORDER BY score DESC, r.updated_seq DESC LIMIT ?) "
            "SELECT r.*, ranked.score FROM ranked "
            "JOIN records r ON r.rowid = ranked.rowid "
            "ORDER BY ranked.score DESC, r.updated_seq DESC")
        rows = self.conn.execute(
            sql, [candidate_query, *params, int(limit)]).fetchall()
        out = []
        for row in rows:
            rec = self._row_to_record(row)
            rec["score"] = row["score"]
            out.append(rec)
        return out

    def search_index_health(self) -> Dict[str, Any]:
        """Check keyed-FTS structure and row coverage against record heads."""
        expected = int(self.conn.execute(
            "SELECT COUNT(*) FROM records WHERE state != 'tombstoned'").fetchone()[0])
        try:
            actual = int(self.conn.execute(
                "SELECT COUNT(*) FROM record_search_fts").fetchone()[0])
            was_in_transaction = self.conn.in_transaction
            self.conn.execute(
                "INSERT INTO record_search_fts(record_search_fts) "
                "VALUES('integrity-check')")
            if not was_in_transaction:
                self.conn.commit()
            integrity = True
        except sqlite3.DatabaseError:
            actual = -1
            integrity = False
        return {"healthy": integrity and actual == expected,
                "integrity": integrity, "expected_rows": expected,
                "actual_rows": actual}

    def ensure_search_index(self) -> bool:
        """Automatically rebuild an incomplete/corrupt derived search index.

        Returns True when recovery was performed. Encrypted record heads remain
        authoritative and are never changed by this operation.
        """
        health = self.search_index_health()
        if health["healthy"]:
            return False
        self.rebuild_search_index(recreate=not health["integrity"])
        verified = self.search_index_health()
        if not verified["healthy"]:
            raise StoreError(f"keyed FTS recovery verification failed: {verified}")
        return True

    def rebuild_search_index(self, recreate: bool = False) -> int:
        """Rebuild keyed FTS from encrypted record heads; return row count."""
        rows = self.conn.execute(
            "SELECT * FROM records WHERE state != 'tombstoned'").fetchall()
        with self.conn:
            if recreate:
                self.conn.execute("DROP TABLE IF EXISTS record_search_fts")
                self.conn.execute("""CREATE VIRTUAL TABLE record_search_fts USING fts5(
                    title, body, tags, entities, content='',
                    tokenize='unicode61')""")
            else:
                self.conn.execute(
                    "INSERT INTO record_search_fts(record_search_fts) VALUES('delete-all')")
            for row in rows:
                public = self._row_to_record(row)
                self._search_refresh(row["id"], public["title"], public["body"],
                                     public["tags"], public["entities"])
        return len(rows)

    def list_records(self, limit: int = 50, state: Optional[str] = "active") -> List[Dict[str, Any]]:
        """Return recent memory heads for the human library view.

        This is intentionally separate from FTS: opening the standalone UI
        should feel like opening a library, not like facing an empty search box.
        Bodies are decrypted at the authority boundary, just as they are for
        ``get_record`` and ``search_fts``.
        """
        limit = max(1, min(int(limit), 200))
        if state is None:
            rows = self.conn.execute(
                "SELECT * FROM records ORDER BY updated_seq DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM records WHERE state = ? ORDER BY updated_seq DESC LIMIT ?",
                (state, limit),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    # -- approvals (operator queue, §J) ---------------------------------------------
    def list_approvals(self, state: str = "pending") -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM approvals WHERE state = ? ORDER BY created_at", (state,)).fetchall()
        return [dict(r) for r in rows]

    def decide_approval(self, approval_id: str, approve: bool, decided_by: str,
                        reason: Optional[str] = None, event_seq: Optional[int] = None) -> str:
        """pending -> approved|denied, receipted (F8). Returns the receipt id."""
        from .spine import uuid7
        with self.conn:
            cur = self.conn.execute(
                "UPDATE approvals SET state = ?, reason = ?, decided_at = ?, decided_by = ?"
                " WHERE id = ? AND state = 'pending'",
                ("approved" if approve else "denied", reason, _now_ms(), decided_by,
                 approval_id))
            if cur.rowcount != 1:
                raise StoreError(f"approval {approval_id} unknown or already decided")
            receipt_id = "rcp_" + uuid7().replace("-", "")
            self.conn.execute(
                "INSERT INTO receipts (receipt_id, actor, action, subject, items,"
                " event_seq, created_at) VALUES (?,?,?,?,?,?,?)",
                (receipt_id, decided_by, "approve" if approve else "deny",
                 approval_id, None, event_seq, _now_ms()))
            self.conn.execute("UPDATE approvals SET receipt_id = ? WHERE id = ?",
                              (receipt_id, approval_id))
        return receipt_id

    # -- stats ----------------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        """Instance statistics for `lamf status` / memory_status. PINNED."""
        c = self.conn
        events = c.execute("SELECT COUNT(*) n, COALESCE(MAX(seq),0) s FROM events").fetchone()
        recs = {r["state"]: r["n"] for r in c.execute(
            "SELECT state, COUNT(*) n FROM records GROUP BY state")}
        spool_gap = c.execute(
            "SELECT COUNT(*) n FROM events WHERE type = 'spool_gap'").fetchone()["n"]
        ck = c.execute(
            "SELECT seq_hi, chain_head_hash, event_count, created_at FROM checkpoints"
            " ORDER BY seq_hi DESC LIMIT 1").fetchone()
        hw = c.execute("SELECT high_water_seq FROM ingester_state WHERE id = 1").fetchone()
        ps = c.execute("SELECT version FROM policy_state WHERE id = 1").fetchone()
        appr = c.execute("SELECT COUNT(*) n FROM approvals WHERE state='pending'").fetchone()["n"]
        quar = c.execute("SELECT COUNT(*) n FROM quarantine WHERE state='quarantined'").fetchone()["n"]
        actors = c.execute("SELECT COUNT(*) n FROM actors WHERE revoked_at IS NULL").fetchone()["n"]
        return {
            "events": events["n"], "head_seq": events["s"],
            "records": recs, "records_total": sum(recs.values()),
            "spool_gap_events": spool_gap,
            "checkpoint": dict(ck) if ck else None,
            "ingester_high_water": hw["high_water_seq"] if hw else 0,
            "policy_version": ps["version"] if ps else 1,
            "pending_approvals": appr, "quarantined": quar, "actors": actors,
        }
