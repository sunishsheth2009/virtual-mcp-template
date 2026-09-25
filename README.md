# Virtual MCP Server (Databricks App prototype)

A prototype Databricks App that presents **one MCP endpoint** which is the union
of tools drawn from **several underlying Unity Catalog MCP services** (e.g.
github + slack + atlassian), and walks a user through logging in to each of them.

> ⚠️ Prototype / experimental. Lives under `experimental/` and has not been
> through review. Config is stored in-process (resets on container recycle).

## Quickstart — create your own app in ml-inference (2 steps)

```bash
git clone https://github.com/sunish-sheth_data/virtual-mcp-template.git
cd virtual-mcp-template && ./create_virtual_mcp.sh my-team-mcp
```

That creates + deploys an app on the `ml-inference` profile using the bundled
service mix, and prints the app URL. **One manual follow-up** (account admin, one
time per app) — the script prints the exact command: add the `unity-catalog`
scope to the new app's OAuth integration. Then open the app in incognito → run
**Guided Login** → your merged tools are live at `<app-url>/mcp`.

To choose a different set of MCP services, pass your own file:
`./create_virtual_mcp.sh my-app my-services.json` (see the script header for the
shape + a discovery command).

## What it does

The running app is a **ready MCP server** — the service selection is baked at
creation time, so you don't configure anything to use it.

1. **Home** (`/`): shows the MCP endpoint and the **live merged tool list**
   (post-login) — exactly what an agent sees. Fast to load (never blocks on the
   full catalog listing).
2. **Virtual MCP server** (`/mcp`, streamable HTTP): on `tools/list` it fans out
   to each configured service's `tools/list` through the AI Gateway
   (`POST /ai-gateway/mcp-services/{fqn}`), filters by your selectors, and returns
   one merged, namespaced (`{alias}__{tool}`) tool list. `tools/call` routes each
   call back to the owning service.
3. **Guided login** (`/login`): checks each underlying service's per-user
   credential (`GET .../mcp-services/{name}/user-credentials`; 404 = needs login)
   and pops the platform's own `/mcp-service-login?name=…` page for each service
   that still needs it, **one after another**, polling until every one is signed
   in. This is the "hack around `/mcp-service-login`": we drive that existing page
   in a popup and poll credential state instead of relying on a cross-origin
   `return_to`.
4. **Configure** (`/configure`, optional): the service/tool picker for tweaking
   the mix after creation — lists all MCP services
   (`GET /api/2.1/unity-catalog/mcp-services`) and lets you pick tools by
   checkbox or case-insensitive regex.

**Creation-time selection**: the mix comes from the `VIRTUAL_MCP_CONFIG` env var
(a JSON string) if set, else the bundled `config.json`. To stamp out your own
apps with different service mixes, see **`TEMPLATE.md`** (and
`create_virtual_mcp.sh`).

## Scopes (confirmed: `unity-catalog` + `ai-gateway`)

The app calls Unity Catalog + the AI Gateway **as the calling user** (OBO), so it
needs user authorization enabled (Public Preview) plus **both**:
- `ai-gateway` — proxy `tools/list`/`tools/call` (`/ai-gateway/mcp-services/{fqn}`).
  On the apps allowlist, so requested at creation via `user_api_scopes`.
- `unity-catalog` — list MCP services + per-user login status. NOT on the
  allowlist, so add it to the app's OAuth **custom-app-integration** as an account
  admin after creation (see `TEMPLATE.md`).

Missing `ai-gateway` → the home page shows an explicit `HTTP 403 ... required
scopes: ai-gateway` per service (diagnostics, not a hang). After granting, reopen
in incognito so the OBO token re-mints.

## Files

| File | Role |
|------|------|
| `app.py` | FastAPI: pages, JSON APIs, mounts the MCP server at `/mcp`. |
| `mcp_proxy.py` | Low-level MCP `Server` (2.x `on_list_tools`/`on_call_tool`) — dynamic proxy; `collect_tools` shared with `/api/tools`. |
| `upstream.py` | Gateway JSON-RPC client (JSON+SSE) + UC REST helpers. |
| `config.py` | Virtual-MCP selection (services + tool selectors); seeds from `VIRTUAL_MCP_CONFIG` env or `config.json`. |
| `context.py` | Per-request user-token contextvar + host/url resolution. |
| `pages.py` | Home (ready-server + tools), guided-login, and configure (picker) HTML/JS. |
| `config.json` | Seed selection. |
| `TEMPLATE.md` / `create_virtual_mcp.sh` | Stamp out your own apps with different service mixes. |

## Run locally

```bash
pip install -r requirements.txt
export DATABRICKS_HOST=https://<your-workspace>.cloud.databricks.com
export VIRTUAL_MCP_DEV_TOKEN=<a-user-oauth-token that can read MCP services + proxy tools>
python app.py     # http://localhost:8000
```

## Deploy (CLI — DABs needs Terraform which is egress-blocked in some envs)

```bash
databricks apps create -p <PROFILE> --json '{"name":"virtual-mcp","description":"..."}'
databricks sync . /Workspace/Users/<you>/virtual-mcp-app -p <PROFILE>
databricks apps deploy virtual-mcp --source-code-path /Workspace/Users/<you>/virtual-mcp-app -p <PROFILE>
```

Point your MCP client at `https://<app-host>/mcp`. The start command is
`python app.py` (the runtime does NOT shell-expand `${DATABRICKS_APP_PORT}` in
`command` args — app.py reads the port from the env itself).

**Deployed prototype** (ml-inference staging):
`https://virtual-mcp-1653573648247579.staging.aws.databricksapps.com`
(OAuth integration `861a272a-e721-4156-81cf-380beb23eddb` — add an MCP-read scope
to it per `TEMPLATE.md`).
