"""Tunnel abstraction so ngrok is only one provider.

Future providers (Cloudflare Tunnel, DeskLink cloud relay, etc.) can implement
the same interface.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

from pyngrok import ngrok
from pyngrok.exception import PyngrokError

from desklink.models import TunnelInfo

logger = logging.getLogger(__name__)


class TunnelProvider(ABC):
    """Abstract tunnel provider."""

    @abstractmethod
    def start(self, local_port: int, authtoken: Optional[str] = None) -> TunnelInfo:
        """Start a tunnel to the local port and return public URL info."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the tunnel and clean up resources."""


class NgrokTunnel(TunnelProvider):
    """ngrok tunnel implementation using pyngrok."""

    def __init__(self):
        self._tunnel = None

    def start(self, local_port: int, authtoken: Optional[str] = None) -> TunnelInfo:
        if authtoken:
            ngrok.set_auth_token(authtoken)
        try:
            # Prefer HTTPS
            self._tunnel = ngrok.connect(local_port, "http")
            public_url = self._tunnel.public_url
            # Ensure https
            if public_url.startswith("http://"):
                public_url = "https://" + public_url[len("http://") :]
            local_url = f"http://127.0.0.1:{local_port}"
            logger.info("ngrok tunnel established: %s -> %s", public_url, local_url)
            return TunnelInfo(
                provider="ngrok",
                public_url=public_url,
                local_url=local_url,
                tunnel_id=getattr(self._tunnel, "name", None),
            )
        except PyngrokError as e:
            logger.error("Failed to start ngrok tunnel: %s", e)
            raise RuntimeError(f"ngrok tunnel failed: {e}") from e

    def stop(self) -> None:
        if self._tunnel:
            try:
                ngrok.disconnect(self._tunnel.public_url)
                logger.info("ngrok tunnel disconnected")
            except Exception as e:
                logger.warning("Error disconnecting ngrok: %s", e)
            self._tunnel = None
        try:
            ngrok.kill()
        except Exception:
            pass


class NoTunnel(TunnelProvider):
    """No-op tunnel for local-only testing."""

    def start(self, local_port: int, authtoken: Optional[str] = None) -> TunnelInfo:
        local_url = f"http://127.0.0.1:{local_port}"
        return TunnelInfo(provider="none", public_url=local_url, local_url=local_url)

    def stop(self) -> None:
        pass


def get_tunnel_provider(name: str) -> TunnelProvider:
    """Factory for tunnel providers."""
    name = (name or "ngrok").lower()
    if name == "ngrok":
        return NgrokTunnel()
    if name in ("none", "local", "disabled"):
        return NoTunnel()
    raise ValueError(f"Unknown tunnel provider: {name}")
