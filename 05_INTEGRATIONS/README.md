# Agent harness integrations

All harnesses use the shared [Parallel Agent Write Protocol](PARALLEL_AGENT_PROTOCOL.md)
for FIFO resource claims, visible waiting positions, leases, fencing, and
conflict-safe memory revision.

Start with `HARNESS_ADAPTER_CONTRACT.md`. Generate a registration for any supported
client with:

```text
lamf harness list
lamf harness emit codex
lamf harness emit claude
lamf harness emit kimi
lamf harness emit grok
lamf harness apply grok
lamf harness emit openclaw
lamf harness emit hermes
lamf harness apply hermes
lamf harness doctor
```

All generated registrations launch the same `runtime/lamf_mcp.py` process and point
at the same `LAMF_DATA_DIR`. The OpenClaw native plugin remains an optional enhanced
adapter; it is no longer the architectural center of LAMF.
