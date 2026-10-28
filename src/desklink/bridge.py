"""Bridge that proxies tools from local STDIO MCP servers.

DeskLink connects to configured STDIO servers (from mcp.json), discovers their
tools, and exposes them through a single Streamable HTTP endpoint.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from desklink.config import DeskLinkConfig

logger = logging.getLogger(__name__)


class ToolProxy:
    """Handles a single tool call with approval and tracing."""

    def __init__(self, config: DeskLinkConfig, sessions: Dict[str, ClientSession]):
        self.config = config
        self.sessions = sessions

    def _should_approve(self, tool_name: str) -> bool:
        policy = self.config.settings.approvals.tools.get(
            tool_name, self.config.settings.approvals.default
        )
        if policy == "auto":
            return True
        # Simple console prompt for MVP
        try:
            resp = input(f"\n[DeskLink] Approve tool call '{tool_name}'? [y/N] ").strip().lower()
            return resp in ("y", "yes")
        except EOFError:
            return False

    def _trace(
        self,
        tool: str,
        args: dict,
        result: Any,
        duration_ms: float,
        error: Optional[str] = None,
    ) -> None:
        if not self.config.settings.tracing.enabled or self.config.settings.tracing.level == "none":
            return
        level = self.config.settings.tracing.level
        entry = {
            "tool": tool,
            "duration_ms": round(duration_ms, 1),
            "error": error,
        }
        if level == "full":
            if self.config.settings.tracing.redact_sensitive:
                sensitive = {"password", "token", "secret", "key", "authorization"}
                safe_args = {
                    k: ("***" if k.lower() in sensitive else v) for k, v in args.items()
                }
            else:
                safe_args = args
            entry["args"] = safe_args
            entry["result"] = str(result)[:500] if result else None
        logger.info("TRACE %s", json.dumps(entry, default=str))

    async def call(self, namespaced_name: str, arguments: dict) -> Any:
        """Route a namespaced tool call to the correct STDIO session."""
        if "__" not in namespaced_name:
            raise ValueError(f"Invalid tool name: {namespaced_name}")
        server_name, tool_name = namespaced_name.split("__", 1)
        session = self.sessions.get(server_name)
        if not session:
            raise RuntimeError(f"No session for server '{server_name}'")

        if not self._should_approve(namespaced_name):
            raise PermissionError(f"Tool call '{namespaced_name}' denied by user")

        start = time.perf_counter()
        error = None
        result = None
        try:
            result = await session.call_tool(tool_name, arguments)
            return result
        except Exception as e:
            error = str(e)
            raise
        finally:
            duration = (time.perf_counter() - start) * 1000
            self._trace(namespaced_name, arguments, result, duration, error)


class McpBridge:
    """Manages STDIO MCP client sessions and builds a proxy FastMCP server."""

    def __init__(self, config: DeskLinkConfig):
        self.config = config
        self.sessions: Dict[str, ClientSession] = {}
        self.tools: List[Dict[str, Any]] = []
        self._contexts: List[Any] = []

    async def start_servers(self) -> None:
        """Connect to all configured STDIO servers and discover tools."""
        for name, srv in self.config.mcp.mcpServers.items():
            params = StdioServerParameters(
                command=srv.command,
                args=srv.args,
                env=srv.env,
                cwd=srv.cwd,
            )
            try:
                stdio_ctx = stdio_client(params)
                read, write = await stdio_ctx.__aenter__()
                session = ClientSession(read, write)
                await session.__aenter__()
                await session.initialize()
                self.sessions[name] = session
                self._contexts.append((stdio_ctx, session))

                tools_result = await session.list_tools()
                for t in tools_result.tools:
                    self.tools.append(
                        {
                            "server": name,
                            "name": t.name,
                            "namespaced": f"{name}__{t.name}",
                            "description": t.description or "",
                            "inputSchema": t.inputSchema,
                        }
                    )
                logger.info(
                    "Connected to MCP server '%s' (%d tools)", name, len(tools_result.tools)
                )
            except Exception as e:
                logger.error("Failed to start MCP server '%s': %s", name, e)

    def build_proxy_server(self) -> FastMCP:
        """Create a FastMCP that proxies all discovered tools.

        Each proxy tool is registered with a signature that matches the original
        MCP tool's inputSchema (not a synthetic kwargs wrapper). This makes the
        advertised schema and the call path consistent.
        """
        import inspect

        mcp = FastMCP(
            "DeskLink Bridge",
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=False,
            ),
        )
        proxy = ToolProxy(self.config, self.sessions)

        for tool in self.tools:
            ns_name = tool["namespaced"]
            desc = tool["description"] or f"Proxied tool from {tool['server']}"
            original_schema = tool.get("inputSchema") or {"type": "object", "properties": {}}

            props = (original_schema or {}).get("properties") or {}
            required = set((original_schema or {}).get("required") or [])

            # Build a real signature so FastMCP generates the correct parameter schema.
            # Only include properties that exist in the original schema.
            # A synthetic "kwargs" parameter is never added unless the upstream tool defines one.
            params = []
            for pname in props:
                if pname in required:
                    params.append(inspect.Parameter(pname, inspect.Parameter.POSITIONAL_OR_KEYWORD))
                else:
                    params.append(
                        inspect.Parameter(pname, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None)
                    )
            sig = inspect.Signature(params)

            def make_handler(name: str, signature: inspect.Signature, req: set):
                async def handler(*args: Any, **kwargs: Any) -> Any:
                    bound = signature.bind(*args, **kwargs)
                    bound.apply_defaults()
                    # Drop unset optionals; keep required values even if None
                    arguments = {
                        k: v for k, v in bound.arguments.items() if v is not None or k in req
                    }
                    return await proxy.call(name, arguments)

                handler.__signature__ = signature
                # Safe function name (MCP tool names can contain __)
                handler.__name__ = name.replace("__", "_")
                return handler

            handler = make_handler(ns_name, sig, required)
            mcp.tool(name=ns_name, description=desc)(handler)

            # Ensure the advertised schema is exactly the original one
            # (FastMCP may still rewrite some details from the signature).
            registered = mcp._tool_manager._tools.get(ns_name)
            if registered is not None and original_schema:
                registered.parameters = original_schema

        return mcp

    async def close(self) -> None:
        for stdio_ctx, session in self._contexts:
            try:
                await session.__aexit__(None, None, None)
                await stdio_ctx.__aexit__(None, None, None)
            except Exception:
                pass
