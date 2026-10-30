"""Tests for OAuth 2.1 helpers and store."""

import tempfile
from pathlib import Path

from desklink.oauth import (
    OAuthApp,
    OAuthStore,
    generate_client_id,
    verify_pkce,
    _hash,
)


def test_pkce_s256():
    import base64
    import hashlib

    verifier = "test-verifier-value-1234567890"
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    assert verify_pkce(verifier, challenge, "S256")
    assert not verify_pkce("wrong", challenge, "S256")


def test_store_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        store = OAuthStore(Path(d))
        app = OAuthApp(
            client_id=generate_client_id(),
            name="Claude",
            preset="claude",
            scopes=["mcp:tools"],
            public=True,
        )
        store.save_app(app)
        loaded = store.get_app(app.client_id)
        assert loaded is not None
        assert loaded.name == "Claude"
        assert loaded.public is True


def test_secret_hash():
    secret = "super-secret"
    h = _hash(secret)
    assert h == _hash(secret)
    assert h != _hash("other")
