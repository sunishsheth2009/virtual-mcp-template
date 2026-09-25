# Using this as a Databricks Apps template

Goal: let anyone stamp out their **own** virtual MCP app by mixing & matching as
many underlying MCP services as they want. The service selection is decided at
**creation time** (baked into the app), so once the app is running it's just a
ready MCP server — open it and you see the merged tool list post-login. No
in-app configuration step is required (though `/configure` is still there to
tweak the mix later).

There are three ways to use it, from most-lightweight to most-integrated.

## 1. One-shot creator script (works today)

`create_virtual_mcp.sh` stamps out a new app with whatever service mix you pass:

```bash
cat > my-mix.json <<'JSON'
{"services":[
  {"name":"system.ai.github","alias":"github","include_regex":"get_.*|list_.*"},
  {"name":"system.ai.slack","alias":"slack"},
  {"name":"cat.schema.jira","alias":"jira","include_tools":["create_issue","get_issue"]}
]}
JSON

./create_virtual_mcp.sh my-team-mcp my-mix.json ml-inference
```

It creates the app (no `user_api_scopes` — see scopes below), bakes `my-mix.json`
as the app's `config.json`, syncs, deploys, and prints the app URL + OAuth
integration id. Run it again with a different name + JSON for another mix.

## 2. Clone a shared git repo, then run the creator script

> NOTE: `databricks apps init --template` is **AppKit-only** (it requires an
> `appkit.plugins.json` and scaffolds a Node/TS app). This is a Python/FastAPI
> app, so it is NOT consumable via `apps init`. Share it as a plain git repo and
> consume it with `git clone` + the creator script instead.

```bash
git clone <git-url-hosting-this-template> virtual-mcp-template
cd virtual-mcp-template
# edit services.json to pick your mix, then:
./create_virtual_mcp.sh my-team-mcp services.json ml-inference
```

The selection is provided by `config.json` (or the `VIRTUAL_MCP_CONFIG` env var,
same JSON shape). If you want a real `apps init` template or a gallery card, the
app would need to be rebuilt on AppKit (Node/TS) — see option 3.

## 3. Databricks Apps gallery entry (the "proper" path)

The gallery reads templates from `apps/deploy/default-app-templates.jsonnet`
(and `app-template-app-manifests.jsonnet`), whose entries point at
`https://github.com/databricks/app-templates.git` + a `path` subfolder. To list
this template in the gallery you must (a) push this folder into that repo as e.g.
`virtual-mcp-server/`, then (b) add a catalog entry:

```jsonnet
{
  name: "Virtual MCP Server",
  use_case: "agents",
  git_repo: "https://github.com/databricks/app-templates.git",
  git_provider: "github",
  path: "virtual-mcp-server",
  description: "One MCP endpoint that merges tools from several Unity Catalog MCP services; guided per-service login.",
  resources: [],
  // Requesting unity-catalog isn't accepted by the apps user_api_scopes
  // allowlist by default; grant an MCP-read scope on the app's OAuth
  // integration after creation instead (see below).
  user_api_scopes: [],
}
```

> Not added to the live jsonnet here on purpose: the catalog entry is only valid
> once the template code exists in `databricks/app-templates`, otherwise the
> gallery 404s. Submit (a) + (b) together.

## Scopes (all three paths) — CONFIRMED set: `unity-catalog` + `ai-gateway`

The app talks to Unity Catalog (list MCP services + per-user login status) and
the AI Gateway (tool proxy `tools/list`/`tools/call`) **as the calling user**
(OBO). Both scopes are required — the tool proxy 403s without `ai-gateway`, the
listing 403s without `unity-catalog`.

- **`ai-gateway`** is on the apps `user_api_scopes` allowlist, so it's requested
  automatically at creation (`create_virtual_mcp.sh` passes it; `app.yaml` /
  `databricks.yml` declare it).
- **`unity-catalog`** is NOT on the allowlist (a bare `unity-catalog` in
  `user_api_scopes` is rejected as "not a valid scope"), so add it to the app's
  OAuth **custom-app-integration** as an account admin after creation (per the
  "Databricks Apps OBO add custom scopes" doc):

```bash
INTEG=<integration_id>   # from `databricks apps get <app> -o json` -> oauth2_app_integration_id
ACCT=<account-profile>
databricks account custom-app-integration get "$INTEG" -p "$ACCT" -o json >/tmp/ig.json
python3 -c "import json;d=json.load(open('/tmp/ig.json'));print(json.dumps({'scopes':sorted(set(d.get('scopes',[])+['unity-catalog']))}))" >/tmp/sc.json
databricks account custom-app-integration update "$INTEG" -p "$ACCT" --json "$(cat /tmp/sc.json)"
```

Then open the app in **incognito** (or clear its cookie) so the OBO token
re-mints with the new scope. Requires workspace **user authorization** enabled.
