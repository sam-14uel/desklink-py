"""DeskLink CLI.

Primary command: desklink start

Supports mcp.json for local STDIO servers and desklink.config.json for settings.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from desklink import __version__
from desklink.auth import load_or_create_token
from desklink.config import ensure_default_filesystem, load_config
from desklink.server import DeskLinkServer

app = typer.Typer(help="Turn your local computer into a remote MCP endpoint.")
console = Console()


def setup_logging(verbose: bool = False, level: Optional[str] = None) -> None:
    log_level = logging.DEBUG if verbose else getattr(logging, (level or "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@app.command()
def start(
    mcp_config: Optional[Path] = typer.Option(None, "--mcp-config", help="Path to mcp.json"),
    config: Optional[Path] = typer.Option(None, "--config", help="Path to desklink.config.json"),
    allowed_dirs: Optional[list[str]] = typer.Option(
        None, "--dir", "-d", help="Allowed directory for default filesystem server (can be repeated)"
    ),
    port: Optional[int] = typer.Option(None, "--port", "-p"),
    tunnel: Optional[str] = typer.Option(None, "--tunnel", help="ngrok or none"),
    token: Optional[str] = typer.Option(None, "--token"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Start the MCP bridge and tunnel.

    If no mcp.json is found, a default official filesystem server is used
    (backward compatible with the previous --dir behaviour).
    """
    cfg = load_config(config_path=config, mcp_path=mcp_config)

    if allowed_dirs:
        dirs = [Path(d).resolve() for d in allowed_dirs]
        cfg = ensure_default_filesystem(cfg, dirs)
    else:
        cfg = ensure_default_filesystem(cfg)

    if port:
        cfg.settings.server.port = port
    if tunnel:
        cfg.settings.tunnel.provider = tunnel
    if token:
        cfg.settings.auth.token = token
    elif cfg.settings.auth.enabled and not cfg.settings.auth.token:
        cfg.settings.auth.token = load_or_create_token(cfg.settings.auth.token_file)

    setup_logging(verbose, cfg.settings.logging.level)

    console.print(Panel(f"DeskLink v{__version__}", style="bold cyan"))

    server = DeskLinkServer(cfg)

    async def _run():
        local = await server.start_http_server()
        public = server.start_tunnel()

        console.print("[green]✓ MCP bridge started[/green]")
        console.print(f"[green]✓ Local MCP:[/green] {local}")
        console.print("[green]✓ Tunnel connected[/green]")
        console.print("\nRemote MCP endpoint:")
        console.print(f"[bold]{public}[/bold]")
        if cfg.settings.auth.token:
            console.print(f"\nAuth token: {cfg.settings.auth.token}")
            console.print("Include as Authorization: Bearer <token> when connecting.")
        console.print(f"\nStatus: ● Connected")
        console.print(f"Tools: {server.status.tools_count}")
        console.print(f"Servers: {len(cfg.mcp.mcpServers)}")
        console.print("\nPress Ctrl+C to stop.")

        loop = asyncio.get_event_loop()

        def _signal_handler():
            console.print("\n[yellow]Stopping DeskLink...[/]")
            server.request_shutdown()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _signal_handler)
            except NotImplementedError:
                signal.signal(sig, lambda *_: _signal_handler())

        await server._shutdown_event.wait()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/]")
    finally:
        asyncio.run(server.shutdown())
        console.print("[green]DeskLink stopped.[/]")


@app.command()
def status():
    """Show current DeskLink status (MVP: placeholder)."""
    console.print("Status command not fully implemented yet. Use 'desklink start'.")


@app.command()
def config_cmd(
    config: Optional[Path] = typer.Option(None, "--config"),
    mcp_config: Optional[Path] = typer.Option(None, "--mcp-config"),
):
    """Show current configuration."""
    cfg = load_config(config_path=config, mcp_path=mcp_config)
    console.print_json(cfg.model_dump_json(indent=2))


app.command(name="config")(config_cmd)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
