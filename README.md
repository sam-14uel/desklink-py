# DeskLink

Turn your local computer into a remotely accessible **MCP endpoint** for cloud AI agents.

DeskLink runs a secure local filesystem MCP server (Streamable HTTP) and exposes it through a temporary public tunnel (ngrok by default) so tools like Grok, Claude, or Cursor can access permitted directories on your machine.

## Quick start

```bash
pip install desklink
# Optional: export NGROK_AUTHTOKEN=your_token   # required for free ngrok
desklink start
```

Example output:

```
┌────────────────┐
│ DeskLink v0.1.0 │
└────────────────┘

✓ Filesystem MCP started
✓ Local MCP: http://127.0.0.1:8765/mcp
✓ Tunnel connected

Remote MCP endpoint:
https://abc123.ngrok-free.app/mcp

Status: ● Connected
Tools: 5

Press Ctrl+C to stop.
```

Connect your MCP client to the printed remote URL and include the Authorization header shown.

## Security

- Filesystem tools are restricted to explicitly allowed directories.
- A random Bearer token is generated (or reused) and required for all requests.
- Token is stored with restricted permissions in `~/.desklink/token`.
- DNS rebinding protection is disabled so public tunnels work; the Bearer token is the primary control.

## Development

```bash
uv sync --extra dev
uv run desklink start --tunnel none
uv run pytest
```

See `ARCHITECTURE.md` for module layout.
