#!/usr/bin/env python3
"""Verify that a Codex home will activate LAMF in every fresh local session."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tomllib
from pathlib import Path


AUTO_APPROVED_TOOLS = {
    "memory_search", "memory_get", "memory_remember", "memory_context",
    "memory_orientation", "memory_handoff", "memory_status",
}
ALL_TOOLS = AUTO_APPROVED_TOOLS | {"memory_approvals", "memory_export"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-home", type=Path,
                        default=Path.home() / ".codex")
    args = parser.parse_args()
    home = args.codex_home.resolve()

    config_path = home / "config.toml"
    require(config_path.is_file(), f"missing {config_path}")
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    server = config.get("mcp_servers", {}).get("lamf-memory")
    require(isinstance(server, dict), "missing [mcp_servers.lamf-memory]")
    require(server.get("enabled") is True, "LAMF MCP is not explicitly enabled")
    require(server.get("required") is True, "LAMF MCP is not required at startup")
    require(server.get("default_tools_approval_mode") == "prompt",
            "operator-only tools must remain approval-gated by default")

    command = Path(server.get("command", ""))
    launch_args = [str(value) for value in server.get("args", [])]
    require(command.is_file(), f"MCP command does not exist: {command}")
    require(launch_args and Path(launch_args[0]).is_file(),
            "LAMF MCP entry point is missing")
    cwd = Path(server.get("cwd", ""))
    require(cwd.is_dir(), f"LAMF MCP working directory is missing: {cwd}")
    data_dir = Path(server.get("env", {}).get("LAMF_DATA_DIR", ""))
    require((data_dir / "lamf.db").is_file(),
            f"LAMF data directory is not initialized: {data_dir}")

    tool_config = server.get("tools", {})
    for name in AUTO_APPROVED_TOOLS:
        require(tool_config.get(name, {}).get("approval_mode") == "approve",
                f"{name} is not pre-approved for unattended local recall")
    for name in ("memory_approvals", "memory_export"):
        require(tool_config.get(name, {}).get("approval_mode") != "approve",
                f"operator-only tool {name} must not be pre-approved")

    guidance = (home / "AGENTS.md").read_text(encoding="utf-8")
    require("At the beginning of every new chat or task" in guidance,
            "global AGENTS.md lacks startup recall guidance")
    require("realtime voice chats" in guidance,
            "global AGENTS.md does not explicitly cover voice chats")
    require("query LAMF before answering" in guidance,
            "global AGENTS.md lacks explicit personal-memory recall guidance")
    require("transcript_delta" in guidance
            and "correct any inaccurate frontend answer" in guidance,
            "global AGENTS.md lacks realtime voice transcript recovery guidance")
    require("harmless verification phrase" in guidance,
            "global AGENTS.md lacks safe voice persistence-test guidance")
    skill = (home / "skills" / "lamf-memory" / "SKILL.md")
    require(skill.is_file() and "name: lamf-memory" in skill.read_text(encoding="utf-8"),
            "global lamf-memory skill is missing or invalid")

    env = os.environ.copy()
    env.update({str(key): str(value)
                for key, value in server.get("env", {}).items()})
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "codex-activation-verifier", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    proc = subprocess.run(
        [str(command), *launch_args],
        input=("\n".join(json.dumps(item) for item in requests) + "\n").encode("utf-8"),
        capture_output=True, env=env,
        cwd=str(cwd), timeout=30)
    require(proc.returncode == 0,
            "LAMF MCP handshake failed: "
            + proc.stderr.decode("utf-8", errors="replace").strip()[:500])
    output = proc.stdout.decode("utf-8", errors="replace")
    replies = {item["id"]: item for item in
               (json.loads(line) for line in output.splitlines())
               if item.get("id") is not None}
    require(set(replies) == {1, 2}, f"incomplete MCP replies: {sorted(replies)}")

    initialized = replies[1]["result"]
    instructions = initialized.get("instructions", "")
    require("beginning of every new task" in instructions,
            "MCP server-wide startup instructions are absent")
    require("realtime voice sessions" in instructions,
            "MCP server-wide instructions do not explicitly cover voice")
    require("memory_orientation" in instructions and "memory_search" in instructions,
            "MCP instructions do not require bounded orientation and search")

    tools = {item["name"]: item for item in replies[2]["result"]["tools"]}
    require(set(tools) == ALL_TOOLS,
            f"unexpected MCP tool set: {sorted(tools)}")
    for name, tool in tools.items():
        annotations = tool.get("annotations", {})
        require({"readOnlyHint", "destructiveHint", "openWorldHint"}
                <= set(annotations), f"missing action annotations for {name}")

    print("PASS: Codex global LAMF activation is required, instructed, "
          "approval-safe, and live")


if __name__ == "__main__":
    main()
