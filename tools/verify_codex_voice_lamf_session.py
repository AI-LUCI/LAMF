#!/usr/bin/env python3
"""Verify one real post-fix Codex realtime-voice session used LAMF."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-home", type=Path,
                        default=Path.home() / ".codex")
    parser.add_argument("--after", required=True,
                        help="Only accept voice sessions at/after this ISO timestamp")
    parser.add_argument("--expect-recalled", action="append", default=[])
    parser.add_argument("--expect-remembered", required=True)
    args = parser.parse_args()

    after = parse_time(args.after)
    roots = [args.codex_home / "sessions", args.codex_home / "archived_sessions"]
    candidates: list[tuple[datetime, Path, list[dict]]] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            rows = load_jsonl(path)
            if not rows:
                continue
            payload = rows[0].get("payload", {})
            if (rows[0].get("type") != "session_meta"
                    or payload.get("thread_source") != "realtime_voice"):
                continue
            started = parse_time(payload["timestamp"])
            if started >= after:
                candidates.append((started, path, rows))

    require(candidates, f"no realtime_voice session found after {args.after}")
    started, path, rows = max(candidates, key=lambda item: item[0])
    meta = rows[0]["payload"]
    require(meta.get("originator") == "Codex Desktop",
            "voice session was not created by Codex Desktop")
    require(Path(meta.get("cwd", "")).is_absolute(),
            "voice session did not run against a local absolute workspace")

    calls: list[dict] = []
    for row in rows:
        payload = row.get("payload", {})
        if (row.get("type") == "event_msg"
                and payload.get("type") == "mcp_tool_call_end"):
            invocation = payload.get("invocation", {})
            if invocation.get("server") == "lamf-memory":
                require("Ok" in payload.get("result", {}),
                        f"LAMF voice tool failed: {payload.get('result')}")
                calls.append(invocation)

    tools = [call.get("tool") for call in calls]
    require("memory_orientation" in tools,
            "voice session did not perform startup orientation")
    require("memory_search" in tools,
            "voice session did not recall through memory_search")
    require("memory_remember" in tools,
            "voice session did not persist through memory_remember")

    serialized = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    for expected in args.expect_recalled:
        require(expected.casefold() in serialized.casefold(),
                f"expected recalled value absent from voice evidence: {expected}")
    remember_calls = [call for call in calls if call.get("tool") == "memory_remember"]
    require(any(args.expect_remembered.casefold() in
                json.dumps(call.get("arguments", {}), ensure_ascii=False).casefold()
                for call in remember_calls),
            "voice memory_remember did not contain the expected phrase")

    print("PASS: realtime voice used LAMF orientation, recall, and persistence")
    print(f"session: {meta.get('session_id')}")
    print(f"started: {started.isoformat()}")
    print(f"evidence: {path}")


if __name__ == "__main__":
    main()
