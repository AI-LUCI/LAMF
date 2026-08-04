"""Shared helpers for deploy-level LAMF final tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = PACKAGE_ROOT / "runtime"
MCP_ENTRY = RUNTIME_DIR / "lamf_mcp.py"
TEST_RUN_ROOT = PACKAGE_ROOT / ".test-runs"


def new_instance(prefix: str):
    TEST_RUN_ROOT.mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix=prefix, dir=TEST_RUN_ROOT))
    data_dir = root / "data"
    proc = subprocess.run(
        [sys.executable, "-m", "lamf.cli", "init", "--profile", "controlled",
         "--data-dir", str(data_dir)],
        cwd=RUNTIME_DIR, text=True, capture_output=True, timeout=30)
    if proc.returncode:
        raise AssertionError(f"LAMF init failed:\n{proc.stdout}\n{proc.stderr}")
    return root, data_dir


class McpClient:
    def __init__(self, data_dir: Path):
        env = os.environ.copy()
        env["LAMF_DATA_DIR"] = str(data_dir)
        env["PYTHONUTF8"] = "1"
        self.proc = subprocess.Popen(
            [sys.executable, str(MCP_ENTRY)], cwd=RUNTIME_DIR, env=env,
            text=True, encoding="utf-8", stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1)
        init = self.request("initialize", {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "lamf-final-test", "version": "1"}})
        assert init["result"]["serverInfo"]["name"] == "lamf"
        instructions = init["result"].get("instructions", "")
        assert "beginning of every new task" in instructions
        assert "memory_orientation" in instructions
        assert "memory_search" in instructions
        self.instructions = instructions
        self.notify("notifications/initialized", {})

    def _send(self, message: dict):
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: dict):
        request_id = getattr(self, "_request_id", 0) + 1
        self._request_id = request_id
        self._send({"jsonrpc": "2.0", "id": request_id,
                    "method": method, "params": params})
        assert self.proc.stdout is not None
        line = self.proc.stdout.readline()
        if not line:
            stderr = self.proc.stderr.read() if self.proc.stderr else ""
            raise AssertionError(f"MCP process exited without a response: {stderr}")
        response = json.loads(line)
        if "error" in response:
            raise AssertionError(f"MCP request failed: {response['error']}")
        return response

    def notify(self, method: str, params: dict):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def tool(self, name: str, arguments: dict):
        response = self.request("tools/call", {"name": name, "arguments": arguments})
        result = response["result"]
        if result.get("isError"):
            raise AssertionError(f"MCP tool failed: {result}")
        text_blocks = [item["text"] for item in result.get("content", [])
                       if item.get("type") == "text"]
        if not text_blocks:
            raise AssertionError(f"MCP tool returned no text content: {result}")
        return json.loads(text_blocks[0])

    def close(self):
        if self.proc.stdin:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            self.proc.wait(timeout=5)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
