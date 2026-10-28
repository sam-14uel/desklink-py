"""Authentication helpers for DeskLink.

Currently provides a simple static Bearer token verifier.
Designed so OAuth / Protected Resource Metadata can be added later.
"""

import secrets
from pathlib import Path
from typing import Optional

from mcp.server.auth.provider import AccessToken, TokenVerifier


def generate_token() -> str:
    """Generate a cryptographically strong random token."""
    return secrets.token_urlsafe(32)


def load_or_create_token(token_file: Path) -> str:
    """Load an existing token or create a new one with restricted permissions."""
    token_file = Path(token_file)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    if token_file.exists():
        return token_file.read_text().strip()
    token = generate_token()
    token_file.write_text(token + "\n")
    try:
        token_file.chmod(0o600)
    except Exception:
        pass  # Windows or restricted FS
    return token


class DeskLinkTokenVerifier(TokenVerifier):
    """Minimal TokenVerifier that accepts a single static Bearer token."""

    def __init__(self, token: str):
        self.token = token

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        if token == self.token:
            return AccessToken(
                token=token,
                client_id="desklink-local",
                scopes=["mcp"],
                expires_at=None,
            )
        return None
