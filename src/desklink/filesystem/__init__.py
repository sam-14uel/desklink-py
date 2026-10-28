"""Secure filesystem MCP tools restricted to configured directories.

This module implements the filesystem capabilities that DeskLink exposes.
It is intentionally modular so additional MCP servers (terminal, browser, git, etc.)
can be added alongside it later.
"""

from pathlib import Path
from typing import List, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings


def is_path_allowed(path: Path, allowed_dirs: List[Path]) -> bool:
    """Check if a resolved path is inside any allowed directory."""
    try:
        resolved = path.resolve()
        for allowed in allowed_dirs:
            try:
                resolved.relative_to(allowed.resolve())
                return True
            except ValueError:
                continue
        return False
    except Exception:
        return False


def create_filesystem_server(
    allowed_directories: List[Path],
    read_only: bool = False,
) -> FastMCP:
    """Create a FastMCP server exposing restricted filesystem tools.

    Args:
        allowed_directories: List of absolute paths the tools may access.
        read_only: If True, write/delete tools are omitted.

    Returns:
        A configured FastMCP instance.
    """
    # Disable DNS rebinding protection so public tunnels (ngrok, Cloudflare, etc.)
    # are accepted. Security is enforced by the Bearer token middleware instead.
    mcp = FastMCP(
        "DeskLink Filesystem",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
    )

    allowed = [p.resolve() for p in allowed_directories]

    @mcp.tool()
    def list_allowed_directories() -> List[str]:
        """Return the directories this server is allowed to access."""
        return [str(p) for p in allowed]

    @mcp.tool()
    def list_directory(path: str = ".") -> dict:
        """List files and directories at the given path (relative to an allowed root or absolute)."""
        target = Path(path)
        if not target.is_absolute():
            # Prefer first allowed dir as default root for relative paths
            if allowed:
                target = allowed[0] / path
            else:
                return {"error": "No allowed directories configured"}
        if not is_path_allowed(target, allowed):
            return {"error": "Access denied: path outside allowed directories"}
        if not target.exists():
            return {"error": f"Path not found: {path}"}
        if not target.is_dir():
            return {"error": "Not a directory"}

        entries = []
        for item in sorted(target.iterdir()):
            entries.append(
                {
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None,
                }
            )
        return {"path": str(target), "entries": entries}

    @mcp.tool()
    def read_file(path: str, max_bytes: int = 1_000_000) -> dict:
        """Read the contents of a text file (truncated if larger than max_bytes)."""
        target = Path(path)
        if not target.is_absolute() and allowed:
            target = allowed[0] / path
        if not is_path_allowed(target, allowed):
            return {"error": "Access denied"}
        if not target.is_file():
            return {"error": "Not a file or does not exist"}
        try:
            data = target.read_bytes()
            truncated = len(data) > max_bytes
            content = data[:max_bytes].decode("utf-8", errors="replace")
            return {
                "path": str(target),
                "content": content,
                "truncated": truncated,
                "size": len(data),
            }
        except Exception as e:
            return {"error": str(e)}

    if not read_only:

        @mcp.tool()
        def write_file(path: str, content: str) -> dict:
            """Write (overwrite) content to a file. Creates parent directories if needed."""
            target = Path(path)
            if not target.is_absolute() and allowed:
                target = allowed[0] / path
            if not is_path_allowed(target, allowed):
                return {"error": "Access denied"}
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                return {"path": str(target), "bytes_written": len(content.encode("utf-8"))}
            except Exception as e:
                return {"error": str(e)}

        @mcp.tool()
        def create_directory(path: str) -> dict:
            """Create a directory (and parents) if it does not exist."""
            target = Path(path)
            if not target.is_absolute() and allowed:
                target = allowed[0] / path
            if not is_path_allowed(target, allowed):
                return {"error": "Access denied"}
            try:
                target.mkdir(parents=True, exist_ok=True)
                return {"path": str(target), "created": True}
            except Exception as e:
                return {"error": str(e)}

    return mcp
