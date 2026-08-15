from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from lamf import api, optimizations, sanitize
from lamf.crypto import InstanceKey
from lamf.policy import load_policy
from lamf.store import Store


ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / ".test-runs"
SCHEMA = ROOT / "04_STORAGE" / "SCHEMA.sql"
PROFILE = ROOT / "02_SECURITY" / "profiles" / "controlled.yaml"


@pytest.fixture
def instance():
    RUNS.mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="protocol3-security-", dir=RUNS))
    data = root / "data"
    data.mkdir()
    key = InstanceKey.generate(data / "instance.key")
    store = Store.open(data / "lamf.db", SCHEMA, instance_key=key)
    store.ensure_actor("lamf-system", "system", b"0" * 32)
    policy = load_policy(PROFILE)
    ctx = types.SimpleNamespace(data_dir=str(data), store=store, spine=None,
                                policy=policy, instance_key=key,
                                actor="lamf-operator")
    yield root, data, store, ctx
    store.close()


def remember(store, index=0, sensitivity="sensitive"):
    marker = f"BODY_SECRET_CANARY_{index}_7X9Q"
    record_id = store.upsert_record({
        "type": "fact",
        "title": f"TITLE_CANARY_{index}",
        "body": marker,
        "tags": [f"TAG_CANARY_{index}"],
        "entities": [f"ENTITY_CANARY_{index}"],
        "scope": "project:protocol3-test",
        "owner_actor": "lamf-system",
        "sensitivity": sensitivity,
        "taint": "user_direct",
        "state": "active",
        "confidence": "high",
    })
    return record_id, marker


def test_database_contains_no_plaintext_memory_or_search_terms(instance):
    _, data, store, _ = instance
    record_id, body = remember(store)
    assert store.search_fts(body, filters={"sensitivity_max": "sensitive"})[0]["id"] == record_id
    store.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    raw = (data / "lamf.db").read_bytes()
    for marker in (body, "TITLE_CANARY_0", "TAG_CANARY_0", "ENTITY_CANARY_0"):
        assert marker.encode() not in raw
    conn = sqlite3.connect(data / "lamf.db")
    assert conn.execute("SELECT title FROM records").fetchone()[0] == "[encrypted]"
    conn.execute("CREATE VIRTUAL TABLE search_vocab USING "
                 "fts5vocab(record_search_fts, 'row')")
    terms = conn.execute("SELECT term FROM search_vocab").fetchall()
    conn.close()
    assert terms and all(len(row[0]) == 24 for row in terms)


def test_blind_search_preserves_weighted_ranking(instance):
    _, _, store, _ = instance
    records = [
        ("title-hit", "needle", "unrelated", [], []),
        ("entity-hit", "unrelated", "unrelated", [], ["needle"]),
        ("tag-hit", "unrelated", "unrelated", ["needle"], []),
        ("body-hit", "unrelated", "needle", [], []),
    ]
    ids = {}
    for name, title, body, tags, entities in records:
        ids[name] = store.upsert_record({
            "id": name, "type": "fact", "title": title, "body": body,
            "tags": tags, "entities": entities,
            "scope": "project:protocol3-test", "owner_actor": "lamf-system",
            "sensitivity": "ordinary", "taint": "user_direct",
            "state": "active", "confidence": "high",
        })

    found = store.search_fts("needle", limit=10)
    assert found[0]["id"] == ids["title-hit"]
    assert {record["id"] for record in found} == set(ids.values())
    assert [record["score"] for record in found] == sorted(
        [record["score"] for record in found], reverse=True)


def test_keyed_fts_refresh_tombstone_and_rebuild(instance):
    _, _, store, _ = instance
    record_id, _ = remember(store, sensitivity="ordinary")
    assert store.search_fts("7X9Q")
    changed = store.get_record(record_id)
    changed.update({"body": "replacement searchable marker", "updated_seq": 2})
    store.upsert_record(changed)
    assert not store.search_fts("7X9Q")
    assert store.search_fts("replacement searchable marker")[0]["id"] == record_id
    store.conn.execute(
        "INSERT INTO record_search_fts(record_search_fts) VALUES('delete-all')")
    assert not store.search_fts("replacement searchable marker")
    assert store.rebuild_search_index() == 1
    assert store.search_fts("replacement searchable marker")[0]["id"] == record_id
    tombstoned = store.get_record(record_id)
    tombstoned.update({"state": "tombstoned", "updated_seq": 3})
    store.upsert_record(tombstoned)
    assert not store.search_fts("replacement searchable marker", filters={"state": None})


def test_orientation_enforces_complete_budget(instance):
    _, _, store, ctx = instance
    labels = ["identity", "prefer", "task", "decision"]
    for i in range(24):
        store.upsert_record({
            "type": "fact", "title": f"{labels[i % 4]} {i}",
            "body": labels[i % 4] + " " + ("bounded context " * 100),
            "scope": "project:protocol3-test", "owner_actor": "lamf-system",
            "sensitivity": "ordinary", "taint": "user_direct",
            "state": "active", "confidence": "high",
        })
    result = api.orientation(ctx, 200, "budget-test")
    serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    assert result["effective_max_tokens"] == 200
    assert (len(serialized.encode("utf-8")) + 2) // 3 <= 210
    assert result["omissions"]


@pytest.mark.parametrize("candidate", [
    "akiaAB12CD34EF56GH78",
    "sk%2DAb3Xy9Qw7Lm2Np8Rt6Vz",
    "sk\u200b-Ab3Xy9Qw7Lm2Np8Rt6Vz",
    "sk- Ab3Xy9Qw7Lm2Np8Rt6Vz",
    r"sk\u002dAb3Xy9Qw7Lm2Np8Rt6Vz",
    "c2stQWIzWHk5UXc3TG0yTnA4UnQ2Vno=",
    "eyJabcdefghijk . abcdefghijklmno . abcdef",
])
def test_common_secret_obfuscations_are_blocked(candidate):
    assert sanitize.scan(candidate)


def test_http_authentication_rate_limit(instance):
    _, data, _, ctx = instance
    (data / "operator.token").write_text("a" * 64, encoding="utf-8")
    server = api.make_server(ctx, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    statuses = []
    try:
        for i in range(65):
            req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/status")
            req.add_header("Authorization", f"Bearer invalid-{i}")
            req.add_header("Host", f"127.0.0.1:{port}")
            try:
                urllib.request.urlopen(req, timeout=3)
            except urllib.error.HTTPError as exc:
                statuses.append(exc.code)
        assert statuses[:60] == [401] * 60
        assert 429 in statuses[60:]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_optimization_instruction_tamper_is_quarantined(instance):
    root, _, _, _ = instance
    source = ROOT / "05_INTEGRATIONS" / "optimizations" / "modules"
    copy = root / "modules"
    import shutil
    shutil.copytree(source, copy)
    target = copy / "minimal-solution" / "instruction.md"
    target.write_text(target.read_text(encoding="utf-8") + "\nmalicious change",
                      encoding="utf-8")
    found = {item["id"]: item for item in optimizations.discover(copy)}
    assert found["minimal-solution"]["error"] == "instruction fragment hash mismatch"
