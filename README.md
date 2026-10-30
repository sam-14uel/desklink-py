# DeskLink

Turn your local computer into a remotely accessible **MCP endpoint** for cloud AI agents.

DeskLink is a thin authenticated bridge: it loads local MCP servers (especially STDIO servers defined in a standard `mcp.json`), discovers their tools, and exposes all of them through a single Streamable HTTP URL (optionally tunnelled with ngrok).

## Quick start

```bash
pip install desklink
# Optional: export NGROK_AUTHTOKEN=your_token
desklink start
```

## OAuth 2.1 for remote agents

DeskLink can act as an OAuth 2.1 authorization server so cloud MCP clients (Claude, ChatGPT, Manus, Cursor, etc.) can obtain scoped access without sharing the device bearer token. Existing bearer-token authentication continues to work.

### Create an app (no lengthy forms)

```bash
desklink create oauth-app claude
desklink create oauth-app chatgpt
desklink create oauth-app manus
desklink create oauth-app cursor
# or
devlink create oauth-app claude
```

This generates a Client ID (and secret for confidential clients), selects a preset of sensible scopes, and prints the authorization, token, and MCP URLs. Redirect URIs are optional. Public clients and dynamically registered callback URLs are supported.

### Endpoints (when `desklink start` is running)

| Endpoint | URL |
|----------|-----|
| Metadata | `http://127.0.0.1:8765/.well-known/oauth-authorization-server` |
| Authorize | `http://127.0.0.1:8765/oauth/authorize` |
| Token | `http://127.0.0.1:8765/oauth/token` |
| Revoke | `http://127.0.0.1:8765/oauth/revoke` |
| Register | `POST http://127.0.0.1:8765/oauth/register` |
| Dashboard | `http://127.0.0.1:8765/dashboard` |
| MCP | `http://127.0.0.1:8765/mcp` |

### Manage apps

```bash
desklink oauth list
desklink oauth revoke <client_id>
```

### Web dashboard and consent

- Open `/dashboard` while DeskLink is running to create apps, view Client IDs, manage scopes, revoke access, and see recent activity.
- Agents that start an Authorization Code + PKCE flow are shown a consent screen listing the agent, requested scopes, and permissions. Users can approve or deny.

### Scopes

`mcp:tools`, `mcp:resources`, `filesystem:read`, `filesystem:write`, `admin`.

Device identity (`~/.desklink/token`) stays separate from OAuth application credentials. All OAuth data is stored as JSON under `~/.desklink/oauth/` (no database).

## Adding MCP servers

DeskLink supports any STDIO MCP server. Define them in a standard `mcp.json`.

## Configuration

See `examples/` for `desklink.config.json` and `mcp.json` samples.
