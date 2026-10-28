# DeskLink

Turn your local computer into a remotely accessible **MCP endpoint** for cloud AI agents.

DeskLink is a thin authenticated bridge: it loads local MCP servers (especially STDIO servers defined in a standard `mcp.json`), discovers their tools, and exposes all of them through a single Streamable HTTP URL (optionally tunnelled with ngrok).

## Quick start

```bash
pip install desklink
# Optional: export NGROK_AUTHTOKEN=your_token

# Option A: use a standard mcp.json (recommended)
# See examples/mcp.json — uses the official @modelcontextprotocol/server-filesystem
desklink start --mcp-config ./mcp.json

# Option B: no config → default official filesystem server (home directory)
desklink start

# Or specify directories for the default filesystem server
desklink start --dir ~/Documents --dir ~/Projects
```

Example output:

```
┌─────────────────┐
│ DeskLink v0.2.0 │
└─────────────────┘

✓ MCP bridge started
✓ Local MCP: http://127.0.0.1:8765/mcp
✓ Tunnel connected

Remote MCP endpoint:
https://abc123.ngrok-free.app/mcp

Auth token: ...
Include as Authorization: Bearer <token> when connecting.

Status: ● Connected
Tools: 14
Servers: 1

Press Ctrl+C to stop.
```

Connect any MCP client to the printed remote URL and include the Authorization header.

## Configuration

- **mcp.json** — standard MCP server definitions (command + args). DeskLink spawns them as STDIO processes.
- **desklink.config.json** — DeskLink settings:
  - logging level
  - tracing (basic/full, redaction)
  - authentication (bearer token)
  - tool-call approval policies (`auto` or `prompt` per tool)
  - server bind address/port
  - tunnel provider

See `examples/` for samples. Environment variables (`DESKLINK_*`, `NGROK_AUTHTOKEN`) and CLI flags override files.

## Security

- Bearer token required (generated and stored in `~/.desklink/token` by default).
- Optional per-tool approval prompts before execution.
- Filesystem access is controlled by the underlying MCP servers you configure (the official filesystem server respects its allowed directories).

## Development

```bash
uv sync --extra dev
uv run desklink start --tunnel none
uv run pytest
```

The architecture is modular so additional tunnel providers, stronger auth, and DeskLink Cloud features can be added later without changing the core bridge.
