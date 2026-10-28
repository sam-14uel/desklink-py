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


def _load_cfg(
    config: Optional[Path],
    mcp_config: Optional[Path],
    allowed_dirs: Optional[list[str]],
) -> "DeskLinkConfig":
    from desklink.config import DeskLinkConfig

    cfg = load_config(config_path=config, mcp_path=mcp_config)
    if allowed_dirs:
        dirs = [Path(d).resolve() for d in allowed_dirs]
        cfg = ensure_default_filesystem(cfg, dirs)
    else:
        cfg = ensure_default_filesystem(cfg)
    return cfg


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
    cfg = _load_cfg(config, mcp_config, allowed_dirs)

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
def tools(
    mcp_config: Optional[Path] = typer.Option(None, "--mcp-config", help="Path to mcp.json"),
    config: Optional[Path] = typer.Option(None, "--config", help="Path to desklink.config.json"),
    allowed_dirs: Optional[list[str]] = typer.Option(
        None, "--dir", "-d", help="Allowed directory for default filesystem server"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """List tools discovered from configured MCP servers (no tunnel started)."""
    cfg = _load_cfg(config, mcp_config, allowed_dirs)
    setup_logging(verbose, cfg.settings.logging.level)

    async def _list():
        bridge = McpBridge(cfg)
        try:
            await bridge.start_servers()
            if not bridge.tools:
                console.print("[yellow]No tools discovered.[/yellow]")
                return
            table = Table(title="Discovered MCP Tools")
            table.add_column("Namespaced Name", style="cyan")
            table.add_column("Server")
            table.add_column("Description")
            for t in bridge.tools:
                table.add_row(t["namespaced"], t["server"], (t["description"] or "")[:80])
            console.print(table)
            console.print(f"\n[dim]Total: {len(bridge.tools)} tools from {len(cfg.mcp.mcpServers)} server(s)[/dim]")
        finally:
            await bridge.close()

    asyncio.run(_list())


@app.command()
def call(
    tool_name: str = typer.Argument(..., help="Namespaced tool name, e.g. filesystem__list_directory"),
    args: Optional[str] = typer.Option(
        None,
        "--args",
        "-a",
        help="JSON object of arguments. On Windows use double quotes: --args \"{\\\"path\\\":\\\"C:\\\\Users\\\\User\\\"}\"",
    ),
    arg: Optional[list[str]] = typer.Option(
        None,
        "--arg",
        "-A",
        help="Single argument as key=value (repeatable). Safer on Windows than JSON.",
    ),
    mcp_config: Optional[Path] = typer.Option(None, "--mcp-config", help="Path to mcp.json"),
    config: Optional[Path] = typer.Option(None, "--config", help="Path to desklink.config.json"),
    allowed_dirs: Optional[list[str]] = typer.Option(
        None, "--dir", "-d", help="Allowed directory for default filesystem server"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Call a tool by its namespaced name and print the result (for testing).

    Examples:
      desklink call filesystem__list_directory --arg path=C:\\Users\\User\\Desktop
      desklink call filesystem__list_directory --args \"{\\\"path\\\":\\\"C:\\\\Users\\\\User\\\\Desktop\\\"}\"
    """
    cfg = _load_cfg(config, mcp_config, allowed_dirs)
    setup_logging(verbose, cfg.settings.logging.level)

    arguments: dict = {}

    # Prefer repeatable --arg key=value (Windows-friendly)
    if arg:
        for item in arg:
            if "=" not in item:
                console.print(f"[red]Invalid --arg (expected key=value):[/red] {item}")
                raise typer.Exit(1)
            key, value = item.split("=", 1)
            # Try to parse value as JSON (numbers, bools, objects); fall back to string
            try:
                arguments[key] = json.loads(value)
            except Exception:
                arguments[key] = value

    # Also accept a full JSON object via --args
    if args:
        # Allow @file.json to read arguments from a file (avoids quoting issues)
        raw = args
        if args.startswith("@"):
            try:
                raw = Path(args[1:]).read_text(encoding="utf-8")
            except Exception as e:
                console.print(f"[red]Could not read args file:[/red] {e}")
                raise typer.Exit(1)
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("args must be a JSON object")
            arguments.update(parsed)
        except Exception as e:
            console.print(f"[red]Invalid --args JSON:[/red] {e}")
            console.print("[dim]Tip (Windows): use --arg path=C:\\Users\\User\\Desktop[/dim]")
            console.print('[dim]Or double quotes: --args \