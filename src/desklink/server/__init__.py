"""DeskLink MCP server orchestration.

Starts the filesystem MCP server over Streamable HTTP, applies auth, and
coordinates with the tunnel.
"""

import asyncio
import contextlib
import logging
from typing import Optional

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Mount
from starlette.types import ASGIApp, Receive, Scope, Send

from desklink.config import DeskLinkConfig
from desklink.filesystem import create_filesystem_server
from desklink.models import ServerStatus
from desklink.tunnel import get_tunnel_provider

logger = logging.getLogger(__name__)


class BearerAuthMiddleware:
    """Simple ASGI middleware that requires a valid Bearer token.

    Designed so stronger authentication can replace or wrap this later.
    """

    def __init__(self, app: ASGIApp, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode("latin-1")
        if not auth.startswith("Bearer ") or auth[7:] != self.token:
            response = JSONResponse(
                {"error": "Unauthorized", "message": "Valid Bearer token required"},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class DeskLinkServer:
    """Manages the local MCP HTTP server and tunnel lifecycle."""

    def __init__(self, config: DeskLinkConfig):
        self.config = config
        self.filesystem_mcp: Optional[FastMCP] = None
        self.app: Optional[Starlette] = None
        self.server: Optional[uvicorn.Server] = None
        self.tunnel = None
        self.status = ServerStatus()
        self._shutdown_event = asyncio.Event()

    def build_mcp(self) -> FastMCP:
        """Create the filesystem MCP server."""
        self.filesystem_mcp = create_filesystem_server(
            self.config.filesystem.allowed_directories,
            read_only=self.config.filesystem.read_only,
        )
        return self.filesystem_mcp

    async def start_http_server(self) -> str:
        """Start the Streamable HTTP server and return the local URL."""
        mcp = self.build_mcp()

        middleware = []
        if self.config.auth.enabled and self.config.auth.token:
            middleware.append(
                Middleware(BearerAuthMiddleware, token=self.config.auth.token)
            )

        # Must run the session manager in the host app lifespan.
        # Mounting streamable_http_app() alone does not start it (known MCP SDK issue).
        @contextlib.asynccontextmanager
        async def lifespan(app: Starlette):
            async with mcp.session_manager.run():
                yield

        # FastMCP's streamable_http_app serves at its configured streamable_http_path
        # (default /mcp). We mount the app at root so the public endpoint is
        # http://host:port/mcp .
        self.app = Starlette(
            routes=[
                Mount("/", app=mcp.streamable_http_app()),
            ],
            middleware=middleware,
            lifespan=lifespan,
        )

        config = uvicorn.Config(
            self.app,
            host=self.config.server.host,
            port=self.config.server.port,
            log_level="warning",
            access_log=False,
        )
        self.server = uvicorn.Server(config)

        loop = asyncio.get_event_loop()
        loop.create_task(self.server.serve())

        # Wait until ready
        for _ in range(60):
            if getattr(self.server, "started", False):
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("HTTP server failed to start within timeout")

        local_url = (
            f"http://{self.config.server.host}:{self.config.server.port}{self.config.server.mcp_path}"
        )
        self.status.local_url = local_url
        self.status.running = True
        logger.info("Local MCP server listening at %s", local_url)
        return local_url

    def start_tunnel(self) -> str:
        """Establish the public tunnel and return the public MCP URL."""
        provider = get_tunnel_provider(self.config.tunnel.provider)
        info = provider.start(
            self.config.server.port,
            authtoken=self.config.tunnel.authtoken,
        )
        self.tunnel = provider
        public_mcp = info.public_url.rstrip("/") + self.config.server.mcp_path
        self.status.public_url = public_mcp
        logger.info("Public MCP endpoint: %s", public_mcp)
        return public_mcp

    async def run(self) -> None:
        """Start everything and block until shutdown."""
        try:
            local = await self.start_http_server()
            public = self.start_tunnel()

            # Count tools
            if self.filesystem_mcp:
                try:
                    tools = self.filesystem_mcp.list_tools()
                    self.status.tools_count = len(list(tools))
                except Exception:
                    self.status.tools_count = 5  # fallback estimate

            self.status.auth_enabled = self.config.auth.enabled
            self.status.allowed_directories = self.config.filesystem.allowed_directories

            # Keep running until shutdown
            await self._shutdown_event.wait()
        finally:
            await self.shutdown()

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down DeskLink...")
        if self.tunnel:
            try:
                self.tunnel.stop()
            except Exception as e:
                logger.warning("Tunnel stop error: %s", e)
        if self.server:
            self.server.should_exit = True
        self.status.running = False
        self._shutdown_event.set()
