"""OAuth 2.1 authorization server and lightweight management dashboard.

Implements:
- Authorization Code + PKCE
- Access and refresh tokens
- Token revocation
- OAuth metadata discovery
- Dynamic Client Registration
- Browser consent screen
- Management dashboard
"""

from __future__ import annotations

import json
import time
from typing import Optional
from urllib.parse import urlencode

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

from desklink.oauth import (
    ALL_SCOPES,
    PRESETS,
    AccessToken,
    AuthCode,
    ConsentGrant,
    OAuthApp,
    OAuthStore,
    generate_access_token,
    generate_client_id,
    generate_client_secret,
    generate_code,
    generate_refresh_token,
    verify_pkce,
    _hash,
)

store = OAuthStore()


def _issuer(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost"))
    return f"{proto}://{host}"


def _scopes_from_str(s: Optional[str]) -> list[str]:
    if not s:
        return []
    return [p for p in s.replace(",", " ").split() if p]


async def metadata(request: Request) -> JSONResponse:
    issuer = _issuer(request)
    return JSONResponse({
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/oauth/authorize",
        "token_endpoint": f"{issuer}/oauth/token",
        "registration_endpoint": f"{issuer}/oauth/register",
        "revocation_endpoint": f"{issuer}/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
        "scopes_supported": ALL_SCOPES,
        "response_modes_supported": ["query"],
    })


async def register(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = body.get("client_name") or body.get("name") or "Dynamic Client"
    preset = body.get("preset") or "custom"
    scopes = body.get("scope") or " ".join(PRESETS.get(preset, PRESETS["custom"])["scopes"])
    if isinstance(scopes, list):
        scopes = " ".join(scopes)
    redirect_uris = body.get("redirect_uris") or []
    public = body.get("token_endpoint_auth_method", "none") == "none"
    client_id = generate_client_id()
    secret = None
    secret_hash = None
    if not public:
        secret = generate_client_secret()
        secret_hash = _hash(secret)
    app = OAuthApp(client_id=client_id, name=name, preset=preset, scopes=_scopes_from_str(scopes) or ["mcp:tools"], public=public, client_secret_hash=secret_hash, redirect_uris=redirect_uris, description=body.get("description") or "")
    store.save_app(app)
    store.log_activity("client_registered", f"{name} ({client_id})")
    resp = {"client_id": client_id, "client_name": name, "scope": " ".join(app.scopes), "redirect_uris": redirect_uris, "token_endpoint_auth_method": "none" if public else "client_secret_post"}
    if secret:
        resp["client_secret"] = secret
    return JSONResponse(resp, status_code=201)


async def authorize(request: Request) -> HTMLResponse:
    q = request.query_params
    client_id = q.get("client_id", "")
    app = store.get_app(client_id)
    if not app or not app.active:
        return HTMLResponse("<h2>Unknown or inactive client</h2>", status_code=400)
    requested = _scopes_from_str(q.get("scope", "")) or app.scopes
    allowed = [s for s in requested if s in app.scopes] or app.scopes
    checks = "".join(f'<label><input type="checkbox" name="scopes" value="{s}" checked> {s}</label><br>' for s in allowed)
    html = f'''<!doctype html><html><head><meta charset="utf-8"><title>Authorize {app.name}</title>
<style>body{{font-family:system-ui;background:#0f1115;color:#eee;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
.card{{background:#1a1d24;padding:2rem;border-radius:12px;max-width:460px}}button{{padding:0.6rem 1rem;border:0;border-radius:8px;margin-right:0.5rem;cursor:pointer}}
.a{{background:#3b82f6;color:#fff}}.d{{background:#374151;color:#fff}}</style></head>
<body><div class="card"><h2>Authorize {app.name}</h2><p>{app.description or app.preset}</p>
<form method="post" action="/oauth/authorize">
<input type="hidden" name="client_id" value="{app.client_id}">
<input type="hidden" name="redirect_uri" value="{q.get("redirect_uri") or ""}">
<input type="hidden" name="state" value="{q.get("state") or ""}">
<input type="hidden" name="code_challenge" value="{q.get("code_challenge") or ""}">
<input type="hidden" name="code_challenge_method" value="{q.get("code_challenge_method") or "S256"}">
{checks}<p><button class="a" name="decision" value="approve">Approve</button>
<button class="d" name="decision" value="deny">Deny</button></p></form></div></body></html>'''
    return HTMLResponse(html)


async def authorize_submit(request: Request) -> RedirectResponse:
    form = await request.form()
    client_id = form.get("client_id", "")
    decision = form.get("decision", "deny")
    redirect_uri = form.get("redirect_uri") or None
    state = form.get("state") or ""
    scopes = form.getlist("scopes") if hasattr(form, "getlist") else []
    if isinstance(scopes, str):
        scopes = [scopes]
    code_challenge = form.get("code_challenge") or None
    code_challenge_method = form.get("code_challenge_method") or "S256"
    app = store.get_app(client_id)
    if not app:
        return HTMLResponse("<h2>Unknown client</h2>", status_code=400)
    if decision != "approve":
        store.log_activity("consent_denied", client_id)
        if redirect_uri:
            q = urlencode({"error": "access_denied", "state": state})
            return RedirectResponse(f"{redirect_uri}?{q}", status_code=302)
        return HTMLResponse("<h2>Access denied</h2>")
    store.save_grant(ConsentGrant(client_id=client_id, scopes=scopes or app.scopes))
    code = generate_code()
    store.save_code(AuthCode(code=code, client_id=client_id, redirect_uri=redirect_uri, scopes=scopes or app.scopes, code_challenge=code_challenge, code_challenge_method=code_challenge_method, expires_at=time.time() + 600))
    store.log_activity("consent_approved", client_id)
    if redirect_uri:
        q = urlencode({"code": code, "state": state})
        return RedirectResponse(f"{redirect_uri}?{q}", status_code=302)
    return HTMLResponse(f"<html><body style='font-family:system-ui;background:#0f1115;color:#eee;padding:2rem'><h2>Approved</h2><p>Code: <code>{code}</code></p></body></html>")


async def token(request: Request) -> JSONResponse:
    form = await request.form()
    grant_type = form.get("grant_type", "")
    client_id = form.get("client_id", "")
    client_secret = form.get("client_secret")
    app = store.get_app(client_id)
    if not app or not app.active:
        return JSONResponse({"error": "invalid_client"}, status_code=401)
    if not app.public:
        if not client_secret or _hash(client_secret) != app.client_secret_hash:
            return JSONResponse({"error": "invalid_client"}, status_code=401)
    if grant_type == "authorization_code":
        code = form.get("code", "")
        verifier = form.get("code_verifier")
        auth_code = store.get_code(code)
        if not auth_code or auth_code.used or auth_code.expires_at < time.time() or auth_code.client_id != client_id:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        if auth_code.code_challenge and (not verifier or not verify_pkce(verifier, auth_code.code_challenge, auth_code.code_challenge_method)):
            return JSONResponse({"error": "invalid_grant", "error_description": "PKCE verification failed"}, status_code=400)
        store.mark_code_used(code)
        access = generate_access_token()
        refresh = generate_refresh_token()
        store.save_token(AccessToken(token=access, client_id=client_id, scopes=auth_code.scopes, expires_at=time.time() + 3600, refresh_token=refresh))
        store.log_activity("token_issued", client_id)
        return JSONResponse({"access_token": access, "token_type": "Bearer", "expires_in": 3600, "refresh_token": refresh, "scope": " ".join(auth_code.scopes)})
    if grant_type == "refresh_token":
        refresh = form.get("refresh_token", "")
        tokens = store.list_tokens(client_id)
        existing = next((t for t in tokens if t.refresh_token == refresh and not t.revoked), None)
        if not existing:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        access = generate_access_token()
        new_refresh = generate_refresh_token()
        store.save_token(AccessToken(token=access, client_id=client_id, scopes=existing.scopes, expires_at=time.time() + 3600, refresh_token=new_refresh))
        store.revoke_token(existing.token)
        return JSONResponse({"access_token": access, "token_type": "Bearer", "expires_in": 3600, "refresh_token": new_refresh, "scope": " ".join(existing.scopes)})
    return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)


async def revoke(request: Request) -> JSONResponse:
    form = await request.form()
    store.revoke_token(form.get("token", ""))
    return JSONResponse({}, status_code=200)


async def dashboard(request: Request) -> HTMLResponse:
    apps = store.list_apps()
    activity = store.list_activity(30)
    tokens = [t for t in store.list_tokens() if not t.revoked and t.expires_at > time.time()]
    rows = "".join(f"<tr><td>{a.name}</td><td><code>{a.client_id}</code></td><td>{a.preset}</td><td>{'public' if a.public else 'confidential'}</td><td>{', '.join(a.scopes)}</td><td><form method='post' action='/dashboard/revoke/{a.client_id}'><button>Revoke</button></form></td></tr>" for a in apps) or "<tr><td colspan='6'>No apps yet</td></tr>"
    act = "".join(f"<tr><td>{time.strftime('%H:%M:%S', time.localtime(i['ts']))}</td><td>{i['event']}</td><td>{i['detail']}</td></tr>" for i in activity)
    opts = "".join(f"<option value='{k}'>{v['name']}</option>" for k, v in PRESETS.items())
    html = f'''<!doctype html><html><head><meta charset="utf-8"><title>DeskLink Dashboard</title>
<style>body{{font-family:system-ui;background:#0f1115;color:#eee;margin:0;padding:1.5rem}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:0.5rem;border-bottom:1px solid #2a2f3a}}
.card{{background:#1a1d24;padding:1.25rem;border-radius:12px;margin-bottom:1rem}}button{{background:#3b82f6;color:#fff;border:0;padding:0.5rem 1rem;border-radius:8px}}</style></head>
<body><h1>DeskLink Dashboard</h1>
<div class="card"><h2>Create OAuth app</h2><form method="post" action="/dashboard/create">Preset <select name="preset">{opts}</select> Name <input name="name" style="background:#111;color:#eee;border:1px solid #333;padding:0.4rem;border-radius:6px"> <button>Create</button></form></div>
<div class="card"><h2>Applications</h2><table><tr><th>Name</th><th>Client ID</th><th>Preset</th><th>Type</th><th>Scopes</th><th></th></tr>{rows}</table><p>Active tokens: {len(tokens)}</p></div>
<div class="card"><h2>Recent activity</h2><table><tr><th>Time</th><th>Event</th><th>Detail</th></tr>{act}</table></div></body></html>'''
    return HTMLResponse(html)


async def dashboard_create(request: Request) -> RedirectResponse:
    form = await request.form()
    preset = form.get("preset", "custom")
    name = form.get("name") or PRESETS.get(preset, PRESETS["custom"])["name"]
    scopes = PRESETS.get(preset, PRESETS["custom"])["scopes"]
    client_id = generate_client_id()
    app = OAuthApp(client_id=client_id, name=name, preset=preset, scopes=scopes, public=True)
    store.save_app(app)
    store.log_activity("app_created", f"{name} ({client_id})")
    return RedirectResponse("/dashboard", status_code=302)


async def dashboard_revoke(request: Request) -> RedirectResponse:
    client_id = request.path_params.get("client_id")
    store.revoke_grant(client_id)
    store.log_activity("grant_revoked", client_id)
    return RedirectResponse("/dashboard", status_code=302)


def get_oauth_routes() -> list[Route]:
    return [
        Route("/.well-known/oauth-authorization-server", metadata, methods=["GET"]),
        Route("/oauth/register", register, methods=["POST"]),
        Route("/oauth/authorize", authorize, methods=["GET"]),
        Route("/oauth/authorize", authorize_submit, methods=["POST"]),
        Route("/oauth/token", token, methods=["POST"]),
        Route("/oauth/revoke", revoke, methods=["POST"]),
        Route("/dashboard", dashboard, methods=["GET"]),
        Route("/dashboard/create", dashboard_create, methods=["POST"]),
        Route("/dashboard/revoke/{client_id}", dashboard_revoke, methods=["POST"]),
    ]


def is_valid_oauth_token(token: str) -> Optional[AccessToken]:
    tok = store.get_token(token)
    if not tok or tok.revoked or tok.expires_at < time.time():
        return None
    return tok
