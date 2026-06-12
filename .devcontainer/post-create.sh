#!/usr/bin/env bash
# Läuft einmalig nach dem Erstellen des Codespace: .env vorbereiten,
# Dependencies installieren. Dauert ca. 1–2 Minuten.
set -e

cd "$(dirname "$0")/../consulting-app"

if [ ! -f .env ]; then
  echo "==> .env aus .env.example anlegen…"
  cp .env.example .env
  SECRET=$(openssl rand -base64 32 | tr -d '\n')
  sed -i "s|^AUTH_SECRET=.*|AUTH_SECRET=\"$SECRET\"|" .env
  sed -i "s|^TEAM_ADMIN_EMAILS=.*|TEAM_ADMIN_EMAILS=\"florian.brimmers@kromeichpartner.de\"|" .env
fi

echo "==> npm install (dauert einen Moment)…"
npm install --no-audit --no-fund

echo "==> Fertig. Beim Start des Codespace wird die App automatisch hochgefahren."
