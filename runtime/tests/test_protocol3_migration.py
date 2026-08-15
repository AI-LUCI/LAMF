from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
sys.path.insert(0, str(RUNTIME))

from lamf.crypto import InstanceKey
from lamf.store import (MigrationRequired, Store, migrate_keyed_fts,
                        migrate_protocol3)


def _downgrade_fixture(tmp_path: Path):
    data = tmp_path / "v2"
    data.mkdir()
    key = InstanceKey.generate(data / "instance.key")
    store = Store.open(data / "lamf.db", instance_key=key)
    store.ensure_actor("lamf-system", "system", bytes.fromhex(key.pub_hex), scopes=["*"])
    rec_id = store.upsert_record({
        "type": "fact", "title": "Private migration title",
        "body": "migration body canary", "tags": ["private-tag"],
        "entities": ["private-entity"], "scope": "project:migration",
        "owner_actor": "lamf-system", "created_seq": 1, "updated_seq": 1,
    })
    rec = store.get_record(rec_id, include_history=True)
    store.close()

    conn = sqlite3.connect(data / "lamf.db")
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.executescript("""
        DROP TRIGGER IF EXISTS record_search_fts_purge_tombstone;
        DROP TRIGGER IF EXISTS record_search_fts_purge_delete;
        DROP TABLE IF EXISTS record_search_fts;
        DROP TRIGGER IF EXISTS record_search_terms_purge_tombstone;
        DROP TABLE IF EXISTS record_search_terms;
        ALTER TABLE records RENAME TO records_v3;
        CREATE TABLE records (
            id TEXT PRIMARY KEY, type TEXT NOT NULL, title TEXT NOT NULL,
            body_enc BLOB NOT NULL, tags TEXT NOT NULL, entities TEXT NOT NULL,
            scope TEXT NOT NULL, owner_actor TEXT NOT NULL, sensitivity TEXT NOT NULL,
            taint TEXT NOT NULL, state TEXT NOT NULL, version INTEGER NOT NULL,
            supersedes TEXT, source_events TEXT NOT NULL, confidence TEXT NOT NULL,
            created_seq INTEGER NOT NULL, updated_seq INTEGER NOT NULL, expires_at INTEGER);
        INSERT INTO records SELECT id,type,title,body_enc,tags,entities,scope,
            owner_actor,sensitivity,taint,state,version,supersedes,source_events,
            confidence,created_seq,updated_seq,expires_at FROM records_v3;
        DROP TABLE records_v3;
        ALTER TABLE record_versions RENAME TO record_versions_v3;
        CREATE TABLE record_versions (
            record_id TEXT NOT NULL REFERENCES records(id), version INTEGER NOT NULL,
            title TEXT NOT NULL, body_enc BLOB NOT NULL, tags TEXT NOT NULL,
            entities TEXT NOT NULL, state TEXT NOT NULL, sensitivity TEXT NOT NULL,
            taint TEXT NOT NULL, changed_seq INTEGER NOT NULL,
            PRIMARY KEY (record_id, version));
        INSERT INTO record_versions SELECT record_id,version,title,body_enc,tags,
            entities,state,sensitivity,taint,changed_seq FROM record_versions_v3;
        DROP TABLE record_versions_v3;
        DELETE FROM schema_migrations WHERE version >= 3;
    """)
    conn.execute("UPDATE records SET title=?, tags=?, entities=? WHERE id=?",
                 (rec["title"], json.dumps(rec["tags"]),
                  json.dumps(rec["entities"]), rec_id))
    conn.execute("UPDATE record_versions SET title=?, tags=?, entities=?",
                 (rec["title"], json.dumps(rec["tags"]),
                  json.dumps(rec["entities"])))
    conn.commit()
    conn.close()
    return data, key, rec_id


def test_v2_open_fails_closed_until_explicit_migration(tmp_path):
    data, key, _ = _downgrade_fixture(tmp_path)
    with pytest.raises(MigrationRequired):
        Store.open(data / "lamf.db", instance_key=key)


def test_v2_migration_backs_up_encrypts_and_preserves_recall(tmp_path):
    data, key, rec_id = _downgrade_fixture(tmp_path)
    backup = tmp_path / "backups" / "before.sqlite"
    result = migrate_protocol3(data / "lamf.db", key, backup)
    assert result == backup and backup.is_file()
    assert sqlite3.connect(backup).execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    raw = (data / "lamf.db").read_bytes()
    for secret in (b"Private migration title", b"private-tag", b"private-entity",
                   b"migration body canary"):
        assert secret not in raw
    store = Store.open(data / "lamf.db", instance_key=key)
    assert store.get_record(rec_id)["title"] == "Private migration title"
    assert store.search_fts("migration canary", filters={
        "scope": "project:migration"})[0]["id"] == rec_id
    assert store.conn.execute(
        "SELECT description FROM schema_migrations WHERE version=3").fetchone()
    store.close()


def test_legacy_protocol3_keyed_fts_migration(tmp_path):
    data = tmp_path / "legacy-v3"
    data.mkdir()
    key = InstanceKey.generate(data / "instance.key")
    store = Store.open(data / "lamf.db", instance_key=key)
    store.ensure_actor("lamf-system", "system", bytes.fromhex(key.pub_hex),
                       scopes=["*"])
    record_id = store.upsert_record({
        "type": "fact", "title": "Migration search title",
        "body": "keyed fts migration canary", "scope": "project:migration",
        "owner_actor": "lamf-system", "sensitivity": "ordinary",
        "taint": "user_direct", "state": "active", "confidence": "high",
    })
    store.close()
    conn = sqlite3.connect(data / "lamf.db")
    conn.executescript("""
        DROP TRIGGER IF EXISTS record_search_fts_purge_tombstone;
        DROP TRIGGER IF EXISTS record_search_fts_purge_delete;
        DROP TABLE record_search_fts;
        CREATE TABLE record_search_terms (
            record_id TEXT NOT NULL, term_hash TEXT NOT NULL,
            field TEXT NOT NULL, occurrences INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY(record_id, term_hash, field));
        CREATE INDEX idx_record_search_terms_hash ON record_search_terms(term_hash);
    """)
    conn.commit()
    conn.close()
    with pytest.raises(MigrationRequired):
        Store.open(data / "lamf.db", instance_key=key)
    backup = migrate_keyed_fts(data / "lamf.db", key, tmp_path / "legacy.sqlite")
    assert backup.is_file()
    store = Store.open(data / "lamf.db", instance_key=key)
    assert store.search_fts("migration canary")[0]["id"] == record_id
    assert store.conn.execute("PRAGMA freelist_count").fetchone()[0] == 0
    assert store.conn.execute(
        "SELECT description FROM schema_migrations WHERE version=4").fetchone()
    store.close()


def test_cli_data_dir_is_order_independent(tmp_path):
    data = tmp_path / "fresh"
    env = {**__import__("os").environ, "PYTHONPATH": str(RUNTIME)}
    before = subprocess.run(
        [sys.executable, "-m", "lamf.cli", "--data-dir", str(data),
         "init", "--profile", "controlled"], env=env, capture_output=True, text=True)
    assert before.returncode == 0, before.stderr
    status = subprocess.run(
        [sys.executable, "-m", "lamf.cli", "status", "--data-dir", str(data)],
        env=env, capture_output=True, text=True)
    assert status.returncode == 0, status.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Windows ACL contract")
def test_init_protects_secret_files_with_windows_dacl(tmp_path):
    data = tmp_path / "acl"
    env = {**__import__("os").environ, "PYTHONPATH": str(RUNTIME)}
    result = subprocess.run(
        [sys.executable, "-m", "lamf.cli", "init", "--data-dir", str(data)],
        env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for name in ("operator.token", "instance.key"):
        acl_env = {**env, "LAMF_ACL_TEST_PATH": str(data / name)}
        acl = subprocess.run(
            ["pwsh.exe", "-NoProfile", "-NonInteractive", "-Command",
             "(Get-Acl -LiteralPath $env:LAMF_ACL_TEST_PATH).Sddl"], env=acl_env,
            capture_output=True, text=True, check=True).stdout.strip()
        assert ";;;SY)" in acl and ";;;BA)" in acl
        assert ";;;BU)" not in acl and ";;;AU)" not in acl


def test_mcp_stdio_forces_utf8_under_legacy_codepage(tmp_path):
    data = tmp_path / "mcp"
    env = {**__import__("os").environ, "PYTHONPATH": str(RUNTIME),
           "PYTHONIOENCODING": "cp1252", "LAMF_DATA_DIR": str(data)}
    init = subprocess.run(
        [sys.executable, "-m", "lamf.cli", "init", "--data-dir", str(data)],
        env=env, capture_output=True)
    assert init.returncode == 0, init.stderr.decode(errors="replace")
    messages = "\n".join((
        json.dumps({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18",
                               "capabilities": {}, "clientInfo": {
                                   "name": "utf8-probe", "version": "1"}}}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list",
                    "params": {}}), ""))
    proc = subprocess.run(
        [sys.executable, str(RUNTIME / "lamf_mcp.py")], env=env,
        input=messages.encode(), capture_output=True, timeout=30)
    decoded = proc.stdout.decode("utf-8")
    replies = [json.loads(line) for line in decoded.splitlines()]
    assert len(replies) == 2 and len(replies[1]["result"]["tools"]) == 10
