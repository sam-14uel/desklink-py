"""Basic tests for DeskLink configuration and bridge setup."""

from pathlib import Path

from desklink.config import DeskLinkConfig, ensure_default_filesystem, load_config


def test_load_config_defaults():
    cfg = load_config()
    assert isinstance(cfg, DeskLinkConfig)
    assert cfg.settings.server.port == 8765
    assert cfg.settings.auth.enabled is True


def test_ensure_default_filesystem():
    cfg = DeskLinkConfig()
    assert not cfg.mcp.mcpServers
    cfg = ensure_default_filesystem(cfg, dirs=[Path("/tmp")])
    assert "filesystem" in cfg.mcp.mcpServers
    fs = cfg.mcp.mcpServers["filesystem"]
    assert fs.command == "npx"
    assert "@modelcontextprotocol/server-filesystem" in fs.args
    assert "/tmp" in fs.args


def test_no_overwrite_existing_servers():
    cfg = DeskLinkConfig()
    from desklink.config import McpServerConfig
    cfg.mcp.mcpServers["custom"] = McpServerConfig(command="echo", args=["hi"])
    cfg = ensure_default_filesystem(cfg)
    assert "custom" in cfg.mcp.mcpServers
    assert "filesystem" not in cfg.mcp.mcpServers
