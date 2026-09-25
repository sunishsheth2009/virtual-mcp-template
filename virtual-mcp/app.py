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

import contextlib
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings

import config as cfg_mod
import pages
from context import USER_TOKEN_HEADER, databricks_host, set_user_token
import mcp_proxy
from mcp_proxy import server
from upstream import user_credential_state

# Stateless proxy: every MCP request is independent, so no session store needed.
# Disable DNS-rebinding protection: the Databricks Apps reverse proxy fronts the
# app under a *.databricksapps.com host, which the localhost-oriented default
# allow-list would otherwise reject.
_session_manager = StreamableHTTPSessionManager(
    app=server,
    json_response=False,
    stateless=True,
    security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _token_from_request(request: Request) -> str | None:
    return request.headers.get(USER_TOKEN_HEADER) or os.environ.get("VIRTUAL_MCP_DEV_TOKEN")


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    async with _session_manager.run():
        yield


app = FastAPI(title="Virtual MCP Server", lifespan=lifespan)


@app.middleware("http")
async def capture_user_token(request: Request, call_next):
    # The user's OBO token rides on every request (pages + /mcp). Stash it so the
    # MCP handlers and API routes can act as the user against upstream services.
    set_user_token(_token_from_request(request))
    return await call_next(request)


# --------------------------------------------------------------------------- #
# The virtual MCP server itself (streamable HTTP), mounted as raw ASGI.
# --------------------------------------------------------------------------- #
async def _mcp_asgi(scope, receive, send):
    token = None
    for key, value in scope.get("headers", []):
        if key == USER_TOKEN_HEADER.encode():
            token = value.decode()
            break
    set_user_token(token or os.environ.get("VIRTUAL_MCP_DEV_TOKEN"))
    await _session_manager.handle_request(scope, receive, send)


app.mount("/mcp", _mcp_asgi)


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    # The running app is a ready MCP server: the landing page shows the endpoint
    # and (post-login) the live tool list. Service selection happens at creation
    # time (VIRTUAL_MCP_CONFIG) or on the /configure page.
    return pages.home_page(cfg_mod.load())


@app.get("/login", response_class=HTMLResponse)
async def login() -> str:
    return pages.login_page(cfg_mod.load())


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
            {"name": t.name, "description": t.description or "", "alias": t.name.split("__", 1)[0]}
            for t in tools
        ],
        "diagnostics": diagnostics,
    }


@app.get("/api/login-status")
async def api_login_status(request: Request):
    token = _token_from_request(request)
    if not token:
        return JSONResponse({"error": "no_user_token"}, status_code=401)
    cfg = cfg_mod.load()
    statuses = []
    for s in cfg.services:
        state = await user_credential_state(token, s.name)
        statuses.append({"name": s.name, "alias": s.alias, "state": state})
    return {"services": statuses, "login_base": f"{databricks_host()}/mcp-service-login"}


@app.get("/healthz")
async def healthz():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("DATABRICKS_APP_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
