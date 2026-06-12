# Consulting-Tool – Phase 1 + 2

Internes Consulting-Werkzeug (Asana-Ersatz) für Kromeich Partner.

- **Phase 1** ✅ — Mandanten, Projekte, Aufgaben, Notizen, Dokumente
- **Phase 2** ✅ — zentrale Team-Inbox: E-Mails empfangen (IMAP), aus dem Tool
  antworten (SMTP, korrektes Threading), Mails Projekten zuordnen, Aufgaben
  aus Mails erstellen, Anhänge ins Projekt übernehmen
- **Phase 3** (geplant) — Mandanten-Portal + Chat
- **Phase 4** (geplant) — WhatsApp Business API

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

### Demo-Daten (empfohlen für den ersten Eindruck)

```bash
node scripts/seed-demo.mjs          # Mandanten, Projekte, Aufgaben + gefüllte Inbox
node scripts/seed-demo.mjs --reset  # Demo-Daten löschen und neu anlegen
```

Damit ist die Inbox sofort mit 3 Beispiel-Threads gefüllt — ohne dass ein
echtes Postfach verbunden sein muss. Antworten aus der Demo-Inbox gehen an
Mailpit (<http://localhost:8025>).

## Funktionen

- **Dashboard** mit eigenen Aufgaben + aktiven Projekten
- **Zentrale Inbox** (`/inbox`): Threads mit Filter (Ungelesen / Mir zugewiesen /
  Archiv) und Suche, Antworten + neue Mails direkt aus dem Tool,
  Projekt-Zuordnung, Team-Zuweisung ("Du kümmerst dich"),
  "Aufgabe daraus erstellen", Anhänge ins Projekt übernehmen
- **Mandanten** anlegen und bearbeiten
- **Projekte** pro Mandant, inkl. zugeordneter E-Mail-Kommunikation
- **Aufgaben** pro Projekt mit Status, Priorität, Zuweisung, Deadline
- **Notizen** (Markdown) pro Projekt
- **Dokumenten-Upload** (lokal in `storage/uploads/`)
- **Einstellungen**: E-Mail-Konten (IMAP/SMTP) und Team-Übersicht

### Echtes Postfach verbinden

Unter **Einstellungen → E-Mail-Konten**:

- **Gmail / Google Workspace**: `imap.gmail.com` (993) / `smtp.gmail.com`
  (587) mit einem [App-Passwort](https://support.google.com/accounts/answer/185833)
  (2FA muss aktiviert sein)
- **Andere Anbieter** (IONOS, Strato, …): IMAP-/SMTP-Daten des Anbieters

Mails abrufen: Button **↻ Synchronisieren** in der Inbox, oder automatisch
per Cron (alle 5 Min.):

```bash
curl -X POST -H "Authorization: Bearer $CRON_SECRET" https://…/api/email/sync
```

> ⚠️ Postfach-Passwörter liegen aktuell unverschlüsselt in der Datenbank —
> für den selbst gehosteten Einsatz im kleinen Team akzeptabel,
> at-rest-Verschlüsselung steht auf der Roadmap. Eingehende Mail-Adressen,
> die zu Mandanten passen, werden automatisch deren aktivstem Projekt
> zugeordnet.

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

- **Phase 3 — Mandanten-Portal + Chat**: Login-Rolle `CLIENT`, sichtbare
  Notizen/Dokumente per `visibility`-Flag, Realtime-Chat (SSE) pro Projekt.
- **Phase 4 — WhatsApp + Kontakt-Tool-Anbindung**: WhatsApp Business API über
  BSP, Kontakt-Stammdaten aus dem bestehenden `src/`-Python-Code übernehmen.
- **Härtung**: Verschlüsselung der Postfach-Passwörter, HTML-Mail-Darstellung
  (aktuell wird der Text-Part angezeigt), Mehrfach-Ordner-Sync (aktuell INBOX).

## Deployment-Hinweise (Production)

- `docker compose` auf eigenem Server (z.B. Hetzner Cloud)
- Reverse Proxy (Caddy/Traefik) mit Let's Encrypt davor
- `.env` mit echtem SMTP-Server statt Mailpit, `AUTH_URL` auf öffentliche
  Domain setzen
- `storage/uploads/` als Docker-Volume mounten
- Backups: `pg_dump` + Snapshot des Upload-Ordners
