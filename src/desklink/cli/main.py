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
def create(
    kind: str = typer.Argument(..., help="What to create, e.g. oauth-app"),
    preset: str = typer.Argument("custom", help="Agent preset: claude, chatgpt, manus, cursor, custom"),
    name: Optional[str] = typer.Option(None, "--name", help="Display name"),
    public: bool = typer.Option(False, "--public/--confidential", help="Public client (PKCE only, no secret). Default is confidential with a secret."),
):
    """Create an OAuth application for a cloud agent.

    Examples:
      desklink create oauth-app claude
      desklink create oauth-app cursor
    """
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
    is_public = public
    if not is_public:
        secret = generate_client_secret()
        secret_hash = _hash(secret)

    app_obj = OAuthApp(
        client_id=client_id,
        name=display,
        preset=preset,
        scopes=scopes,
        public=is_public,
        client_secret_hash=secret_hash,
        description=meta.get("description", ""),
    )
    OAuthStore().save_app(app_obj)

    console.print(Panel(f"OAuth app created: {display}", style="bold green"))
    console.print(f"[cyan]Client ID:[/cyan] {client_id}")
    if secret:
        console.print(f"[cyan]Client Secret:[/cyan] {secret}")
    else:
        console.print("[dim]Public client (no secret). Use PKCE.[/dim]")
    console.print(f"[cyan]Scopes:[/cyan] {', '.join(scopes)}")
    console.print(f"[cyan]Preset:[/cyan] {preset}")
    console.print()
    console.print("[bold]Endpoints (when DeskLink is running):[/bold]")
    console.print("  Authorization:  http://127.0.0.1:8765/oauth/authorize")
    console.print("  Token:          http://127.0.0.1:8765/oauth/token")
    console.print("  Metadata:       http://127.0.0.1:8765/.well-known/oauth-authorization-server")
    console.print("  MCP:            http://127.0.0.1:8765/mcp")
    console.print("  Dashboard:      http://127.0.0.1:8765/dashboard")
    console.print()
    console.print("[dim]Redirect URIs are optional. Public clients and dynamic registration are supported.[/dim]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
