# DeskLink

**Turn your local computer into a remotely accessible MCP endpoint for cloud AI agents.**

DeskLink is a thin authenticated bridge. It starts the local STDIO MCP servers you already use (or the official filesystem server), discovers their tools, and exposes everything through a single **Streamable HTTP** MCP URL. Optionally tunnels that URL with ngrok so Claude, ChatGPT, Cursor, Manus, or any remote MCP client can reach your machine securely.

Package name on PyPI: **`desklink`**  
CLI commands: `desklink` and `devlink` (alias)

---

## What it does

1. Loads MCP servers from a standard `mcp.json` (or injects the official `@modelcontextprotocol/server-filesystem` if none are defined).
2. Starts a local Streamable HTTP server (default `http://127.0.0.1:8765/mcp`).
3. Proxies every discovered tool under a namespaced name (`servername__toolname`).
4. Protects the endpoint with a device bearer token **and/or** OAuth 2.1 (Authorization Code + PKCE).
5. Optionally opens an ngrok tunnel so the same endpoint is reachable from the public internet.
6. Gives you a simple web dashboard + consent screen for OAuth apps.

You keep full control: tools stay on your machine, approvals can prompt you, and tokens never leave your machine unless you choose.

---

## Quick start

```bash
pip install desklink

# Optional but recommended for public tunnels
export NGROK_AUTHTOKEN=your_ngrok_token

desklink start
```

On first run DeskLink will:

- Create `~/.desklink/token` (device bearer token)
- Start the official filesystem MCP server scoped to your home directory (unless you provide an `mcp.json`)
- Print the **local** and **public** MCP URLs plus the auth token

Copy the public URL + token into any MCP-compatible client.

### Useful flags

```bash
desklink start \
  --mcp-config ./mcp.json \
  --config ./desklink.config.json \
  --dir ~/Documents --dir ~/projects \
  --port 8765 \
  --tunnel ngrok          # or "none" for local-only
  --token my-static-token # optional override
  -v                      # verbose logging
```

---

## Configuration

DeskLink looks for two files (first match wins):

| File | Search order |
|------|--------------|
| **DeskLink settings** | `--config` → `./desklink.config.json` → `~/.desklink/config.json` |
| **MCP servers** | `--mcp-config` → `./mcp.json` → `~/.desklink/mcp.json` |

### Example `mcp.json`

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/you/Documents", "/Users/you/projects"]
    },
    "my-custom-server": {
      "command": "python",
      "args": ["-m", "my_mcp_server"],
      "env": { "API_KEY": "..." }
    }
  }
}
```

Any STDIO MCP server works. Tools appear as `filesystem__read_file`, `my-custom-server__do_something`, etc.

### Example `desklink.config.json`

```json
{
  "logging": { "level": "info" },
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
      "filesystem__create_directory": "prompt"
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

**Approvals**  
- `"auto"` – run immediately  
- `"prompt"` – ask in the terminal before the tool executes

**Tracing levels**  
- `none` / `basic` / `full` (full logs args + truncated results; sensitive keys are redacted by default)

Environment variables use the prefix `DESKLINK_` (e.g. `DESKLINK_SERVER__PORT=9000`). `NGROK_AUTHTOKEN` is also picked up automatically.

---

## Authentication

### 1. Device bearer token (always available)

Stored at `~/.desklink/token`. Sent as:

```
Authorization: Bearer <token>
```

Use this for simple scripts or clients that just need a static secret.

### 2. OAuth 2.1 (recommended for cloud agents)

DeskLink acts as a full OAuth 2.1 authorization server so agents never see your device token.

**Create an app (CLI)**

```bash
desklink create oauth-app claude
desklink create oauth-app chatgpt
desklink create oauth-app manus
desklink create oauth-app cursor
desklink create oauth-app custom --name "My Agent" --public
```

Presets come with sensible default scopes. Confidential clients get a Client Secret; public clients rely on PKCE.

**Endpoints (when `desklink start` is running)**

| Purpose | URL |
|---------|-----|
| Metadata | `http://127.0.0.1:8765/.well-known/oauth-authorization-server` |
| Authorize | `http://127.0.0.1:8765/oauth/authorize` |
| Token | `http://127.0.0.1:8765/oauth/token` |
| Revoke | `http://127.0.0.1:8765/oauth/revoke` |
| Dynamic registration | `POST http://127.0.0.1:8765/oauth/register` |
| Dashboard | `http://127.0.0.1:8765/dashboard` |
| MCP | `http://127.0.0.1:8765/mcp` |

When using a tunnel the same paths work on the public URL.

**Manage apps**

```bash
desklink oauth list
desklink oauth revoke <client_id>
```

Or open `/dashboard` in a browser – create apps, view Client IDs, revoke access, and see recent activity.

**Scopes**

| Scope | Meaning |
|-------|---------|
| `mcp:tools` | Call tools |
| `mcp:resources` | Read resources |
| `filesystem:read` | Read files |
| `filesystem:write` | Write / create |
| `admin` | Full control |

All OAuth state lives as JSON under `~/.desklink/oauth/` (no database).

---

## Customer usage flow

1. Install & start DeskLink on the machine whose tools/files you want to expose.
2. (Optional) Create an OAuth app for the agent you will connect.
3. Give the agent the **public MCP URL** + either the device token or the OAuth Client ID (and secret if confidential).
4. The agent discovers tools via normal MCP `tools/list` and calls them. DeskLink proxies the call to the local STDIO server, applies your approval policy, and returns the result.
5. Stop with `Ctrl+C`. The tunnel and local servers shut down cleanly.

---

## Extensibility

- **Any STDIO MCP server** – just add it to `mcp.json`. No code changes required.
- **Approvals & tracing** – configure per-tool policies and log levels without touching the bridge.
- **Tunnel providers** – currently `ngrok` and `none`. The interface is abstract; additional providers (Cloudflare Tunnel, etc.) can be added later.
- **Auth** – static bearer + full OAuth 2.1 (PKCE, refresh tokens, dynamic registration, consent screen). Device identity stays separate from OAuth application credentials.
- **Programmatic use** – import `desklink` and drive `DeskLinkServer` / `McpBridge` from your own Python process if you need tighter integration.

---

## Development

```bash
git clone https://github.com/sam-14uel/desklink-py.git
cd desklink-py
pip install -e ".[dev]"
pytest
```

---

## License

MIT © Samuel Obinna Chimdi
