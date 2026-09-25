"""Clients for the two Databricks surfaces this app talks to:

1. The AI Gateway MCP-services proxy  (POST {host}/ai-gateway/mcp-services/{fqn})
   -- used to list/call the tools of each underlying MCP service, speaking
   JSON-RPC 2.0 over streamable HTTP.
2. The Unity Catalog REST API  (GET {host}/api/2.1/unity-catalog/mcp-services...)
   -- used to enumerate available MCP services and read per-user login status.

Both are called with the *user's* OBO token so results respect the caller's
Unity Catalog grants and per-user MCP credentials.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from context import databricks_host

# A streamable-HTTP MCP client must advertise it can read both JSON and SSE, and
# declare a protocol version. The gateway tolerates a plain call without an
# initialize handshake (see the sentinel probe), but we do the handshake anyway
# so real upstream servers that require it work too.
_MCP_PROTOCOL_VERSION = "2025-06-18"
_ACCEPT = "application/json, text/event-stream"

_UC_MCP_SERVICES = "/api/2.1/unity-catalog/mcp-services"


class UpstreamError(Exception):
    """A JSON-RPC error returned by an upstream MCP service."""

    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    # -32042 is the gateway's "you're not signed in to this MCP service" code.
    @property
    def needs_login(self) -> bool:
        return self.code == -32042


def _parse_response(resp: httpx.Response, want_id: Any) -> dict:
    """Extract a single JSON-RPC message from a JSON or text/event-stream body."""
    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        chosen: dict | None = None
        for line in resp.text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            try:
                msg = json.loads(line[len("data:"):].strip())
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            if msg.get("id") == want_id or "result" in msg or "error" in msg:
                chosen = msg
                if msg.get("id") == want_id:
                    break
        if chosen is None:
            raise UpstreamError(-32000, "No JSON-RPC message found in SSE stream")
        return chosen
    return resp.json()


class GatewayMcpClient:
    """Talks JSON-RPC to one upstream MCP service through the AI Gateway proxy."""

    def __init__(self, token: str, timeout: float = 60.0):
        self._token = token
        self._host = databricks_host()
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _url(self, fqn: str) -> str:
        return f"{self._host}/ai-gateway/mcp-services/{fqn}"

    async def _rpc(
        self, fqn: str, method: str, params: dict | None, session_id: str | None
    ) -> tuple[dict, str | None]:
        rpc_id = uuid.uuid4().hex
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
        if params is not None:
            body["params"] = params
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": _ACCEPT,
            "MCP-Protocol-Version": _MCP_PROTOCOL_VERSION,
        }
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        resp = await self._client.post(self._url(fqn), json=body, headers=headers)
        new_session = resp.headers.get("mcp-session-id") or session_id
        if resp.status_code >= 400 and "text/event-stream" not in resp.headers.get(
            "content-type", ""
        ):
            raise UpstreamError(
                -32000, f"HTTP {resp.status_code} from {fqn}: {resp.text[:300]}"
            )
        msg = _parse_response(resp, rpc_id)
        if "error" in msg:
            err = msg["error"]
            raise UpstreamError(
                err.get("code", -32000), err.get("message", "unknown"), err.get("data")
            )
        return msg.get("result", {}), new_session

    async def _initialize(self, fqn: str) -> str | None:
        """Best-effort MCP handshake. Returns a session id if the server issued one."""
        try:
            _, session = await self._rpc(
                fqn,
                "initialize",
                {
                    "protocolVersion": _MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "virtual-mcp-app", "version": "0.1"},
                },
                None,
            )
            if session:
                await self._rpc(fqn, "notifications/initialized", {}, session)
            return session
        except (UpstreamError, httpx.HTTPError):
            return None  # fall back to direct calls, like the sentinel probe

    async def list_tools(self, fqn: str) -> list[dict]:
        session = await self._initialize(fqn)
        result, _ = await self._rpc(fqn, "tools/list", {}, session)
        return result.get("tools", [])

    async def call_tool(self, fqn: str, name: str, arguments: dict) -> dict:
        session = await self._initialize(fqn)
        result, _ = await self._rpc(
            fqn, "tools/call", {"name": name, "arguments": arguments}, session
        )
        return result


# --------------------------------------------------------------------------- #
# Unity Catalog REST helpers (list services, per-user credential status)
# --------------------------------------------------------------------------- #


async def list_mcp_services(token: str) -> list[dict]:
    """GET /api/2.1/unity-catalog/mcp-services -- requires the `unity-catalog` scope."""
    host = databricks_host()
    services: list[dict] = []
    page_token = ""
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            params = {"page_size": 200}
            if page_token:
                params["page_token"] = page_token
            resp = await client.get(
                f"{host}{_UC_MCP_SERVICES}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            services.extend(data.get("mcp_services", []))
            page_token = data.get("next_page_token", "")
            if not page_token:
                break
    return services


async def revoke_user_credential(token: str, name: str) -> int:
    """DELETE the caller's stored credential for one MCP service. Returns the HTTP
    status (404 = already had none). Used by the guided-revoke flow."""
    host = databricks_host()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.delete(
            f"{host}{_UC_MCP_SERVICES}/{name}/user-credentials",
            headers={"Authorization": f"Bearer {token}"},
        )
    return resp.status_code


async def user_credential_state(token: str, name: str) -> str:
    """Return login state for one service: 'ACTIVE', 'NEEDS_LOGIN', or 'NO_AUTH'.

    404 => the user has no stored credential => needs to log in.
    """
    host = databricks_host()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{host}{_UC_MCP_SERVICES}/{name}/user-credentials",
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code == 404:
        return "NEEDS_LOGIN"
    if resp.status_code >= 400:
        # Some services need no per-user auth; treat auth-not-required as done.
        return "NO_AUTH"
    state = (resp.json().get("provisioning_info") or {}).get("state", "")
    return "ACTIVE" if state == "ACTIVE" else "NEEDS_LOGIN"
