#!/usr/bin/env bash
# Bringt den Codespace nach einem `git pull` auf den aktuellen Stand:
# - Prisma-Client neu generieren (Schema-Änderungen)
# - DB-Schema synchronisieren
# - Demo-Daten frisch aufsetzen
#
# Aufruf:   bash scripts/upgrade-demo.sh
set -e

cd "$(dirname "$0")/.."

echo "==> Prisma-Client neu generieren…"
npx prisma generate > /dev/null

echo "==> DB-Schema synchronisieren…"
npx prisma db push --skip-generate --accept-data-loss > /dev/null

echo "==> Demo-Daten zurücksetzen + neu anlegen…"
rm -f .seeded
node scripts/seed-demo.mjs --reset
touch .seeded

echo ""
echo "Fertig. Falls 'npm run dev' läuft, einmal Strg+C → 'npm run dev'."
