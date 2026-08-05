#!/usr/bin/env python3
"""Show sensitive remember -> search -> get -> context recall through MCP."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTS_DIR))

from final_test_support import McpClient, new_instance  # noqa: E402


def main():
    root, data_dir = new_instance("lamf-final-recall-")
    phrase = "FINAL-RECALL-COMET-58317"
    transcript = []
    try:
        with McpClient(data_dir) as client:
            remembered = client.tool("memory_remember", {
                "title": "Final recall comet",
                "body": f"Recall phrase: {phrase}", "record_type": "preference",
                "scope": "test:final-recall", "sensitivity": "sensitive",
                "tags": ["final-test", "recall"]})
            transcript.append({"step": "remember", "result": remembered})

            searched = client.tool("memory_search", {
                "query": phrase, "scope": "test:final-recall",
                "sensitivity_max": "sensitive", "limit": 5})
            assert any(hit["record_id"] == remembered["record_id"]
                       and phrase in hit["snippet"] for hit in searched["results"])
            transcript.append({"step": "search", "result": searched})

            fetched = client.tool("memory_get", {"record_id": remembered["record_id"]})
            assert fetched["found"] and phrase in fetched["record"]["body"]
            transcript.append({"step": "get", "result": fetched})

            context = client.tool("memory_context", {
                "purpose": phrase, "scopes": ["test:final-recall"],
                "max_tokens": 500, "sensitivity_max": "sensitive"})
            assert phrase in json.dumps(context, ensure_ascii=False)
            transcript.append({"step": "context", "result": context})

        print(json.dumps({"result": "PASS", "recall_process": transcript},
                         ensure_ascii=False, indent=2))
    finally:
        shutil.rmtree(root, ignore_errors=False)


if __name__ == "__main__":
    main()
