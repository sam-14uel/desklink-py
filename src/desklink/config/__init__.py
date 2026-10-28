"""Configuration loading for DeskLink."""

import os
from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8765
    mcp_path: str = "/mcp"


class FilesystemConfig(BaseSettings):
    allowed_directories: List[Path] = Field(default_factory=lambda: [Path.home()])
    read_only: bool = False


class TunnelConfig(BaseSettings):
    provider: str = "ngrok"
    authtoken: Optional[str] = None


class AuthConfig(BaseSettings):
    enabled: bool = True
    token: Optional[str] = None
    token_file: Path = Path.home() / ".desklink" / "token"


class DeskLinkConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DESKLINK_", env_nested_delimiter="__")

    server: ServerConfig = Field(default_factory=ServerConfig)
    filesystem: FilesystemConfig = Field(default_factory=FilesystemConfig)
    tunnel: TunnelConfig = Field(default_factory=TunnelConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)

    def model_post_init(self, __context) -> None:
        # Pull ngrok token from env if not set
        if not self.tunnel.authtoken:
            self.tunnel.authtoken = os.getenv("NGROK_AUTHTOKEN")


def load_config(path: Optional[Path] = None) -> DeskLinkConfig:
    """Load configuration from env and optional file."""
    # Simple env-based loading for MVP; YAML support can be added later
    return DeskLinkConfig()
