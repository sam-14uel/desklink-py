# DeskLink

Turn your local computer into a remotely accessible **MCP endpoint** for cloud AI agents.

DeskLink is a thin authenticated bridge: it loads local MCP servers (especially STDIO servers defined in a standard `mcp.json`), discovers their tools, and exposes all of them through a single Streamable HTTP URL (optionally tunnelled with ngrok).

## Quick start

```bash
pip install desklink
# Optional: export NGROK_AUTHTOKEN=your_token

# Option A: use a standard mcp.json (recommended)
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

## Adding MCP servers

DeskLink supports any STDIO MCP server. Define them in a standard `mcp.json`:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/you/Documents"]
    },
    "git": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-git", "--repository", "/path/to/repo"]
    },
    "custom": {
      "command": "python",
      "args": ["my_server.py"],
      "env": { "DEBUG": "1" },
      "cwd": "/path/to/workdir"
    }
  }
}
```

Then:

```bash
desklink start --mcp-config ./mcp.json
```

If no `mcp.json` is found, DeskLink automatically starts the official `@modelcontextprotocol/server-filesystem` (controlled by `--dir` or home).

Tool names are namespaced as `servername__toolname` (e.g. `filesystem__list_directory`).

## Listing and testing tools

```bash
# List all discovered tools (no tunnel started)
desklink tools
desklink tools --mcp-config ./mcp.json

# Call a tool with arguments (for testing)

# Windows-friendly (recommended on cmd.exe):
desklink call filesystem__list_directory --arg path=C:\Users\User\Desktop
desklink call filesystem__list_allowed_directories

# JSON form (use double quotes on Windows):
desklink call filesystem__list_directory --args "{\"path\":\"C:\\Users\\User\\Desktop\"}"

# Or load args from a file:
desklink call filesystem__list_directory --args @args.json
```

Tool schemas match the original MCP server definitions. A synthetic `kwargs` wrapper is not added unless the upstream tool itself defines a `kwargs` parameter.

## Configuration: desklink.config.json

Create `desklink.config.json` (or `~/.desklink/config.json`) for DeskLink settings:

```json
{
  "logging": {
    "level": "info"
  },
  "tracing": {
    "enabled": true,
    "level": "basic",
    "redact_sensitive": true
  },
  "auth": {
    "enabled": true
  },
  "approvals": {
    "default": "auto",
    "tools": {
      "filesystem__write_file": "prompt",
      "filesystem__create_directory": "prompt",
      "git__commit": "prompt"
    }
  },
  "server": {
    "host": "127.0.0.1",
    "port": 8765,
    "mcp_path": "/mcp"
  },
  "tunnel": {
    "provider": "ngrok"
  }
}
```

### Full config options

| Section | Key | Values | Description |
|---------|-----|--------|-------------|
| `logging` | `level` | `debug`, `info`, `warning`, `error` | Log verbosity |
| `tracing` | `enabled` | `true` / `false` | Enable tool-call tracing |
| `tracing` | `level` | `none`, `basic`, `full` | `basic` = name + duration + error; `full` = + args + truncated result |
| `tracing` | `redact_sensitive` | `true` / `false` | Mask keys like password/token/secret/key |
| `auth` | `enabled` | `true` / `false` | Require Bearer token |
| `auth` | `token` | string | Override auto-generated token |
| `approvals` | `default` | `auto` / `prompt` | Default policy for all tools |
| `approvals` | `tools` | map of `namespaced_tool` → `auto`/`prompt` | Per-tool override |
| `server` | `host`, `port`, `mcp_path` | | Local bind settings |
| `tunnel` | `provider` | `ngrok`, `none` | Tunnel provider |

**Approval policies:**
- `auto` — tool calls execute immediately.
- `prompt` — DeskLink asks for confirmation in the terminal before executing the tool.

Environment variables (`DESKLINK_*`, `NGROK_AUTHTOKEN`) and CLI flags override the config file.

## Security

- Bearer token required (generated and stored in `~/.desklink/token` by default).
- Optional per-tool approval prompts before execution (`auto` or `prompt`).
- Filesystem (and other) access is controlled by the underlying MCP servers you configure.

## Development

```bash
uv sync --extra dev
uv run desklink start --tunnel none
uv run desklink tools
uv run pytest
```

The architecture is modular so additional tunnel providers, stronger auth, and DeskLink Cloud features can be added later without changing the core bridge.
