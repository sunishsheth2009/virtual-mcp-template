#!/usr/bin/env bash
# Create a UC volume holding a Virtual MCP "preset" (the services/tools selection),
# so the "Virtual MCP Server" custom template can point at it: in the create
# wizard you pick this volume for the `config-volume` resource, and the app reads
# its mix from <volume>/virtual_mcp_config.json.
#
#   ./create_preset_volume.sh <catalog.schema.volume> [services.json] [profile]
#
# services.json shape (same as config.json); discover real MCP service names with:
#   databricks api get /api/2.1/unity-catalog/mcp-services -p ml-inference \
#     | python3 -c "import sys,json;[print(s['name'].replace('mcp-services/','')) for s in json.load(sys.stdin)['mcp_services']]"
set -euo pipefail

FQV="${1:?usage: create_preset_volume.sh <catalog.schema.volume> [services.json] [profile]}"
HERE="$(cd "$(dirname "$0")" && pwd)"
CFG="${2:-$HERE/config.json}"
PROFILE="${3:-ml-inference}"

CAT="${FQV%%.*}"; REST="${FQV#*.}"; SCH="${REST%%.*}"; VOL="${REST##*.}"
[ "$CAT.$SCH.$VOL" = "$FQV" ] || { echo "volume must be catalog.schema.volume"; exit 1; }

echo ">> ensuring volume $FQV"
databricks volumes create "$CAT" "$SCH" "$VOL" MANAGED -p "$PROFILE" 2>/dev/null \
  || echo "   (already exists or no create permission -- continuing)"

DEST="dbfs:/Volumes/$CAT/$SCH/$VOL/virtual_mcp_config.json"
echo ">> uploading preset $CFG -> $DEST"
databricks fs cp "$CFG" "$DEST" --overwrite -p "$PROFILE"

echo ""
echo "Preset ready in volume: $FQV"
echo "Create an app: Apps UI -> Custom templates -> 'Virtual MCP Server' -> pick volume '$FQV' -> Create."
echo "Then (account admin) add unity-catalog to the new app's OAuth integration, open in incognito, Guided Login."
