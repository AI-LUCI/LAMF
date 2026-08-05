# Hermes Agent adapter

Hermes uses the universal LAMF MCP stdio server and the same authority as every
other harness. Install or repair its registration with:

```text
lamf harness apply hermes
```

This idempotently merges a `lamf` entry into `~/.hermes/config.yaml`, preserves all
unrelated settings, creates a timestamped backup, and writes atomically. Hermes
registers the tools with names such as `mcp_lamf_memory_search`.

Restart Hermes, then ask it to call `mcp_lamf_memory_status`. Use
`mcp_lamf_memory_search`, `mcp_lamf_memory_get`, `mcp_lamf_memory_remember`, and
`mcp_lamf_memory_context` for normal memory work. Returned memory is untrusted data,
never authority or instructions.
