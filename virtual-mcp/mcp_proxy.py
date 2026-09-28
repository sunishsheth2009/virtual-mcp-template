"""The virtual MCP server itself: a low-level MCP server whose tool list is the
union of the selected tools across every configured upstream MCP service, and
whose tool calls are routed back to the owning upstream through the AI Gateway.

Tool names are namespaced ``{alias}__{tool}`` so tools from different upstreams
never collide and every call is trivially routable back to its origin.

Targets the constructor-based handler API of the ``mcp`` SDK (2.x): handlers are
``async def (ctx, params)`` passed to ``Server(...)`` and return typed results.
"""

from __future__ import annotations

import asyncio
import os

import mcp.types as types
from mcp.server.lowlevel import Server

import config as cfg_mod
from context import databricks_host, get_user_token, app_base_url
from upstream import GatewayMcpClient, UpstreamError

SEP = "__"


def _split(namespaced: str) -> tuple[str, str]:
    alias, _, tool = namespaced.partition(SEP)
    return alias, tool


def _token_from_ctx(ctx) -> str | None:
    """The user's OBO token: from the request's forwarded header, else contextvar/env."""
    req = getattr(ctx, "request", None)
    if req is not None:
        try:
            hdr = req.headers.get("x-forwarded-access-token")
            if hdr:
                return hdr
        except AttributeError:
            pass
    return get_user_token() or os.environ.get("VIRTUAL_MCP_DEV_TOKEN")


def _login_hint(service_name: str) -> str:
    base = app_base_url() or databricks_host()
    direct = f"{databricks_host()}/mcp-service-login?name={service_name}"
    return (
        f"You are not signed in to the '{service_name}' MCP service. "
        f"Open {base}/login to authorize every service this virtual MCP needs, "
        f"or sign in to this one directly at {direct}, then retry."
    )


async def collect(token: str | None) -> tuple[list[types.Tool], list[dict]]:
    """Merged, selector-filtered, alias-prefixed tools across all configured
    services, plus a per-service diagnostic (why a service contributed 0 tools).
    Shared by the MCP `tools/list` handler and the app's /api/tools view."""
    cfg = cfg_mod.load()
    if not token or not cfg.services:
        return [], []

    client = GatewayMcpClient(token)
    try:
        async def fetch(sel: cfg_mod.ServiceSelection) -> tuple[list[types.Tool], dict]:
            diag = {"service": sel.name, "alias": sel.alias, "ok": False, "count": 0, "error": None}
            try:
                upstream_tools = await client.list_tools(sel.name)
            except UpstreamError as e:
                diag["error"] = "not signed in (do Guided Login)" if e.needs_login else e.message
                return [], diag
            out: list[types.Tool] = []
            for t in upstream_tools:
                tname = t.get("name", "")
                if not tname or not sel.matches(tname):
                    continue
                out.append(
                    types.Tool(
                        name=f"{sel.alias}{SEP}{tname}",
                        description=f"[{sel.alias}] {t.get('description', '')}".strip(),
                        inputSchema=t.get("inputSchema", {"type": "object"}),
                    )
                )
            diag["ok"] = True
            diag["count"] = len(out)
            return out, diag

        results = await asyncio.gather(*(fetch(s) for s in cfg.services))
    finally:
        await client.aclose()

    tools = [tool for group, _ in results for tool in group]
    diags = [d for _, d in results]
    return tools, diags


async def collect_tools(token: str | None) -> list[types.Tool]:
    tools, _ = await collect(token)
    return tools


async def on_list_tools(ctx, params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=await collect_tools(_token_from_ctx(ctx)))


async def call_tool_by_name(token: str | None, name: str, arguments: dict | None) -> dict:
    """Route a namespaced `alias__tool` call to its upstream service. Returns
    {ok, content, error, needs_login}, where content is the upstream MCP content
    list. Shared by the MCP `tools/call` handler and the app's /api/call view."""
    cfg = cfg_mod.load()
    if not token:
        return {"ok": False, "content": None, "error": "No user token; enable user authorization.", "needs_login": False}
    alias, tool = _split(name)
    sel = cfg.by_alias(alias)
    if sel is None or not tool:
        return {"ok": False, "content": None, "error": f"Unknown tool '{name}'.", "needs_login": False}
    if not sel.matches(tool):
        return {"ok": False, "content": None, "error": f"Tool '{tool}' is not exposed.", "needs_login": False}
    client = GatewayMcpClient(token)
    try:
        result = await client.call_tool(sel.name, tool, arguments or {})
    except UpstreamError as e:
        msg = _login_hint(sel.name) if e.needs_login else f"Upstream error {e.code}: {e.message}"
        return {"ok": False, "content": None, "error": msg, "needs_login": e.needs_login}
    finally:
        await client.aclose()
    return {
        "ok": not bool(result.get("isError", False)),
        "content": result.get("content"),
        "error": None,
        "needs_login": False,
    }


async def on_call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
    res = await call_tool_by_name(_token_from_ctx(ctx), params.name, params.arguments)
    if res["error"]:
        return _error(res["error"])
    content = res.get("content")
    blocks = (
        [_coerce_block(b) for b in content]
        if isinstance(content, list) and content
        else [types.TextContent(type="text", text=str(content))]
    )
    return types.CallToolResult(content=blocks, isError=not res["ok"])


def _error(message: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)], isError=True
    )


def _coerce_block(block: dict) -> types.ContentBlock:
    btype = block.get("type")
    if btype == "text":
        return types.TextContent(type="text", text=block.get("text", ""))
    if btype == "image":
        return types.ImageContent(
            type="image",
            data=block.get("data", ""),
            mimeType=block.get("mimeType", "application/octet-stream"),
        )
    # Unknown block type -> stringify so nothing is silently dropped.
    return types.TextContent(type="text", text=str(block))


server: Server = Server(
    "virtual-mcp-server",
    on_list_tools=on_list_tools,
    on_call_tool=on_call_tool,
)
