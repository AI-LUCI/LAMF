#!/usr/bin/env python3
"""Deploy a legacy sensitive-inline spine event and prove safe reconciliation."""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import types
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = TESTS_DIR.parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(RUNTIME_DIR))

from final_test_support import new_instance  # noqa: E402
from lamf import api  # noqa: E402
from lamf.cli import _open_ctx  # noqa: E402
from lamf.crypto import InstanceKey  # noqa: E402
from lamf.spine import Spine  # noqa: E402
from lamf.store import StoreError  # noqa: E402


def main():
    root, data_dir = new_instance("lamf-final-recovery-")
    try:
        key = InstanceKey.load(data_dir / "instance.key")
        spine = Spine(data_dir / "events", instance_key=key)
        ctx = types.SimpleNamespace(actor="lamf-operator")
        legacy = api.make_event(
            ctx, "memory_request", {"title": "Legacy recovery probe"},
            scope="test:final-recovery", sensitivity="sensitive",
            taint="user_direct")
        spine.append(legacy)  # simulate the historical pre-fix failure exactly

        conn = sqlite3.connect(data_dir / "lamf.db")
        try:
            before = conn.execute(
                "SELECT COUNT(*) FROM events WHERE id = ?", (legacy["id"],)).fetchone()[0]
            assert before == 0
        finally:
            conn.close()

        opened = _open_ctx(data_dir)
        try:
            row = opened.store.conn.execute(
                "SELECT payload_json, payload_ref FROM events WHERE id = ?",
                (legacy["id"],)).fetchone()
            assert row is not None and row["payload_json"] is None and row["payload_ref"]
            assert opened.store.get_payload(row["payload_ref"]) == api._event_payload_bytes(
                {"title": "Legacy recovery probe"})
            assert opened.store.head_seq() == opened.spine.head()[0]
            assert opened.spine.verify_deep()

            # Ordinary payloads above the 4 KiB inline limit use the same
            # encrypted reference path.
            oversized = api.make_event(
                ctx, "message", {"text": "x" * 5000},
                scope="test:final-recovery", sensitivity="ordinary",
                taint="user_direct")
            api.spine_append(opened.spine, oversized, opened.store)
            assert "payload" not in oversized and oversized.get("payload_ref")
            before_retry = opened.store.conn.execute(
                "SELECT COUNT(*) FROM events WHERE id = ?", (oversized["id"],)).fetchone()[0]
            opened.store.insert_event(dict(oversized))
            after_retry = opened.store.conn.execute(
                "SELECT COUNT(*) FROM events WHERE id = ?", (oversized["id"],)).fetchone()[0]
            assert before_retry == after_retry == 1
            conflicting = dict(oversized)
            conflicting["hash"] = "f" * 64
            try:
                opened.store.insert_event(conflicting)
                raise AssertionError("conflicting event mirror retry was accepted")
            except StoreError:
                pass

            # Payloads above the hard 1 MiB bound fail before the spine moves.
            head_before_huge = opened.spine.head()[0]
            huge = api.make_event(
                ctx, "message", {"text": "y" * (1024 * 1024 + 1)},
                scope="test:final-recovery", sensitivity="sensitive",
                taint="user_direct")
            try:
                api.spine_append(opened.spine, huge, opened.store)
                raise AssertionError("oversized payload unexpectedly appended")
            except api.ApiError as exc:
                assert exc.code == "too_large"
            assert opened.spine.head()[0] == head_before_huge

            # A pre-append writer failure cleans up the newly encrypted blob
            # and its wrapped key rather than leaving orphaned sensitive data.
            class FailingSpine:
                def append(self, _event):
                    raise OSError("intentional final-test append failure")

                def iter_events(self):
                    return iter(())

                def head(self):
                    return opened.store.head_seq(), "0" * 64

            failing = api.make_event(
                ctx, "message", {"text": "cleanup probe"},
                scope="test:final-recovery", sensitivity="sensitive",
                taint="user_direct")
            try:
                api.spine_append(FailingSpine(), failing, opened.store)
                raise AssertionError("failing spine unexpectedly appended")
            except OSError:
                pass
            orphan_key = opened.store.conn.execute(
                "SELECT 1 FROM record_keys WHERE record_id = ?", (failing["id"],)).fetchone()
            orphan_blob = opened.store.conn.execute(
                "SELECT 1 FROM payload_store WHERE sha256 = ?",
                (failing.get("payload_ref"),)).fetchone()
            assert orphan_key is None and orphan_blob is None

            assert opened.store.head_seq() == opened.spine.head()[0]
            report = {"result": "PASS", "recovered_event": legacy["id"],
                      "payload_ref": row["payload_ref"],
                      "spine_head": opened.spine.head()[0],
                      "sqlite_head": opened.store.head_seq()}
        finally:
            opened.store.close()
        print(json.dumps(report, indent=2))
    finally:
        shutil.rmtree(root, ignore_errors=False)


if __name__ == "__main__":
    main()
