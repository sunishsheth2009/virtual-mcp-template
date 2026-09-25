#!/usr/bin/env bash
# Create a new Virtual MCP app from this template on Databricks Apps.
#
#   ./create_virtual_mcp.sh <app-name> [services.json] [profile]
#
# Simplest form -- uses the bundled config.json (real ml-inference MCP services)
# and the ml-inference profile:
#   ./create_virtual_mcp.sh my-team-mcp
#
# To pick your own mix, pass a services.json (same shape as config.json):
#   {"services":[
#      {"name":"main.sunish_rsrc_policy_poc.gh_test_mcp","alias":"gh","include_regex":"get_.*|list_.*"},
#      {"name":"system.ai.genie_one_mcp","alias":"genie"}
#   ]}
# Discover real service names:
#   databricks api get /api/2.1/unity-catalog/mcp-services -p ml-inference \
#     | python3 -c "import sys,json;[print(s['name'].replace('mcp-services/','')) for s in json.load(sys.stdin)['mcp_services']]"
set -euo pipefail

APP="${1:?usage: create_virtual_mcp.sh <app-name> [services.json] [profile]}"
HERE="$(cd "$(dirname "$0")" && pwd)"
CFG="${2:-$HERE/config.json}"   # default: bundled real-services config
PROFILE="${3:-ml-inference}"

EMAIL="$(databricks current-user me -p "$PROFILE" -o json | python3 -c 'import sys,json;print(json.load(sys.stdin)["userName"])')"
WS="/Workspace/Users/${EMAIL}/${APP}"

# Stage the template + this app's chosen service mix as its config.json seed.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp "$HERE"/*.py "$HERE"/app.yaml "$HERE"/requirements.txt "$STAGE"/
cp "$CFG" "$STAGE"/config.json

# ai-gateway is on the apps user_api_scopes allowlist, so request it at create
# time (auto-granted on the OAuth integration). unity-catalog is NOT allowlisted,
# so it's added to the integration afterwards (see the reminder at the end).
echo ">> creating app '$APP' (requesting ai-gateway; unity-catalog added to the integration after)"
databricks apps create -p "$PROFILE" --json "{\"name\":\"$APP\",\"description\":\"Virtual MCP server (from template).\",\"user_api_scopes\":[\"ai-gateway\"]}" --no-wait || true

echo ">> syncing source to $WS"
databricks sync "$STAGE" "$WS" -p "$PROFILE" --full

echo ">> deploying"
databricks apps deploy "$APP" --source-code-path "$WS" -p "$PROFILE"

INTEG="$(databricks apps get "$APP" -p "$PROFILE" -o json | python3 -c 'import sys,json;print(json.load(sys.stdin).get("oauth2_app_integration_id",""))')"
URL="$(databricks apps get "$APP" -p "$PROFILE" -o json | python3 -c 'import sys,json;print(json.load(sys.stdin).get("url",""))')"
echo ""
echo "App URL:            $URL"
echo "OAuth integration:  $INTEG"
echo "Next (ACCOUNT ADMIN): add the unity-catalog scope to the integration (merges with existing):"
echo "  ACCT=<account-profile>"
echo "  databricks account custom-app-integration get $INTEG -p \$ACCT -o json >/tmp/ig.json"
echo "  python3 -c \"import json;d=json.load(open('/tmp/ig.json'));print(json.dumps({'scopes':sorted(set(d.get('scopes',[])+['unity-catalog']))}))\" >/tmp/sc.json"
echo "  databricks account custom-app-integration update $INTEG -p \$ACCT --json \"\$(cat /tmp/sc.json)\""
echo "Then open the app in incognito so the OBO token re-mints. Confirmed scope set: unity-catalog + ai-gateway."
