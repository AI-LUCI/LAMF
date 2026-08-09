"""Deterministic tests for ephemeral active-work awareness."""
from pathlib import Path
from types import SimpleNamespace

from lamf import mcp_server


def ctx(root: Path, agent: str):
    return SimpleNamespace(data_dir=root, coordination_id=agent,
                           actor="lamf-operator", policy=None,
                           spine=None, store=None)


def run():
    import tempfile
    with tempfile.TemporaryDirectory(prefix="lamf-activity-test-") as tmp:
        root = Path(tmp)
        clock = [1_000_000]
        original_now = mcp_server._now_ms
        mcp_server._now_ms = lambda: clock[0]
        try:
            try:
                mcp_server.activity(ctx(root, "codex:secret-test"), {
                    "action": "register", "objective":
                    "Use sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456 for a benchmark"})
                raise AssertionError("secret-bearing activity succeeded")
            except mcp_server.ToolError as exc:
                assert exc.code == "policy_denied", exc.code
            first = mcp_server.activity(ctx(root, "codex:benchmark-a"), {
                "action": "register",
                "objective": "Build a universal benchmark platform for memory systems against LAMF",
                "project": "memory-benchmarks",
                "workspace": "Z:/Memory-Benchmarks",
                "concepts": ["universal benchmark", "memory systems", "LAMF"],
                "artifacts": ["contract:memory-benchmark-v1"],
                "progress": {"summary": "Adapter contract started"},
            })
            aid = first["activity"]["activity_id"]
            mcp_server.activity(ctx(root, "codex:benchmark-a"), {
                "action": "wait", "activity_id": aid,
                "requested_input": "Choose synthetic or imported fixtures."})

            clock[0] += mcp_server.ACTIVITY_WAIT_MS + 1
            second = mcp_server.activity(ctx(root, "claude:benchmark-b"), {
                "action": "register",
                "objective": "Create repeatable universal memory benchmarks for LAMF",
                "project": "memory-benchmarks",
                "concepts": ["memory benchmark", "LAMF"],
                "artifacts": ["contract:memory-benchmark-v1"],
            })
            assert second["overlap"] == "high", second
            assert second["recommended_action"] == "pause_and_reconcile", second
            assert "hand it off" in second["user_notice"], second
            match = second["matches"][0]
            assert match["activity_id"] == aid, second
            assert match["status"] == "paused_waiting_for_user", second
            assert match["requested_input"], second

            bid = second["activity"]["activity_id"]
            try:
                mcp_server.activity(ctx(root, "claude:benchmark-b"), {
                    "action": "transfer", "activity_id": aid,
                    "recipient_activity_id": bid})
                raise AssertionError("transfer without user approval succeeded")
            except mcp_server.ToolError as exc:
                assert exc.code == "approval_required", exc.code
            moved = mcp_server.activity(ctx(root, "claude:benchmark-b"), {
                "action": "transfer", "activity_id": aid,
                "recipient_activity_id": bid, "user_approved": True})
            assert moved["activity"]["status"] == "transferred", moved
            assert moved["recipient_activity"]["handoff_context"]["progress"][
                "summary"] == "Adapter contract started", moved
            cards = mcp_server.activity(ctx(root, "claude:benchmark-b"), {
                "action": "list", "include_history": True})["activities"]
            recipient = next(x for x in cards if x["activity_id"] == bid)
            assert recipient["transferred_from"] == aid, recipient
        finally:
            mcp_server._now_ms = original_now
    print("PASS: activity pause, overlap visibility, and approved transfer")


if __name__ == "__main__":
    run()
