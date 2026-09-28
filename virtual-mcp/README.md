# Virtual MCP Server

One MCP endpoint that merges tools from several Unity Catalog MCP services (e.g.
GitHub + Slack + Genie) and routes each call to the right one. Pick which services
and tools to expose; sign in to them through a guided flow. Runs on Databricks Apps.

> Prototype / experimental — not formally reviewed.

## Overview

- **Aggregates** the tools of many MCP services behind a single `/mcp` endpoint,
  namespaced `<alias>__<tool>` so nothing collides.
- **Filters** each service's tools by an explicit list or a regex, so you expose
  only what you want.
- **Guided sign-in** walks the user through the platform's per-service login for
  every underlying service, and lets them revoke access.
- Which services/tools are combined is chosen **once, at app-creation time** — the
  running app has no configuration UI.

## Quickstart

**1. Choose your services.** Put a `virtual_mcp_config.json` in a Unity Catalog
volume (this is the "preset" the app reads):

```json
{
  "services": [
    { "name": "system.ai.github", "include_regex": "get_.*|list_.*" },
    { "name": "system.ai.slack",  "include_tools": ["slack_send_message"] },
    { "name": "system.ai.genie_one_mcp" }
  ]
}
```
`include_regex` / `include_tools` are optional (omit both = all tools). Helper:
`./create_preset_volume.sh <catalog.schema.volume> config.json <profile>`.

**2. Create the app.** In the Databricks UI: **Create app → Custom templates →
Virtual MCP Server**, and pick your volume for the `config-volume` resource.
(Or by CLI: `./create_virtual_mcp.sh <app-name>`.)

**3. Grant the scope — BEFORE first sign-in.** The app acts on Unity Catalog on
behalf of the user (list services, read status, **and revoke** credentials), so an
account admin grants the **writable** `unity-catalog` scope. Use bare
`unity-catalog`, **not `unity-catalog:read`** — read-only can list/status but
cannot revoke (there is no `unity-catalog:write`). Set both the requestable scope
and the pre-consented set (`ai-gateway` is requested automatically):

```bash
INTEG=$(databricks apps get <app-name> -o json | jq -r .oauth2_app_integration_id)
databricks account custom-app-integration get "$INTEG" -o json \
  | jq '{scopes:(.scopes + ["unity-catalog"] | unique)}' \
  | databricks account custom-app-integration update "$INTEG" --json @-
databricks account custom-app-integration update "$INTEG" \
  --json '{"user_authorized_scopes":["ai-gateway","unity-catalog"]}'
```

> Do this **before** anyone signs in. A user's OAuth consent grant is fixed at
> the scope granted on first sign-in — if the app ever hands out `unity-catalog:read`
> first, that user's grant sticks read-only (revoke 403s) and only recreating the
> app resets it.

**4. Sign in and use.** Open the app, click **Sign in** (guided per-service
login), then point your agent at `https://<app-url>/mcp`.

## Pages

| Path | Purpose |
|------|---------|
| `/` | The MCP endpoint + the live merged tool list |
| `/login` | Guided sign-in — redirects through each service's login, one by one |
| `/login-status` | Connections: per-service status, sign in, revoke / revoke all |
| `/mcp` | The MCP server agents connect to (streamable HTTP) |

## Config precedence

`VIRTUAL_MCP_CONFIG` env (inline JSON) → the picked `config-volume`'s
`virtual_mcp_config.json` → the bundled `config.json` default.

## Local development

```bash
pip install -r requirements.txt
export DATABRICKS_HOST=https://<workspace-host>
export VIRTUAL_MCP_DEV_TOKEN=<user OAuth token with unity-catalog + ai-gateway>
python app.py     # http://localhost:8000
```
