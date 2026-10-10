#!/usr/bin/env bash
# Installiert den Scrapling MCP-Server, den .mcp.json als "scrapling" einbindet.
set -euo pipefail
cd "$(dirname "$0")/.."

pip install -r requirements-scrapling.txt
# Browser für fetch/stealthy_fetch (make_request/bulk_get brauchen keine)
scrapling install

command -v scrapling-mcp >/dev/null || {
  echo "scrapling-mcp nicht im PATH – venv aktivieren oder vollen Pfad in .mcp.json eintragen." >&2
  exit 1
}
echo "Scrapling MCP bereit. Claude Code neu starten und den Server 'scrapling' freigeben."
