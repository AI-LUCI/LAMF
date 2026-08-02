#!/usr/bin/env python3
"""Deploy a sensitive record through the real stdio MCP server."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from unittest.mock import patch
from pathlib import Path

import nacl.signing

TESTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(TESTS_DIR.parent))

from final_test_support import McpClient, RUNTIME_DIR, new_instance  # noqa: E402
from lamf import api  # noqa: E402
from lamf.cli import _open_ctx  # noqa: E402
from lamf.crypto import InstanceKey  # noqa: E402
from lamf.store import Store  # noqa: E402


def main():
    # Deterministic Windows regression: a seed containing LF must remain
    # exactly 32 raw bytes on disk (never text-mode expanded to CRLF).
    seed = b"\x0a" + bytes(range(1, 32))
    with tempfile.TemporaryDirectory(prefix="lamf-key-binary-") as key_tmp:
        key_path = Path(key_tmp) / "instance.key"
        with patch("lamf.crypto.nacl.signing.SigningKey.generate",
                   return_value=nacl.signing.SigningKey(seed)):
            InstanceKey.generate(key_path)
        assert key_path.read_bytes() == seed

    root, data_dir = new_instance("lamf-final-sensitive-")
    phrase = "FINAL-SENSITIVE-RECALL-74291"
    try:
        with McpClient(data_dir) as client:
            remembered = client.tool("memory_remember", {
                "title": "Final sensitive deployment record",
                "body": f"The deploy-level sensitive test phrase is {phrase}.",
                "record_type": "fact", "scope": "test:final-sensitive",
                "sensitivity": "sensitive", "tags": ["final-test"]})
            record_id = remembered["record_id"]

        ctx = _open_ctx(data_dir)
        try:
            corrected = api.correct_record(
                ctx, record_id, 1,
                f"The corrected sensitive test phrase remains {phrase}.",
                "final sensitive correction")
            api.save_approvals(data_dir, [{
                "approval_id": "approval_final_sensitive", "state": "pending",
                "kind": "final-test", "scope": "test:final-sensitive",
                "sensitivity": "sensitive"}])
        finally:
            ctx.store.close()

        with McpClient(data_dir) as client:
            approval = client.tool("memory_approvals", {
                "action": "approve", "approval_id": "approval_final_sensitive",
                "reason": "final sensitive approval test"})
        approval_event_id = approval["decided"]["event_id"]

        cli = subprocess.run(
            [sys.executable, "-m", "lamf.cli", "remember",
             "--data-dir", str(data_dir), "--title", "Final sensitive CLI record",
             "--body", "Sensitive CLI deployment body", "--type", "fact",
             "--scope", "test:final-sensitive", "--sensitivity", "sensitive"],
            cwd=RUNTIME_DIR, text=True, capture_output=True, timeout=30)
        assert cli.returncode == 0, cli.stderr
        cli_result = json.loads(cli.stdout.strip().splitlines()[-1])

        conn = sqlite3.connect(data_dir / "lamf.db")
        conn.row_factory = sqlite3.Row
        event_ids = [remembered["event_id"], corrected["event_id"],
                     approval_event_id, cli_result["source_event"]]
        events = [conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
                  for event_id in event_ids]
        assert all(event is not None for event in events)
        for event in events:
            assert event["sensitivity"] == "sensitive"
            assert event["payload_json"] is None
            assert event["payload_ref"] is not None
            assert conn.execute("SELECT 1 FROM payload_store WHERE sha256 = ?",
                                (event["payload_ref"],)).fetchone()
        record = conn.execute(
            "SELECT body_enc, sensitivity FROM records WHERE id = ?",
            (corrected["record_id"],)).fetchone()
        assert record["sensitivity"] == "sensitive"
        assert phrase.encode() not in record["body_enc"]
        conn.close()

        key = InstanceKey.load(data_dir / "instance.key")
        with Store.open(data_dir / "lamf.db", instance_key=key) as store:
            audit = json.loads(store.get_payload(events[0]["payload_ref"]).decode("utf-8"))
            assert audit["title"] == "Final sensitive deployment record"
            fetched = store.get_record(corrected["record_id"])
            assert phrase in fetched["body"]

        spine_events = []
        for segment in sorted((data_dir / "events").glob("segment-*.jsonl")):
            spine_events += [json.loads(line) for line in segment.read_text(
                encoding="utf-8").splitlines() if line]
        for event_id, db_event in zip(event_ids, events):
            spine_event = next(item for item in spine_events if item["id"] == event_id)
            assert "payload" not in spine_event
            assert spine_event["payload_ref"] == db_event["payload_ref"]
        print(json.dumps({"result": "PASS", "record_id": corrected["record_id"],
                          "sensitive_event_ids": event_ids,
                          "encrypted_payload_refs": [e["payload_ref"] for e in events]},
                         indent=2))
    finally:
        shutil.rmtree(root, ignore_errors=False)


if __name__ == "__main__":
    main()
