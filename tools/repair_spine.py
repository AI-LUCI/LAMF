#!/usr/bin/env python3
"""Quarantine an invalid Witness Spine suffix and restore the valid prefix.

Dry-run by default. ``--apply`` preserves every removed byte under
``<data-dir>/quarantine/`` before truncating the authority and reconciles the
SQLite event mirror. Records that cite quarantined events are reported but are
not silently deleted.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from lamf.cli import _open_ctx  # noqa: E402
from lamf.spine import GENESIS_PREV_HASH, Spine  # noqa: E402


def inspect(ctx):
    valid = []
    invalid = []
    prev = GENESIS_PREV_HASH
    expect = 1
    broken = False
    for segment in ctx.spine._segments():
        with open(segment, "rb") as source:
            offset = 0
            for raw in source:
                end = offset + len(raw)
                if not raw.strip():
                    offset = end
                    continue
                event = json.loads(raw.decode("utf-8"))
                error, _ = ctx.spine._verify_event(event, expect, prev)
                if broken or error:
                    broken = True
                    invalid.append((segment, offset, end, raw, event, error))
                else:
                    valid.append((segment, offset, end, raw, event))
                    prev = event["hash"]
                    expect += 1
                offset = end
    return valid, invalid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    data_dir = Path(args.data_dir).resolve()
    ctx = _open_ctx(data_dir)
    valid, invalid = inspect(ctx)
    report = {
        "valid_events": len(valid), "invalid_events": len(invalid),
        "first_invalid": invalid[0][4].get("id") if invalid else None,
        "first_error": invalid[0][5] if invalid else None,
        "applied": False, "quarantine": None, "orphan_records": [],
    }
    if not invalid or not args.apply:
        print(json.dumps(report, indent=2))
        return 1 if invalid else 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    quarantine = data_dir / "quarantine" / f"spine-invalid-suffix-{stamp}"
    quarantine.mkdir(parents=True, exist_ok=False)
    invalid_ids = {item[4]["id"] for item in invalid}

    # Preserve complete affected segments and the exact invalid suffix.
    affected = []
    for segment, *_ in invalid:
        if segment not in affected:
            affected.append(segment)
    for segment in affected:
        shutil.copy2(segment, quarantine / segment.name)
    with open(quarantine / "invalid-events.jsonl", "wb") as out:
        for item in invalid:
            out.write(item[3])
    (quarantine / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")

    # Rewrite the event directory from the verified prefix, preserving normal
    # segment names and using atomic replacement for every surviving segment.
    by_segment = {}
    for segment, _start, _end, raw, _event in valid:
        by_segment.setdefault(segment, []).append(raw)
    for segment in ctx.spine._segments():
        lines = by_segment.get(segment, [])
        if lines:
            tmp = segment.with_suffix(segment.suffix + ".repair.tmp")
            with open(tmp, "wb") as out:
                out.writelines(lines)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, segment)
        else:
            segment.unlink()

    # Reconcile only the disposable SQLite event mirror. The quarantined copy
    # remains recoverable and referenced in the report.
    with ctx.store.conn:
        ctx.store.conn.executemany(
            "DELETE FROM events WHERE id = ?", [(event_id,) for event_id in invalid_ids])
        ctx.store.conn.execute(
            "UPDATE ingester_state SET high_water_seq = ?, updated_ts = ? WHERE id = 1",
            (len(valid), int(time.time() * 1000)))

    for row in ctx.store.conn.execute(
            "SELECT id, source_events FROM records WHERE state = 'active'"):
        try:
            refs = set(json.loads(row["source_events"] or "[]"))
        except ValueError:
            refs = set()
        if refs & invalid_ids:
            report["orphan_records"].append(row["id"])

    repaired = Spine(data_dir / "events", instance_key=ctx.instance_key)
    if not repaired.verify_deep():
        raise RuntimeError("repair did not produce a valid deep chain")
    report.update({"applied": True, "quarantine": str(quarantine),
                   "repaired_head": repaired.head()[0]})
    (quarantine / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
