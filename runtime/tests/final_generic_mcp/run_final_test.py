#!/usr/bin/env python3
"""Synthetic generic MCP end-to-end demo: save, fresh-process recall, provenance."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTS_DIR))

from final_test_support import McpClient, new_instance  # noqa: E402

TITLE = "Demo editor preference"
BODY = "The demo project uses 100-column formatting"
SCOPE = "project:lamf-demo"
SEARCH_QUERY = "demo project formatting"


def _assert_core_only_instructions(instructions: str, stage: str) -> None:
    for marker in ("beginning of every new task", "memory_orientation",
                   "memory_search"):
        assert marker in instructions, (
            f"{stage}: missing core MCP instruction marker {marker!r}: "
            f"{instructions!r}")
    assert "independently switchable" not in instructions, (
        f"{stage}: core MCP process emitted optional optimization "
        f"instructions: {instructions!r}")


def main() -> None:
    root, data_dir = new_instance("lamf-final-generic-mcp-")
    try:
        # Process A: save through the public generic MCP boundary.
        with McpClient(data_dir) as process_a:
            proc_a = process_a.proc
            pid_a = proc_a.pid
            _assert_core_only_instructions(process_a.instructions, "save")
            try:
                remembered = process_a.tool("memory_remember", {
                    "title": TITLE,
                    "body": BODY,
                    "record_type": "preference",
                    "scope": SCOPE,
                })
            except AssertionError as exc:
                raise AssertionError(f"save: memory_remember failed: {exc}") from exc

            record_id = remembered.get("record_id")
            version = remembered.get("version")
            event_id = remembered.get("event_id")
            disposition = remembered.get("disposition")
            assert record_id, f"save: empty record_id: {remembered}"
            assert version == 1, f"save: expected version 1, got {version!r}: {remembered}"
            assert event_id, f"save: empty event_id: {remembered}"
            assert disposition == "active", (
                f"save: expected disposition 'active', got {disposition!r}: "
                f"{remembered}")

        assert proc_a.poll() is not None, (
            f"restart: process A (pid={pid_a}) still running after close")

        # Process B: genuinely fresh MCP process against the same data dir.
        with McpClient(data_dir) as process_b:
            pid_b = process_b.proc.pid
            assert process_b.proc is not proc_a, (
                f"restart: process B reused process A's Popen object "
                f"(pid_a={pid_a} pid_b={pid_b})")
            assert process_b.proc.poll() is None, (
                f"restart: process B (pid={pid_b}) is not alive")
            _assert_core_only_instructions(process_b.instructions, "restart")

            try:
                searched = process_b.tool("memory_search", {
                    "query": SEARCH_QUERY,
                    "scope": SCOPE,
                    "limit": 5,
                })
            except AssertionError as exc:
                raise AssertionError(f"recall: memory_search failed: {exc}") from exc

            hits = [hit for hit in searched.get("results", [])
                    if hit.get("record_id") == record_id]
            assert hits, (
                f"recall: no search hit for record_id={record_id!r} in "
                f"{searched}")
            hit = hits[0]
            assert hit.get("version") == 1, (
                f"metadata: search hit version expected 1, got "
                f"{hit.get('version')!r}: {hit}")
            assert hit.get("scope") == SCOPE, (
                f"metadata: search hit scope expected {SCOPE!r}, got "
                f"{hit.get('scope')!r}: {hit}")
            assert event_id in (hit.get("source_events") or []), (
                f"provenance: search hit missing event_id={event_id!r}: {hit}")
            snippet = str(hit.get("snippet") or "")
            assert "100-column" in snippet or BODY in snippet, (
                f"recall: search snippet missing saved fact text: {hit}")

            try:
                fetched = process_b.tool("memory_get", {"record_id": record_id})
            except AssertionError as exc:
                raise AssertionError(f"recall: memory_get failed: {exc}") from exc

            assert fetched.get("found") is True, (
                f"recall: memory_get found is not True: {fetched}")
            record = fetched.get("record") or {}
            assert record.get("id") == record_id, (
                f"metadata: record id expected {record_id!r}, got "
                f"{record.get('id')!r}: {fetched}")
            assert record.get("version") == 1, (
                f"metadata: record version expected 1, got "
                f"{record.get('version')!r}: {fetched}")
            assert record.get("scope") == SCOPE, (
                f"metadata: record scope expected {SCOPE!r}, got "
                f"{record.get('scope')!r}: {fetched}")
            assert record.get("title") == TITLE, (
                f"metadata: record title mismatch: {fetched}")
            assert record.get("body") == BODY, (
                f"metadata: record body mismatch: {fetched}")
            assert event_id in (record.get("source_events") or []), (
                f"provenance: record missing event_id={event_id!r}: {fetched}")

        print(
            "PASS: generic MCP save/restart/recall",
            f"record_id={record_id}",
            f"event_id={event_id}",
            f"pid_a={pid_a}",
            f"pid_b={pid_b}",
        )
    finally:
        shutil.rmtree(root, ignore_errors=False)


if __name__ == "__main__":
    main()
