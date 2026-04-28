# Consulting-Tool – Phase 1

Internes Consulting-Werkzeug (Asana-Ersatz) für Kromeich Partner. Phase 1 deckt
Mandanten, Projekte, Aufgaben, Notizen und Dokumente ab. Phase 2 (zentrale
Team-Inbox), Phase 3 (Mandanten-Portal + Chat) und Phase 4 (WhatsApp) folgen.

## Tech-Stack

- **Next.js 15** (App Router, React 19, Server Actions)
- **PostgreSQL 16** + **Prisma**
- **Auth.js v5** mit Magic-Link via Nodemailer
- **Tailwind CSS**
- **Mailpit** als lokaler Mail-Catcher (für Magic-Link-Tests)
- **Docker Compose** für Postgres + Mailpit

## Lokales Setup

### Voraussetzungen

- Node.js ≥ 20
- Docker + Docker Compose

### Schritte

```bash
cd consulting-app

# 1. Dependencies installieren
npm install

# 2. .env aus Beispiel anlegen und anpassen
cp .env.example .env
# → AUTH_SECRET setzen: openssl rand -base64 32
# → TEAM_ADMIN_EMAILS auf eure Adressen setzen

# 3. Postgres + Mailpit starten
docker compose up -d

# 4. Datenbank-Schema anwenden
npm run db:push

# 5. Dev-Server starten
npm run dev
```

App läuft auf <http://localhost:3000>, Mailpit-Web-UI auf
<http://localhost:8025>.

### Erster Login

1. Auf <http://localhost:3000> die in `TEAM_ADMIN_EMAILS` eingetragene
   E-Mail eingeben → "Magic Link senden"
2. Mailpit öffnen (<http://localhost:8025>) → Magic-Link-Mail anklicken
3. Auf den Login-Link klicken → ihr seid eingeloggt und automatisch
   `TEAM_ADMIN`

## Funktionen Phase 1

- **Dashboard** mit eigenen Aufgaben + aktiven Projekten
- **Mandanten** anlegen und bearbeiten
- **Projekte** pro Mandant
- **Aufgaben** pro Projekt mit Status, Priorität, Zuweisung, Deadline
- **Notizen** (Markdown) pro Projekt
- **Dokumenten-Upload** (lokal in `storage/uploads/`)

## Verzeichnisstruktur

```
consulting-app/
├── app/
│   ├── (app)/              Geschützter Bereich (Login erforderlich)
│   │   ├── dashboard/
│   │   ├── clients/
│   │   ├── projects/
│   │   └── tasks/
│   ├── api/
│   │   ├── auth/[...nextauth]/   Auth.js
│   │   └── documents/[id]/       Datei-Download
│   └── login/
├── components/
│   ├── tasks/              Task-Liste + Status-Select
│   └── projects/           Notes- und Documents-Liste
├── lib/
│   ├── auth.ts             Auth.js-Konfiguration
│   ├── access.ts           Auth-Helper (requireUser, requireTeamMember)
│   ├── prisma.ts           Prisma-Client (Singleton)
│   └── utils.ts            Formatierung + Labels
├── prisma/
│   └── schema.prisma       Datenmodell
├── storage/uploads/        Dokumenten-Storage (gitignored)
└── docker-compose.yml      Postgres + Mailpit
```

## Roadmap

- **Phase 2 — zentrale Team-Inbox**: IMAP/SMTP-Anbindung, Posteingang im Tool,
  aus dem Tool antworten, Mail → Projekt-Zuordnung, Anhänge in
  Document-Storage.
- **Phase 3 — Mandanten-Portal + Chat**: Login-Rolle `CLIENT`, sichtbare
  Notizen/Dokumente per `visibility`-Flag, Realtime-Chat (SSE) pro Projekt.
- **Phase 4 — WhatsApp + Kontakt-Tool-Anbindung**: WhatsApp Business API über
  BSP, Kontakt-Stammdaten aus dem bestehenden `src/`-Python-Code übernehmen.

## Deployment-Hinweise (Production)

- `docker compose` auf eigenem Server (z.B. Hetzner Cloud)
- Reverse Proxy (Caddy/Traefik) mit Let's Encrypt davor
- `.env` mit echtem SMTP-Server statt Mailpit, `AUTH_URL` auf öffentliche
  Domain setzen
- `storage/uploads/` als Docker-Volume mounten
- Backups: `pg_dump` + Snapshot des Upload-Ordners
