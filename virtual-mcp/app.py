"""Virtual MCP Server -- a Databricks App that fans one MCP endpoint out across
several underlying Unity Catalog MCP services.

The running app only serves the MCP endpoint and per-service login. WHICH
services/tools are combined is decided at app-creation time (VIRTUAL_MCP_CONFIG /
the template's services.json) -- there is deliberately no in-app configuration.

Surfaces:
  GET  /                     read-only landing: the endpoint + live tool list (post-login)
  GET  /login                guided, one-after-another login to every underlying service
  ANY  /mcp                  the virtual MCP server (streamable HTTP) that agents connect to
  GET  /api/tools            merged/filtered tool list (backs the landing page)
  GET  /api/login-status     per-service login state for the login chain
  GET  /healthz              liveness
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import json
import os

from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings

import config as cfg_mod
import pages
from context import USER_TOKEN_HEADER, app_base_url, databricks_host, set_user_token
import mcp_proxy
from mcp_proxy import server
from upstream import revoke_user_credential, user_credential_state

# Stateless proxy: every MCP request is independent, so no session store needed.
# json_response=True: reply with a single plain-JSON body instead of an SSE frame.
# Non-streaming clients (e.g. the AI Gateway / playground, a Jackson-based Java
# caller) send `Accept: application/json` and cannot parse an SSE frame; in JSON
# mode the SDK also relaxes its Accept check to json-only, so they stop getting
# 406. Spec-compliant clients accept JSON too, so this works for both. (Trade-off:
# JSON mode disables server->client requests, which this proxy doesn't use -- the
# "not signed in" case is returned as tool text, not an elicitation.)
# Disable DNS-rebinding protection: the Databricks Apps reverse proxy fronts the
# app under a *.databricksapps.com host, which the localhost-oriented default
# allow-list would otherwise reject.
_session_manager = StreamableHTTPSessionManager(
    app=server,
    json_response=True,
    stateless=True,
    security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

_ACCEPT_BOTH = b"application/json, text/event-stream"


def _with_full_accept(scope: dict) -> dict:
    """Force the Accept header to advertise both JSON and SSE.

    Clients that send only one of them (or none) would otherwise be rejected with
    406 by the transport's Accept validation. We answer in JSON regardless, so
    widening the header is safe and makes the endpoint accept any MCP client.
    """
    headers = [(k, v) for k, v in scope.get("headers", []) if k != b"accept"]
    headers.append((b"accept", _ACCEPT_BOTH))
    return {**scope, "headers": headers}


def _token_from_request(request: Request) -> str | None:
    return request.headers.get(USER_TOKEN_HEADER) or os.environ.get("VIRTUAL_MCP_DEV_TOKEN")


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    # Prime the config cache with fast, local config (env/bundled -- no network),
    # then discover the bound volume's config in a worker thread so the blocking
    # Unity Catalog calls never run on the event loop (which, under UC rate
    # limiting, would freeze every route). Fire-and-forget: serving starts now.
    cfg_mod.load()
    asyncio.create_task(asyncio.to_thread(cfg_mod.refresh_from_volume))
    async with _session_manager.run():
        yield


async def _credential_states(token: str, services) -> list[str]:
    """Per-service login state, checked in parallel with a short timeout so a
    slow/rate-limited Unity Catalog can't stall the request. Unknown -> treated
    as NEEDS_LOGIN so the guided flow still offers a sign-in."""

    async def one(name: str) -> str:
        try:
            return await asyncio.wait_for(user_credential_state(token, name), timeout=8)
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            return "UNKNOWN"

    return await asyncio.gather(*(one(s.name) for s in services))


app = FastAPI(title="Virtual MCP Server", lifespan=lifespan)


@app.middleware("http")
async def capture_user_token(request: Request, call_next):
    # The user's OBO token rides on every request (pages + /mcp). Stash it so the
    # MCP handlers and API routes can act as the user against upstream services.
    set_user_token(_token_from_request(request))
    return await call_next(request)


# --------------------------------------------------------------------------- #
# The virtual MCP server (streamable HTTP). We do NOT use app.mount("/mcp", ...):
# Starlette's Mount 307-redirects the bare "/mcp" to "/mcp/" using the app's
# internal host (localhost:8000), which MCP clients can't follow. Instead an
# outer ASGI wrapper dispatches BOTH "/mcp" and "/mcp/" straight to the session
# manager -- no redirect, correct host.
async def _mcp_asgi(scope, receive, send):
    token = None
    for key, value in scope.get("headers", []):
        if key == USER_TOKEN_HEADER.encode():
            token = value.decode()
            break
    set_user_token(token or os.environ.get("VIRTUAL_MCP_DEV_TOKEN"))
    await _session_manager.handle_request(_with_full_accept(scope), receive, send)


async def application(scope, receive, send):
    """ASGI entrypoint: MCP traffic to /mcp(/) bypasses FastAPI routing (no
    trailing-slash redirect); everything else (pages, APIs, lifespan) goes to
    FastAPI, whose lifespan runs the MCP session manager."""
    if scope["type"] == "http" and scope.get("path", "").rstrip("/") == "/mcp":
        await _mcp_asgi(scope, receive, send)
        return
    await app(scope, receive, send)


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    # The running app is a ready MCP server: the landing page shows the endpoint
    # and (post-login) the live tool list. Service selection happens at creation
    # time (VIRTUAL_MCP_CONFIG) or on the /configure page.
    return pages.home_page(cfg_mod.load())


def _public_base(request: Request) -> str:
    """Public base URL of this app, for building an mcp-service-login return_to.

    Behind the Databricks Apps proxy the `Host` header is the internal
    localhost:8000; the public host arrives in `x-forwarded-host`. Use that (never
    a localhost host, which would make return_to unreachable)."""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    if host and "localhost" not in host and "127.0.0.1" not in host:
        proto = request.headers.get("x-forwarded-proto", "https")
        return f"{proto}://{host}"
    return app_base_url()


@app.get("/login")
async def login(request: Request):
    """Guided sign-in: redirect the browser to the platform's /mcp-service-login
    for the first underlying service that still needs it (with return_to back
    here so it chains through the rest); once none remain, land on the status
    page. This is the redirect-driven flow; /login-status is the management view."""
    token = _token_from_request(request)
    if token:
        services = cfg_mod.load().services
        states = await _credential_states(token, services)
        for s, state in zip(services, states):
            if state == "NEEDS_LOGIN":
                return_to = quote(f"{_public_base(request)}/login", safe="")
                return RedirectResponse(
                    f"{databricks_host()}/mcp-service-login?name={quote(s.name)}&return_to={return_to}",
                    status_code=302,
                )
    # No token, or every service is already signed in -> back to the home page,
    # which shows per-service status + tools.
    return RedirectResponse("/", status_code=302)


@app.get("/api/tools")
async def api_tools(request: Request):
    """The exact merged/filtered tool list agents see post-login, plus a
    per-service diagnostic so an empty result explains itself."""
    token = _token_from_request(request)
    if not token:
        return JSONResponse({"error": "no_user_token"}, status_code=401)
    tools, diagnostics = await mcp_proxy.collect(token)
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description or "",
                "alias": t.name.split("__", 1)[0],
                "inputSchema": t.input_schema or {"type": "object"},
            }
            for t in tools
        ],
        "diagnostics": diagnostics,
    }


@app.post("/api/call")
async def api_call(request: Request, payload: dict):
    """Invoke one merged tool (namespaced `alias__tool`) with JSON arguments, so
    the UI can try tools. Routes to the owning service via the same path the MCP
    server uses. Returns {ok, text, error, needs_login}."""
    token = _token_from_request(request)
    if not token:
        return JSONResponse({"error": "no_user_token"}, status_code=401)
    name = payload.get("name")
    if not name:
        return JSONResponse({"error": "name required"}, status_code=400)
    args = payload.get("arguments") or {}
    if not isinstance(args, dict):
        return JSONResponse({"error": "arguments must be a JSON object"}, status_code=400)
    res = await mcp_proxy.call_tool_by_name(token, name, args)
    # Flatten upstream content blocks to display text.
    text = ""
    for b in res.get("content") or []:
        if isinstance(b, dict):
            text += b.get("text", "") if b.get("type") == "text" else json.dumps(b)
        else:
            text += str(b)
    return {"ok": res["ok"], "text": text, "error": res.get("error"), "needs_login": res.get("needs_login", False)}


@app.get("/api/login-status")
async def api_login_status(request: Request):
    token = _token_from_request(request)
    if not token:
        return JSONResponse({"error": "no_user_token"}, status_code=401)
    services = cfg_mod.load().services
    states = await _credential_states(token, services)
    statuses = [
        {"name": s.name, "alias": s.alias, "state": st} for s, st in zip(services, states)
    ]
    return {"services": statuses, "login_base": f"{databricks_host()}/mcp-service-login"}


@app.post("/api/revoke")
async def api_revoke(request: Request, payload: dict):
    """Revoke the caller's stored credential for one service (DELETE). Needs the
    writable `unity-catalog` OBO scope; surfaces the upstream error on failure."""
    token = _token_from_request(request)
    if not token:
        return JSONResponse({"error": "no_user_token"}, status_code=401)
    name = payload.get("name")
    if not name:
        return JSONResponse({"error": "name required"}, status_code=400)
    status, detail = await revoke_user_credential(token, name)
    return {"ok": status < 400 or status == 404, "status": status, "detail": detail}


@app.get("/api/debug-scopes")
async def api_debug_scopes(request: Request):
    """Decode the incoming OBO token's `scope` claim (no signature check, claims
    only) so we can see exactly what scopes THIS caller's token carries -- a
    browser session vs a CLI bearer can differ. Does not return the token."""
    tok = request.headers.get(USER_TOKEN_HEADER)
    if not tok:
        return {"error": "no x-forwarded-access-token on this request"}
    parts = tok.split(".")
    if len(parts) < 2:
        return {"note": "token is not a JWT (opaque); cannot read scopes client-side"}
    try:
        pad = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(pad))
    except (binascii.Error, ValueError, json.JSONDecodeError) as e:
        return {"error": f"could not decode token payload: {e}"}
    return {
        "scope": claims.get("scope") or claims.get("scopes"),
        "aud": claims.get("aud"),
        "token_type": claims.get("token_type"),
    }


@app.get("/healthz")
async def healthz():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("DATABRICKS_APP_PORT", 8000))
    uvicorn.run(application, host="0.0.0.0", port=port)
