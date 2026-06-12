#!/usr/bin/env bash
# Läuft bei jedem Start des Codespace: Postgres + Mailpit hochfahren,
# Schema anwenden, Demo-Daten beim ersten Mal anlegen, Dev-Server starten.
set -e

cd "$(dirname "$0")/../consulting-app"

# --- AUTH_URL auf die Codespaces-URL des Ports 3000 setzen ---
# Auth.js verwendet diese URL für Magic-Link-Mails. Ohne das würden die
# Login-Links auf http://localhost:3000 zeigen — also auf das falsche
# Netz aus Browser-Sicht.
if [ -n "$CODESPACE_NAME" ] && [ -n "$GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN" ]; then
  APP_URL="https://${CODESPACE_NAME}-3000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
  MAILPIT_URL="https://${CODESPACE_NAME}-8025.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
  if grep -q "^AUTH_URL=" .env; then
    sed -i "s|^AUTH_URL=.*|AUTH_URL=\"$APP_URL\"|" .env
  else
    echo "AUTH_URL=\"$APP_URL\"" >> .env
  fi
else
  APP_URL="http://localhost:3000"
  MAILPIT_URL="http://localhost:8025"
fi

echo "==> Postgres + Mailpit starten…"
docker compose up -d

echo "==> Warte auf Postgres…"
for i in $(seq 1 60); do
  if docker compose exec -T postgres pg_isready -U consulting > /dev/null 2>&1; then
    echo "    bereit."
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "FEHLER: Postgres ist nach 60 s nicht erreichbar."
    echo "Logs:  docker compose logs postgres"
    exit 1
  fi
  sleep 1
done

echo "==> Schema in DB schreiben…"
npx prisma db push --skip-generate --accept-data-loss > /dev/null

if [ ! -f .seeded ]; then
  echo "==> Demo-Daten anlegen…"
  node scripts/seed-demo.mjs
  touch .seeded
fi

echo "==> Dev-Server starten (im Hintergrund)…"
pkill -f "next dev" >/dev/null 2>&1 || true
nohup npm run dev > /tmp/next-dev.log 2>&1 &

# Kurz warten, bis Next.js Port 3000 belegt — dann triggert Codespaces das
# automatische Öffnen des Browser-Tabs.
for i in $(seq 1 30); do
  if curl -s -o /dev/null http://localhost:3000/login; then
    break
  fi
  sleep 1
done

cat <<EOF

╔════════════════════════════════════════════════════════════════════╗
║  Kromeich Consulting — bereit                                      ║
╠════════════════════════════════════════════════════════════════════╣
║  App:     $APP_URL
║  Mailpit: $MAILPIT_URL
║                                                                    ║
║  Login: Deine Mail eingeben → "Magic Link senden" →                ║
║         Mailpit-Tab öffnen → Link in der Mail anklicken.           ║
║                                                                    ║
║  Dev-Server-Logs:  tail -f /tmp/next-dev.log                       ║
╚════════════════════════════════════════════════════════════════════╝
EOF
