"""Configuration loading for DeskLink.

Supports:
- desklink.config.json (DeskLink settings: auth, tracing, approvals, server, tunnel)
- mcp.json (standard MCP server definitions, STDIO by default)
- Environment variables and CLI overrides
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    mcp_path: str = "/mcp"


class TunnelConfig(BaseModel):
    provider: str = "ngrok"
    authtoken: Optional[str] = None


class AuthConfig(BaseModel):
    enabled: bool = True
    token: Optional[str] = None
    token_file: Path = Path.home() / ".desklink" / "token"


class TracingConfig(BaseModel):
    enabled: bool = True
    level: str = "basic"  # none | basic | full
    redact_sensitive: bool = True
    log_file: Optional[Path] = None


class ApprovalsConfig(BaseModel):
    default: str = "auto"  # auto | prompt
    tools: Dict[str, str] = Field(default_factory=dict)  # tool_name -> auto|prompt


class LoggingConfig(BaseModel):
    level: str = "info"


class DeskLinkSettings(BaseModel):
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    tracing: TracingConfig = Field(default_factory=TracingConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    approvals: ApprovalsConfig = Field(default_factory=ApprovalsConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    tunnel: TunnelConfig = Field(default_factory=TunnelConfig)


class McpServerConfig(BaseModel):
    command: str
    args: List[str] = Field(default_factory=list)
    env: Optional[Dict[str, str]] = None
    cwd: Optional[str] = None


class McpConfig(BaseModel):
    mcpServers: Dict[str, McpServerConfig] = Field(default_factory=dict)


class DeskLinkConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DESKLINK_", env_nested_delimiter="__")

    settings: DeskLinkSettings = Field(default_factory=DeskLinkSettings)
    mcp: McpConfig = Field(default_factory=McpConfig)

    def model_post_init(self, __context: Any) -> None:
        if not self.settings.tunnel.authtoken:
            self.settings.tunnel.authtoken = os.getenv("NGROK_AUTHTOKEN")


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_config(
    config_path: Optional[Path] = None,
    mcp_path: Optional[Path] = None,
) -> DeskLinkConfig:
    """Load DeskLink settings and mcp.json.

    Search order for desklink.config.json:
    - explicit path
    - ./desklink.config.json
    - ~/.desklink/config.json

    Search order for mcp.json:
    - explicit path
    - ./mcp.json
    - ~/.desklink/mcp.json
    """
    home = Path.home()
    candidates_config = [
        config_path,
        Path.cwd() / "desklink.config.json",
        home / ".desklink" / "config.json",
    ]
    candidates_mcp = [
        mcp_path,
        Path.cwd() / "mcp.json",
        home / ".desklink" / "mcp.json",
    ]

    settings_data = {}
    for p in candidates_config:
        if p and p.exists():
            settings_data = _load_json(p)
            break

    mcp_data = {}
    for p in candidates_mcp:
        if p and p.exists():
            mcp_data = _load_json(p)
            break

    settings = DeskLinkSettings.model_validate(settings_data) if settings_data else DeskLinkSettings()
    mcp = McpConfig.model_validate(mcp_data) if mcp_data else McpConfig()

    cfg = DeskLinkConfig(settings=settings, mcp=mcp)
    return cfg


def ensure_default_filesystem(cfg: DeskLinkConfig, dirs: Optional[List[Path]] = None) -> DeskLinkConfig:
    """If no MCP servers are configured, inject the official filesystem server.

    Uses npx @modelcontextprotocol/server-filesystem with the given directories
    (or home as fallback). This preserves the previous single-filesystem UX.
    """
    if cfg.mcp.mcpServers:
        return cfg

    allowed = [str(d) for d in (dirs or [Path.home()])]
    cfg.mcp.mcpServers["filesystem"] = McpServerConfig(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem"] + allowed,
    )
    return cfg
