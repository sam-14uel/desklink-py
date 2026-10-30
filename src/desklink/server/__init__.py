"""DeskLink MCP server orchestration.

Starts a proxy Streamable HTTP server that aggregates tools from local STDIO
MCP servers (defined in mcp.json), applies auth (static bearer or OAuth), and
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

from desklink.bridge import McpBridge
from desklink.config import DeskLinkConfig
from desklink.models import ServerStatus
from desklink.oauth.server import get_oauth_routes, is_valid_oauth_token
from desklink.tunnel import get_tunnel_provider

logger = logging.getLogger(__name__)


class BearerAuthMiddleware:
    """ASGI middleware that accepts a static device bearer token or an OAuth access token."""

    def __init__(self, app: ASGIApp, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # Allow OAuth and dashboard paths without the device token
        path = scope.get("path", "")
        if path.startswith("/oauth") or path.startswith("/.well-known") or path.startswith("/dashboard"):
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode("latin-1")
        if not auth.startswith("Bearer "):
            response = JSONResponse({"error": "Unauthorized", "message": "Valid Bearer token required"}, status_code=401)
            await response(scope, receive, send)
            return
        token = auth[7:]
        if token != self.token and not is_valid_oauth_token(token):
            response = JSONResponse({"error": "Unauthorized", "message": "Valid Bearer token required"}, status_code=401)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


class DeskLinkServer:
    """Manages the local MCP HTTP proxy server and tunnel lifecycle."""

    def __init__(self, config: DeskLinkConfig):
        self.config = config
        self.bridge: Optional[McpBridge] = None
        self.proxy_mcp: Optional[FastMCP] = None
        self.app: Optional[Starlette] = None
        self.server: Optional[uvicorn.Server] = None
        self.tunnel = None
        self.status = ServerStatus()
        self._shutdown_event = asyncio.Event()

    async def start_http_server(self) -> str:
        self.bridge = McpBridge(self.config)
        await self.bridge.start_servers()
        self.proxy_mcp = self.bridge.build_proxy_server()

        middleware = []
        if self.config.settings.auth.enabled and self.config.settings.auth.token:
            middleware.append(Middleware(BearerAuthMiddleware, token=self.config.settings.auth.token))

        @contextlib.asynccontextmanager
        async def lifespan(app: Starlette):
            async with self.proxy_mcp.session_manager.run():
                yield

        self.app = Starlette(
            routes=[*get_oauth_routes(), Mount("/", app=self.proxy_mcp.streamable_http_app())],
            middleware=middleware,
            lifespan=lifespan,
        )

        config = uvicorn.Config(self.app, host=self.config.settings.server.host, port=self.config.settings.server.port, log_level="warning", access_log=False)
        self.server = uvicorn.Server(config)
        loop = asyncio.get_event_loop()
        loop.create_task(self.server.serve())

        for _ in range(60):
            if getattr(self.server, "started", False):
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("HTTP server failed to start within timeout")

        local_url = f"http://{self.config.settings.server.host}:{self.config.settings.server.port}{self.config.settings.server.mcp_path}"
        self.status.local_url = local_url
        self.status.running = True
        self.status.tools_count = len(self.bridge.tools)
        logger.info("Local MCP bridge listening at %s (%d tools)", local_url, self.status.tools_count)
        return local_url

    def start_tunnel(self) -> str:
        provider = get_tunnel_provider(self.config.settings.tunnel.provider)
        info = provider.start(self.config.settings.server.port, authtoken=self.config.settings.tunnel.authtoken)
        self.tunnel = provider
        public_mcp = info.public_url.rstrip("/") + self.config.settings.server.mcp_path
        self.status.public_url = public_mcp
        logger.info("Public MCP endpoint: %s", public_mcp)
        return public_mcp

    async def run(self) -> None:
        try:
            await self.start_http_server()
            self.start_tunnel()
            self.status.auth_enabled = self.config.settings.auth.enabled
            await self._shutdown_event.wait()
        finally:
            await self.shutdown()

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    async def shutdown(self) -> None:
        logger.info("Shutting down DeskLink...")
        if self.bridge:
            await self.bridge.close()
        if self.tunnel:
            try:
                self.tunnel.stop()
            except Exception as e:
                logger.warning("Tunnel stop error: %s", e)
        if self.server:
            self.server.should_exit = True
        self.status.running = False
        self._shutdown_event.set()
