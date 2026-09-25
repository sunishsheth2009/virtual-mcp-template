"""Per-request context shared between the FastAPI layer and the MCP handlers.

The Databricks Apps platform forwards the calling user's token on every request
(both the browser pages and the /mcp MCP traffic) via the
``x-forwarded-access-token`` header when user authorization is enabled. The MCP
proxy needs that token to talk to upstream MCP services *as the user* so that
per-user credential checks and the ``-32042`` "not signed in" elicitation fire
correctly. We stash it in a contextvar so the low-level MCP handlers -- which do
not otherwise see the raw ASGI request -- can reach it.
"""

from __future__ import annotations

import os
from contextvars import ContextVar

# The user's OBO token for the in-flight request, or None (local dev / SP-only).
_user_token: ContextVar[str | None] = ContextVar("user_token", default=None)

USER_TOKEN_HEADER = "x-forwarded-access-token"


def set_user_token(token: str | None) -> None:
    _user_token.set(token)


def get_user_token() -> str | None:
    return _user_token.get()


def databricks_host() -> str:
    """Workspace host, e.g. https://my-workspace.cloud.databricks.com (no trailing slash)."""
    host = os.environ.get("DATABRICKS_HOST", "").rstrip("/")
    if host and not host.startswith("http"):
        host = f"https://{host}"
    return host


def app_base_url() -> str:
    """Public base URL of this app, used to build return_to links for the login chain.

    Databricks injects DATABRICKS_APP_URL for deployed apps; fall back to a
    configurable override for local testing.
    """
    return (
        os.environ.get("DATABRICKS_APP_URL")
        or os.environ.get("VIRTUAL_MCP_APP_URL", "")
    ).rstrip("/")
