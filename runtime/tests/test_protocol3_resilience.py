from __future__ import annotations

import concurrent.futures
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lamf.crypto import InstanceKey
from lamf.store import Store

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"


def _run(data: Path, *args, timeout=60):
    env = {**os.environ, "PYTHONPATH": str(RUNTIME)}
    return subprocess.run(
        [sys.executable, "-m", "lamf.cli", *args, "--data-dir", str(data)],
        env=env, capture_output=True, text=True, timeout=timeout)


def test_multiprocess_writes_and_crash_recovery(tmp_path):
    data = tmp_path / "stress"
    assert _run(data, "init").returncode == 0

    def remember(i):
        return _run(data, "remember", "--scope", "project:stress",
                    "--title", f"worker-{i}", "--body", f"body-{i}").returncode

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(remember, range(16))) == [0] * 16
    assert _run(data, "verify", "--deep").returncode == 0

    env = {**os.environ, "PYTHONPATH": str(RUNTIME)}
    for i in range(8):
        process = subprocess.Popen(
            [sys.executable, "-m", "lamf.cli", "remember", "--data-dir", str(data),
             "--scope", "project:stress", "--title", f"crash-{i}",
             "--body", "X" * 8192], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep((i % 4) * 0.003)
        if process.poll() is None:
            process.kill()
        process.wait()
    assert _run(data, "verify", "--deep").returncode == 0
    assert remember("post-crash") == 0
    assert _run(data, "verify", "--deep").returncode == 0


def test_corrupted_spine_fails_verification(tmp_path):
    data = tmp_path / "corrupt"
    assert _run(data, "init").returncode == 0
    assert _run(data, "remember", "--title", "canary", "--body", "body").returncode == 0
    segment = next((data / "events").glob("segment-*.jsonl"))
    raw = segment.read_bytes()
    segment.write_bytes(raw[:-1] + (b"X" if raw[-1:] != b"X" else b"Y"))
    assert _run(data, "verify", "--deep").returncode != 0


def test_disk_full_failure_rolls_back_record_transaction(tmp_path, monkeypatch):
    data = tmp_path / "full"
    assert _run(data, "init").returncode == 0
    key = InstanceKey.load(data / "instance.key")
    store = Store.open(data / "lamf.db", instance_key=key)
    record = {
        "id": "rec_disk_full_canary", "type": "fact", "title": "before",
        "body": "stable", "scope": "project:full", "owner_actor": "lamf-system",
        "created_seq": 1, "updated_seq": 1,
    }
    store.upsert_record(record)

    def fail_full(*_args, **_kwargs):
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(store, "_search_refresh", fail_full)
    changed = {**record, "title": "partial", "body": "must roll back",
               "updated_seq": 2}
    with pytest.raises(sqlite3.OperationalError, match="disk is full"):
        store.upsert_record(changed)
    current = store.get_record(record["id"], include_history=True)
    assert current["title"] == "before" and current["body"] == "stable"
    assert len(current["history"]) == 1
    store.close()


def test_reopen_automatically_recovers_partial_search_index_loss(tmp_path):
    data = tmp_path / "fts-loss"
    assert _run(data, "init").returncode == 0
    assert _run(data, "remember", "--title", "recoverable",
                "--body", "automatic search recovery canary").returncode == 0
    key = InstanceKey.load(data / "instance.key")
    store = Store.open(data / "lamf.db", instance_key=key)
    record_id = store.search_fts("recovery canary")[0]["id"]
    store.conn.execute(
        "INSERT INTO record_search_fts(record_search_fts) VALUES('delete-all')")
    store.conn.commit()
    assert not store.search_fts("recovery canary")
    store.close()

    reopened = Store.open(data / "lamf.db", instance_key=key)
    assert reopened.search_index_health()["healthy"]
    assert reopened.search_fts("recovery canary")[0]["id"] == record_id
    reopened.close()


def test_reopen_automatically_recovers_structural_search_corruption(tmp_path):
    data = tmp_path / "fts-corrupt"
    assert _run(data, "init").returncode == 0
    assert _run(data, "remember", "--title", "structural",
                "--body", "structural corruption recovery canary").returncode == 0
    key = InstanceKey.load(data / "instance.key")
    conn = sqlite3.connect(data / "lamf.db")
    conn.execute("DELETE FROM record_search_fts_idx")
    conn.commit()
    conn.close()

    reopened = Store.open(data / "lamf.db", instance_key=key)
    assert reopened.search_index_health()["healthy"]
    assert reopened.search_fts("structural corruption canary")
    reopened.close()
