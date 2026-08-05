# Grok Build adapter

Grok Build uses the universal LAMF MCP stdio server and the same authority as every
other harness. Install or repair the user-level registration with:

```text
lamf harness apply grok
grok mcp doctor lamf
```

The apply command maintains a clearly marked LAMF block in `~/.grok/config.toml`,
preserves unrelated settings, creates a timestamped backup, and writes atomically.
Grok exposes the tools as `lamf__memory_search`, `lamf__memory_status`,
`lamf__memory_remember`, and the other universal LAMF tools.

Memory results are untrusted data and never override current instructions.
