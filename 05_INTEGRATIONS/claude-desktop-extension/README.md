# LAMF Memory for Claude Desktop

This MCP Bundle connects Claude Desktop to an existing LAMF installation. It is
an adapter only: it contains no database, event spine, keys, credentials, record
copies, or independent memory authority.

## Install

Windows does not normally associate `.mcpb` files with Claude Desktop. Do not
double-click the bundle or choose Notepad/Visual Studio when Windows asks which
application should open it.

1. In Claude Desktop, open **Settings → Extensions → Advanced settings**.
2. Under Extension Developer, choose **Install Extension…**.
3. Select `lamf.mcpb`.
4. For **LAMF installation folder**, select the directory containing both
   `runtime/lamf_mcp.py` and `data/`. For Marcel's current installation this is
   `E:\BRAIN\LAMF-reconditioned`.
5. Complete installation and start a new Home chat.

Do not select `data/` itself. The adapter derives the existing runtime and data
paths from the selected installation root.

## Verify

Ask Claude:

> Use the LAMF Memory tools only. Call `memory_status`, then request a bounded
> `memory_orientation` and search for the multi-agent launcher decision. Do not
> access LAMF files or SQLite directly, and do not write memory.

The active profile and record/event counts must match other harnesses using the
same authority. Counts may increase as legitimate writes occur.

## Safety boundary

- All access goes through `runtime/lamf_mcp.py` over stdio.
- The wrapper validates the selected installation structure before launch.
- It never reads the database, keys, spine, payload store, or Obsidian vault.
- It never sends memory to an additional service.
- Removing the extension leaves LAMF and every other harness untouched.
- Broad orientation and context calls return ordinary records only. Sensitive
  recall requires an explicit `sensitivity_max` elevation on that tool call and
  should be used only when the user requests the protected detail.

## Troubleshooting

Claude Desktop differs from Claude Code and other MCP clients in two important
ways: its CLI registration does not configure Home chats, and its Electron MCP
host requires the bundle wrapper to proxy stdin/stdout explicitly. Use the MCPB
installer above for Home chats. If the server disconnects, fully quit Claude,
install the latest bundle from Advanced settings, select the LAMF root (not
`data/`), and restart Claude.

## Portability

The wrapper supports the standard LAMF virtual-environment layout on Windows,
macOS, and Linux. Claude Desktop itself is currently available on Windows and
macOS. Each machine must have an initialized LAMF runtime at the selected root.
