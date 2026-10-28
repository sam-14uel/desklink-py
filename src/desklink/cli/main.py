"""DeskLink CLI.

Primary command: desklink start
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from desklink import __version__
from desklink.auth import load_or_create_token
from desklink.config import DeskLinkConfig, load_config
from desklink.server import DeskLinkServer

app = typer.Typer(help="Turn your local computer into a remote MCP endpoint.")
console = Console()


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@app.command()
def start(
    allowed_dirs: Optional[list[str]] = typer.Option(
        None, "--dir", "-d", help="Allowed directory (can be repeated)"
    ),
    port: Optional[int] = typer.Option(None, "--port", "-p"),
    tunnel: Optional[str] = typer.Option(None, "--tunnel", help="ngrok or none"),
    token: Optional[str] = typer.Option(None, "--token"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Start the local MCP server and tunnel."""
    setup_logging(verbose)
    config = load_config()

    if allowed_dirs:
        config.filesystem.allowed_directories = [Path(d).resolve() for d in allowed_dirs]
    if port:
        config.server.port = port
    if tunnel:
        config.tunnel.provider = tunnel
    if token:
        config.auth.token = token
    elif config.auth.enabled and not config.auth.token:
        config.auth.token = load_or_create_token(config.auth.token_file)

    console.print(Panel(f"DeskLink v{__version__}", style="bold cyan"))

    server = DeskLinkServer(config)

    def shutdown_handler(*_):
        console.print("\nShutting down...")
        server.request_shutdown()

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    # Print status after start (the run loop prints via logging; enhance later)
    if server.status.public_url:
        console.print("[green]✓ Filesystem MCP started[/green]")
        console.print(f"[green]✓ Local MCP:[/green] {server.status.local_url}")
        console.print("[green]✓ Tunnel connected[/green]")
        console.print("\nRemote MCP endpoint:")
        console.print(f"[bold]{server.status.public_url}[/bold]")
        if config.auth.token:
            console.print(f"\nAuth token: {config.auth.token}")
            console.print("Include as Authorization: Bearer <token> when connecting.")
        console.print(f"\nStatus: ● Connected")
        console.print(f"Tools: {server.status.tools_count}")
        console.print(f"Allowed dirs: {len(server.status.allowed_directories)}")
        console.print("\nPress Ctrl+C to stop.")


@app.command()
def status():
    """Show current DeskLink status (MVP: placeholder)."""
    console.print("Status command not fully implemented yet. Use 'desklink start'.")


@app.command()
def config():
    """Show current configuration."""
    cfg = load_config()
    console.print(cfg.model_dump())


if __name__ == "__main__":
    app()
