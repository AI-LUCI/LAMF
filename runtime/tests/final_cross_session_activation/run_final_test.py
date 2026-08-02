#!/usr/bin/env python3
"""Prove a record written by one MCP process is recalled by a fresh process."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTS_DIR))

from final_test_support import McpClient, new_instance  # noqa: E402


def main() -> None:
    root, data_dir = new_instance("lamf-final-cross-session-")
    marker = "FINAL-CROSS-SESSION-ORBIT-7319"
    try:
        # Chat A: deploy through the real MCP write path, then fully exit.
        with McpClient(data_dir) as chat_a:
            remembered = chat_a.tool("memory_remember", {
                "title": "Cross-session orbit marker",
                "body": f"Cross-session marker: {marker}",
                "record_type": "fact", "scope": "test:cross-session",
                "sensitivity": "sensitive", "tags": ["final-test"]})

        # Chat B: a distinct OS process must discover and recall Chat A's record.
        with McpClient(data_dir) as chat_b:
            found = chat_b.tool("memory_search", {
                "query": marker, "scope": "test:cross-session",
                "sensitivity_max": "sensitive", "limit": 5})
            assert any(item["record_id"] == remembered["record_id"]
                       and marker in item["snippet"]
                       for item in found["results"])
            exact = chat_b.tool("memory_get", {
                "record_id": remembered["record_id"]})
            assert exact["found"] and marker in exact["record"]["body"]

        print("PASS: independent chat processes persisted and recalled", marker)
    finally:
        shutil.rmtree(root, ignore_errors=False)


if __name__ == "__main__":
    main()
