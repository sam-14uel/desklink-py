"""Basic tests for DeskLink components."""

from pathlib import Path

import pytest

from desklink.auth import DeskLinkTokenVerifier, generate_token, load_or_create_token
from desklink.config import DeskLinkConfig
from desklink.filesystem import create_filesystem_server, is_path_allowed
from desklink.tunnel import get_tunnel_provider


def test_generate_token():
    t1 = generate_token()
    t2 = generate_token()
    assert len(t1) > 20
    assert t1 != t2


def test_load_or_create_token(tmp_path: Path):
    token_file = tmp_path / "token"
    token = load_or_create_token(token_file)
    assert token_file.read_text().strip() == token
    # Second call reuses
    assert load_or_create_token(token_file) == token


@pytest.mark.asyncio
async def test_token_verifier():
    token = "test-token-123"
    verifier = DeskLinkTokenVerifier(token)
    result = await verifier.verify_token(token)
    assert result is not None
    assert result.token == token
    assert await verifier.verify_token("wrong") is None


def test_is_path_allowed(tmp_path: Path):
    allowed = [tmp_path]
    inside = tmp_path / "subdir" / "file.txt"
    outside = tmp_path.parent / "outside.txt"
    assert is_path_allowed(inside, allowed)
    assert not is_path_allowed(outside, allowed)


def test_filesystem_server_creation(tmp_path: Path):
    mcp = create_filesystem_server([tmp_path], read_only=True)
    assert mcp is not None
    # Tools should exist
    tools = list(mcp._tool_manager.list_tools())
    names = {t.name for t in tools}
    assert "list_directory" in names
    assert "read_file" in names
    assert "write_file" not in names  # read_only


def test_config_defaults():
    cfg = DeskLinkConfig()
    assert cfg.server.port == 8765
    assert cfg.tunnel.provider == "ngrok"
    assert cfg.auth.enabled is True


def test_tunnel_factory():
    assert get_tunnel_provider("none").__class__.__name__ == "NoTunnel"
    assert get_tunnel_provider("ngrok").__class__.__name__ == "NgrokTunnel"
    with pytest.raises(ValueError):
        get_tunnel_provider("unknown")
