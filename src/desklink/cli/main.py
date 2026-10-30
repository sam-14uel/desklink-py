"""DeskLink CLI.

Primary command: desklink start

Supports mcp.json for local STDIO servers and desklink.config.json for settings.
Also provides tools listing and direct tool invocation for testing.
"""

import asyncio
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from desklink import __version__
from desklink.auth import load_or_create_token
from desklink.bridge import McpBridge
from desklink.config import ensure_default_filesystem, load_config
from desklink.oauth import (
    PRESETS,
    OAuthApp,
    OAuthStore,
    generate_client_id,
    generate_client_secret,
    _hash,
)
from desklink.server import DeskLinkServer

app = typer.Typer(help="Turn your local computer into a remote MCP endpoint.")
console = Console()


def setup_logging(verbose: bool = False, level: Optional[str] = None) -> None:
    log_level = logging.DEBUG if verbose else getattr(logging, (level or "INFO").upper(), logging.INFO)
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")


def _load_cfg(config, mcp_config, allowed_dirs):
    cfg = load_config(config_path=config, mcp_path=mcp_config)
    if allowed_dirs:
        dirs = [Path(d).resolve() for d in allowed_dirs]
        cfg = ensure_default_filesystem(cfg, dirs)
    else:
        cfg = ensure_default_filesystem(cfg)
    return cfg


@app.command()
def start(
    mcp_config: Optional[Path] = typer.Option(None, "--mcp-config"),
    config: Optional[Path] = typer.Option(None, "--config"),
    allowed_dirs: Optional[list[str]] = typer.Option(None, "--dir", "-d"),
    port: Optional[int] = typer.Option(None, "--port", "-p"),
    tunnel: Optional[str] = typer.Option(None, "--tunnel"),
    token: Optional[str] = typer.Option(None, "--token"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Start the MCP bridge and tunnel."""
    cfg = _load_cfg(config, mcp_config, allowed_dirs)
    if port: cfg.settings.server.port = port
    if tunnel: cfg.settings.tunnel.provider = tunnel
    if token: cfg.settings.auth.token = token
    elif cfg.settings.auth.enabled and not cfg.settings.auth.token:
        cfg.settings.auth.token = load_or_create_token(cfg.settings.auth.token_file)
    setup_logging(verbose, cfg.settings.logging.level)
    console.print(Panel(f"DeskLink v{__version__}", style="bold cyan"))
    server = DeskLinkServer(cfg)
    async def _run():
        local = await server.start_http_server()
        public = server.start_tunnel()
        console.print("[green]MCP bridge started[/green]")
        console.print(f"Local: {local}")
        console.print(f"Remote: {public}")
        if cfg.settings.auth.token:
            console.print(f"Auth token: {cfg.settings.auth.token}")
        await server._shutdown_event.wait()
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    finally:
        asyncio.run(server.shutdown())


@app.command()
def create(
    kind: str = typer.Argument(..., help="What to create, e.g. oauth-app"),
    preset: str = typer.Argument("custom", help="Agent preset: claude, chatgpt, manus, cursor, custom"),
    name: Optional[str] = typer.Option(None, "--name"),
    public: bool = typer.Option(False, "--public/--confidential", help="Public client (no secret). Default is confidential with a secret."),
):
    """Create an OAuth application. Always generates Client ID + Client Secret unless --public."""
    if kind != "oauth-app":
        console.print(f"[red]Unknown create target:[/red] {kind}")
        raise typer.Exit(1)
    preset = preset.lower()
    meta = PRESETS.get(preset, PRESETS["custom"])
    display = name or meta["name"]
    scopes = meta["scopes"]
    client_id = generate_client_id()
    secret = None
    secret_hash = None
    if not public:
        secret = generate_client_secret()
        secret_hash = _hash(secret)
    OAuthStore().save_app(OAuthApp(client_id=client_id, name=display, preset=preset, scopes=scopes, public=public, client_secret_hash=secret_hash, description=meta.get("description", "")))
    console.print(Panel(f"OAuth app created: {display}", style="bold green"))
    console.print(f"[cyan]Client ID:[/cyan] {client_id}")
    if secret:
        console.print(f"[cyan]Client Secret:[/cyan] {secret}")
    else:
        console.print("[dim]Public client (no secret). Use PKCE.[/dim]")
    console.print(f"[cyan]Scopes:[/cyan] {', '.join(scopes)}")
    console.print("\nEndpoints (when DeskLink is running):")
    console.print("  Authorization:  http://127.0.0.1:8765/oauth/authorize")
    console.print("  Token:          http://127.0.0.1:8765/oauth/token")
    console.print("  MCP:            http://127.0.0.1:8765/mcp")
    console.print("  Dashboard:      http://127.0.0.1:8765/dashboard")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
