"""File-based OAuth 2.1 store for DeskLink.

Persists applications, authorization codes, access/refresh tokens, and consent
grants under ~/.desklink/oauth/ without introducing a database.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

OAUTH_DIR = Path.home() / ".desklink" / "oauth"
APPS_FILE = OAUTH_DIR / "apps.json"
CODES_FILE = OAUTH_DIR / "codes.json"
TOKENS_FILE = OAUTH_DIR / "tokens.json"
GRANTS_FILE = OAUTH_DIR / "grants.json"
ACTIVITY_FILE = OAUTH_DIR / "activity.json"

# Sensible agent presets. Redirect URIs are optional.
PRESETS: Dict[str, Dict[str, Any]] = {
    "claude": {
        "name": "Claude",
        "scopes": ["mcp:tools", "mcp:resources", "filesystem:read"],
        "public": True,
        "description": "Anthropic Claude desktop / cloud agent",
    },
    "chatgpt": {
        "name": "ChatGPT",
        "scopes": ["mcp:tools", "mcp:resources"],
        "public": True,
        "description": "OpenAI ChatGPT agent",
    },
    "manus": {
        "name": "Manus",
        "scopes": ["mcp:tools", "filesystem:read", "filesystem:write"],
        "public": True,
        "description": "Manus agent",
    },
    "cursor": {
        "name": "Cursor",
        "scopes": ["mcp:tools", "filesystem:read", "filesystem:write"],
        "public": True,
        "description": "Cursor IDE agent",
    },
    "custom": {
        "name": "Custom Agent",
        "scopes": ["mcp:tools"],
        "public": True,
        "description": "Custom MCP client",
    },
}

ALL_SCOPES = [
    "mcp:tools",
    "mcp:resources",
    "filesystem:read",
    "filesystem:write",
    "admin",
]


def _now() -> float:
    return time.time()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except Exception:
        pass


@dataclass
class OAuthApp:
    client_id: str
    name: str
    preset: str
    scopes: List[str]
    public: bool = True
    client_secret_hash: Optional[str] = None
    redirect_uris: List[str] = field(default_factory=list)
    description: str = ""
    created_at: float = field(default_factory=_now)
    active: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AuthCode:
    code: str
    client_id: str
    redirect_uri: Optional[str]
    scopes: List[str]
    code_challenge: Optional[str]
    code_challenge_method: str = "S256"
    expires_at: float = 0.0
    used: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AccessToken:
    token: str
    client_id: str
    scopes: List[str]
    expires_at: float
    refresh_token: Optional[str] = None
    revoked: bool = False
    created_at: float = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConsentGrant:
    client_id: str
    scopes: List[str]
    granted_at: float = field(default_factory=_now)
    revoked: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class OAuthStore:
    """Simple JSON-file store for OAuth entities."""

    def __init__(self, base: Optional[Path] = None):
        self.base = base or OAUTH_DIR
        self.apps_file = self.base / "apps.json"
        self.codes_file = self.base / "codes.json"
        self.tokens_file = self.base / "tokens.json"
        self.grants_file = self.base / "grants.json"
        self.activity_file = self.base / "activity.json"

    def list_apps(self) -> List[OAuthApp]:
        data = _load(self.apps_file)
        return [OAuthApp(**v) for v in data.values()]

    def get_app(self, client_id: str) -> Optional[OAuthApp]:
        data = _load(self.apps_file)
        raw = data.get(client_id)
        return OAuthApp(**raw) if raw else None

    def save_app(self, app: OAuthApp) -> None:
        data = _load(self.apps_file)
        data[app.client_id] = app.to_dict()
        _save(self.apps_file, data)

    def delete_app(self, client_id: str) -> bool:
        data = _load(self.apps_file)
        if client_id in data:
            del data[client_id]
            _save(self.apps_file, data)
            return True
        return False

    def save_code(self, code: AuthCode) -> None:
        data = _load(self.codes_file)
        data[code.code] = code.to_dict()
        _save(self.codes_file, data)

    def get_code(self, code: str) -> Optional[AuthCode]:
        data = _load(self.codes_file)
        raw = data.get(code)
        return AuthCode(**raw) if raw else None

    def mark_code_used(self, code: str) -> None:
        data = _load(self.codes_file)
        if code in data:
            data[code]["used"] = True
            _save(self.codes_file, data)

    def save_token(self, token: AccessToken) -> None:
        data = _load(self.tokens_file)
        data[token.token] = token.to_dict()
        _save(self.tokens_file, data)

    def get_token(self, token: str) -> Optional[AccessToken]:
        data = _load(self.tokens_file)
        raw = data.get(token)
        return AccessToken(**raw) if raw else None

    def revoke_token(self, token: str) -> bool:
        data = _load(self.tokens_file)
        if token in data:
            data[token]["revoked"] = True
            _save(self.tokens_file, data)
            return True
        for k, v in data.items():
            if v.get("refresh_token") == token:
                v["revoked"] = True
                _save(self.tokens_file, data)
                return True
        return False

    def list_tokens(self, client_id: Optional[str] = None) -> List[AccessToken]:
        data = _load(self.tokens_file)
        tokens = [AccessToken(**v) for v in data.values()]
        if client_id:
            tokens = [t for t in tokens if t.client_id == client_id]
        return tokens

    def save_grant(self, grant: ConsentGrant) -> None:
        data = _load(self.grants_file)
        data[grant.client_id] = grant.to_dict()
        _save(self.grants_file, data)

    def get_grant(self, client_id: str) -> Optional[ConsentGrant]:
        data = _load(self.grants_file)
        raw = data.get(client_id)
        return ConsentGrant(**raw) if raw else None

    def revoke_grant(self, client_id: str) -> bool:
        data = _load(self.grants_file)
        if client_id in data:
            data[client_id]["revoked"] = True
            _save(self.grants_file, data)
            tokens = _load(self.tokens_file)
            for v in tokens.values():
                if v.get("client_id") == client_id:
                    v["revoked"] = True
            _save(self.tokens_file, tokens)
            return True
        return False

    def log_activity(self, event: str, detail: str = "") -> None:
        data = _load(self.activity_file)
        items = data.get("items", [])
        items.append({"ts": _now(), "event": event, "detail": detail})
        data["items"] = items[-200:]
        _save(self.activity_file, data)

    def list_activity(self, limit: int = 50) -> List[dict]:
        data = _load(self.activity_file)
        return list(reversed(data.get("items", [])))[:limit]


def generate_client_id() -> str:
    return "dl_" + secrets.token_urlsafe(16)


def generate_client_secret() -> str:
    return secrets.token_urlsafe(32)


def generate_code() -> str:
    return secrets.token_urlsafe(32)


def generate_access_token() -> str:
    return "dl_at_" + secrets.token_urlsafe(32)


def generate_refresh_token() -> str:
    return "dl_rt_" + secrets.token_urlsafe(32)


def verify_pkce(verifier: str, challenge: str, method: str = "S256") -> bool:
    """Verify PKCE code_verifier against code_challenge."""
    if method == "plain":
        return secrets.compare_digest(verifier, challenge)
    digest = hashlib.sha256(verifier.encode()).digest()
    import base64
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return secrets.compare_digest(computed, challenge)
