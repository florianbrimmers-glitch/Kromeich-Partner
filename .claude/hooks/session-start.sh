#!/bin/bash
# SessionStart-Hook: die API-Korrekturen wieder in den Propstack-Skill eintragen.
#
# Warum: ~/.claude/skills/synced/ wird beim Container-Start aus der Skill-Quelle neu
# geschrieben. Korrekturen, die dort von Hand eingetragen werden, sind danach weg -
# am 19.08.2026 zweimal an einem Tag passiert, und in der Zwischenzeit stand die
# widerlegte Aussage "mezzanineflache direkt setzen wirkungslos" wieder im Skill.
#
# Die Skill-Dateien selbst liegen NICHT in diesem Repo: sie enthalten zwei
# Propstack-API-Keys und einen Slack-Bot-Token im Klartext. Versioniert werden nur die
# Korrekturen in scripts/skill_korrekturen.py, die nach jedem Reset neu angewendet
# werden. Das Skript ist idempotent und meldet UNKLAR, wenn sich die Skill-Quelle so
# geaendert hat, dass ein Anker nicht mehr passt.
set -uo pipefail

REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
SKRIPT="$REPO/scripts/skill_korrekturen.py"
BERICHT="$REPO/.claude/hooks/letzte-spiegelung.log"

[ -f "$SKRIPT" ] || { echo "skill_korrekturen.py fehlt - keine Skill-Pflege"; exit 0; }

{
  echo "Skill-Korrekturen $(date -Is)"
  python3 "$SKRIPT"
  echo "--- Gegenprobe ---"
  python3 "$SKRIPT" --pruefen
} > "$BERICHT" 2>&1
ergebnis=$?

if [ "$ergebnis" -eq 0 ]; then
  echo "Propstack-Skill: alle API-Korrekturen eingetragen (Bericht: .claude/hooks/letzte-spiegelung.log)"
else
  echo "ACHTUNG: Propstack-Skill-Korrekturen unvollstaendig (Code $ergebnis)."
  echo "Die Skill-Quelle hat sich vermutlich geaendert. Bericht:"
  sed 's/^/    /' "$BERICHT"
fi
exit 0
