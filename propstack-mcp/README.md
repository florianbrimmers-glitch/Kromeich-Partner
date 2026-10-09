# Propstack MCP Server – Kromeich GmbH

Remote-MCP-Server auf Cloudflare Workers. Über ihn arbeitet das Team aus Claude heraus mit Propstack.
Basis ist die Cloudflare-Vorlage [`remote-mcp-google-oauth`](https://github.com/cloudflare/ai/tree/main/demos/remote-mcp-google-oauth).

Live unter `https://propstack-mcp.kromeichpartner.workers.dev/mcp`, als Organisations-Connector in Claude eingetragen.

- **Phase 1 (abgenommen 09.10.2026):** Login über Google, Propstack-Nutzer-Abgleich, `whoami`.
- **Phase 2:** Lese-Tools und Audit-Log in D1. Kein Tool schreibt nach Propstack.

## Tools (Phase 2)

| Tool | Zweck | Propstack-Endpunkt (V1) |
|---|---|---|
| `whoami` | Angemeldeter Nutzer und Propstack-ID | – |
| `search_contacts` / `get_contact` | Kontakte suchen bzw. abrufen | `GET /contacts`, `GET /contacts/:id` |
| `search_objects` / `get_object` | Objekte (Einheiten) suchen bzw. abrufen | `GET /units`, `GET /units/:id?new=1` |
| `search_deals` | Deals suchen und abrufen (Kontakt, Objekt, Phase, Preis) | `GET /client_properties` |
| `pipeline_status` | Pipelines mit Phasen; je Phase Anzahl, Summe Preis, gewichteter Wert | `GET /deal_pipelines`, `GET /client_properties` |
| `list_tags` | Merkmale je Entität mit IDs | `GET /groups`, `GET /super_groups` |
| `list_fields` | Custom-Felder je Entität | `GET /custom_field_groups` |
| `list_reference` | Objekt-Status, Kontakt-Quellen, Nutzer, Projekte mit IDs | `GET /property_statuses`, `/contact_sources`, `/brokers`, `/projects` |
| `aggregate` | Zählen nach Dimension, mit allen Such-Filtern; Deals je Phase mit Summen | `with_meta=1&per=1` → `meta.total_count` |

Grundsätze:
- **Kürzen:** Antworten enthalten nur relevante Felder (`src/propstack/mappers.ts`). Bei Kontakten werden Ausweis- und Steuernummer, Geburtsdaten, Einkommen, Nationalität und der Kundenportal-Token **nie** ausgegeben.
- **Begrenzen:** max. 50 Treffer pro Seite und max. 45 Propstack-Anfragen pro Tool-Aufruf. `aggregate` bricht bei mehr als 40 Gruppen mit einem Hinweis ab, statt Propstack zu fluten.
- **Fehler:** Propstack-Fehler (401/403/404/429/5xx) kommen als verständliche Meldung zurück, bei 429 mit Retry und Backoff. Interna werden nicht ausgegeben.
- **Sichtbarkeit:** Alle Abfragen laufen über einen API-Key (Entscheidung Florian). Jeder angemeldete Nutzer sieht alles, was der Key sieht. Propstack-Sichtbarkeitsregeln je Nutzer oder Team gelten im Connector nicht.

Bewusste Lücken: Ein einzelner Deal per ID und die Kontakt-Status-Liste sind nur in der V2-Doku vorhanden. Deals werden daher über `search_deals` abgerufen, Kontakte lassen sich nicht nach Status gruppieren.

## Audit-Log (D1)

Jeder Tool-Aufruf wird in `propstack-mcp-audit` (Tabelle `audit_log`, Schema in `migrations/`) protokolliert: Zeitpunkt, Mail, Propstack-ID, Tool, Parameter (max. 2000 Zeichen), Trefferzahl, Erfolg/Fehler, Dauer. Ergebnisdaten werden **nicht** gespeichert. Ein täglicher Cron (03:17 UTC) löscht Einträge, die älter als **12 Monate** sind. Bei Lese-Tools gilt „best effort“: Fällt das Log aus, läuft die Abfrage trotzdem und der Fehler wird geloggt. Ab Phase 3 (Schreiben) muss das Log vor jedem Write erfolgreich sein.

Auswerten (Cloudflare-Dashboard → D1 → `propstack-mcp-audit` → Console, oder `npx wrangler d1 execute AUDIT_DB --remote --command "…"`):

```sql
SELECT ts, user_email, tool, params, result_count, ok FROM audit_log ORDER BY ts DESC LIMIT 50;
```

## So funktioniert der Login

1. Claude registriert sich per Dynamic Client Registration (`/register`) und startet OAuth (`/authorize`).
2. Der Worker leitet zum Google-Login weiter (Scope `openid email profile`, Hinweis `hd=kromeichpartner.de`).
3. In `/callback` prüft der Worker serverseitig:
   - **3a** (`src/auth/google-id-token.ts`): Die Signatur des ID-Tokens wird gegen Googles JWKS geprüft (RS256). Außerdem `iss`, `aud`, `exp` und `iat`. `hd` muss `kromeichpartner.de` sein, `email_verified` muss `true` sein.
   - **3b** (`src/auth/broker-lookup.ts`): Zur Mail muss es in `GET /v1/brokers` genau einen Propstack-Nutzer geben. Der Abgleich ignoriert Groß- und Kleinschreibung. Treffer landen 1 h im KV-Cache (`propstack-broker:<mail>`). Abgelehnte Mails werden nie gecacht.
   - Schlägt eine Prüfung fehl, gibt es eine Seite „Zugriff verweigert“ (403) und kein Token. Ist Propstack nicht erreichbar, gibt es 503 (fail closed).
4. Das Token enthält nur `email`, `name` und `brokerId`. Das Google-Access-Token wird verworfen.
5. Access-Token-Laufzeit: 1 h. Bei jedem Refresh wird 3b erneut geprüft (`tokenExchangeCallback` in `src/index.ts`), Cache inklusive. Ohne Propstack-Nutzer bekommt der Client `invalid_grant` und muss sich neu anmelden.

## Einrichtung

Voraussetzungen: Node ≥ 20, Zugriff auf den Cloudflare-Account **kromeichpartner**, Admin in Google Workspace und in Propstack.

```bash
cd propstack-mcp
npm install
npm test            # Unit-Tests (Auth, Client, Filter, Mapper, Tools, Audit)
npm run type-check
```

### 1. Google-OAuth-Client (GCP)

1. Google Cloud Console → Projekt der Kromeich GmbH → **APIs & Dienste → OAuth-Zustimmungsbildschirm**.
   - Nutzertyp: **Intern**. Damit können sich nur Konten aus dem Workspace anmelden.
   - Scopes: `openid`, `email`, `profile`. Mehr nicht.
2. **Anmeldedaten → Anmeldedaten erstellen → OAuth-Client-ID**, Typ **Webanwendung**.
   - Autorisierte Weiterleitungs-URIs:
     - `https://propstack-mcp.kromeichpartner.workers.dev/callback` (Produktion)
     - `http://localhost:8788/callback` (lokale Tests; besser ein eigener Dev-Client)
3. Client-ID und Client-Secret notieren. Nur für die Secrets unten, nie ins Repo.

### 2. Propstack-API-Key

Propstack → **Verwaltung → API-Schlüssel**. Ein V1-Key, laut Spezifikation **ohne Löschrechte**. Ab Phase 2 braucht er **Leserechte** auf: Nutzer, Kontakte (inkl. Quellen), Objekte (inkl. Status), Projekte, Deals, Deal-Pipelines, Merkmale und Custom-Felder. Fehlt ein Recht, meldet das Tool „Zugriff verweigert (401/403)“.

### 3. Cloudflare: Login und KV

```bash
npx wrangler login                                 # mit dem Firmen-Account kromeichpartner
```

Der KV-Namespace `propstack-mcp-OAUTH_KV` (ID `759b347676ea454c98f8dbd171d4070f`) ist bereits angelegt und in `wrangler.jsonc` eingetragen. Die ID ist kein Secret.

### 4. Lokal testen (vor jedem Deployment)

```bash
cp .dev.vars.example .dev.vars    # .dev.vars ist gitignored
# Werte eintragen. COOKIE_ENCRYPTION_KEY: openssl rand -hex 32
npm run dev                       # http://localhost:8788
npx @modelcontextprotocol/inspector@latest
```

Im Inspector `http://localhost:8788/mcp` eintragen, verbinden, anmelden und `whoami` aufrufen. Dann die Abnahmefälle unten durchspielen.

### 5. Secrets und Deployment

Erst deployen, wenn alle Abnahmefälle lokal grün sind. Es gibt kein Deployment ohne Auth.
`wrangler secret put` für einen noch nicht existierenden Worker legt einen leeren Platzhalter-Worker an. Deshalb beim **ersten** Deployment die Secrets direkt mitschicken:

```bash
# Einmalig: Datei außerhalb des Repos anlegen, z. B. ~/propstack-mcp.secrets (Format wie .dev.vars):
#   GOOGLE_CLIENT_ID=...  GOOGLE_CLIENT_SECRET=...  COOKIE_ENCRYPTION_KEY=...  PROPSTACK_API_KEY=...
npx wrangler deploy --secrets-file ~/propstack-mcp.secrets
rm ~/propstack-mcp.secrets
```

Danach werden einzelne Secrets nur noch so geändert:

```bash
npx wrangler secret put PROPSTACK_API_KEY
npx wrangler secret put GOOGLE_CLIENT_ID
npx wrangler secret put GOOGLE_CLIENT_SECRET
npx wrangler secret put COOKIE_ENCRYPTION_KEY
npx wrangler deploy
```

Prüfen: `curl -i -X POST https://propstack-mcp.kromeichpartner.workers.dev/mcp` muss `401` liefern.

### 5b. Automatisches Deployment (ab Phase 2)

`.github/workflows/propstack-mcp-deploy.yml` veröffentlicht nach jedem Merge auf `main` (bei Änderungen in `propstack-mcp/`): Tests → D1-Migrationen → `wrangler deploy` → Smoke-Test (401 ohne Token). Einmalig einrichten:

1. Cloudflare-Dashboard → **Mein Profil → API-Tokens → Token erstellen** → Vorlage **„Cloudflare Workers bearbeiten“**. Zusätzlich die Berechtigung **Konto → D1 → Bearbeiten** hinzufügen und das Konto auf kromeichpartner beschränken.
2. GitHub → Repo → **Settings → Secrets and variables → Actions** → zwei Secrets anlegen:
   - `CLOUDFLARE_API_TOKEN` (Token aus Schritt 1)
   - `CLOUDFLARE_ACCOUNT_ID` (Cloudflare-Dashboard → Workers & Pages → rechts „Konto-ID“)

Ohne diese Secrets wird das Deployment mit einer Warnung übersprungen. Die Worker-Secrets (Google, Propstack, Cookie-Key) bleiben in Cloudflare, ein Deployment löscht sie nicht.

### 6. Connector in Claude eintragen

- **Team/Enterprise (empfohlen, einmal für alle):** Ein Org-Owner geht zu claude.ai → **Admin-Einstellungen → Connectors → Add custom connector**. Name: `Propstack`, URL: `https://propstack-mcp.kromeichpartner.workers.dev/mcp`. Client-ID und Secret leer lassen (Dynamic Client Registration).
- **Einzelner Nutzer:** claude.ai → **Einstellungen → Connectors → Add custom connector** mit derselben URL.
- Danach im Chat den Connector aktivieren und **Connect** wählen. Google-Login mit dem @kromeichpartner.de-Konto. Test: „Wer bin ich in Propstack?“ ruft `whoami` auf.

## Abnahme Phase 1

| Kriterium | So prüfen |
|---|---|
| Domain-Konto mit Propstack-Nutzer → richtige ID | Anmelden, `whoami` aufrufen, `propstack_user_id` mit Propstack → Verwaltung → Nutzer vergleichen |
| Privates Gmail → abgelehnt | Mit Gmail-Konto anmelden: Google blockt schon beim internen Client. Sonst zeigt der Worker 403 |
| Domain-Konto ohne Propstack-Nutzer → abgelehnt | Mit einem Funktionspostfach anmelden → 403 „kein aktiver Propstack-Nutzer“ |
| Kein Secret im Repo | `git grep -nE '(PROPSTACK_API_KEY|GOOGLE_CLIENT_SECRET|COOKIE_ENCRYPTION_KEY)\s*[=:]\s*\S{8,}|GOCSPX[-]|[0-9]+-[a-z0-9]{32}\.apps\.googleusercontent\.com'` liefert nichts |
| Unit-Tests 3a/3b | `npm test` (die CI läuft bei Änderungen in `propstack-mcp/`) |

## Abnahme Phase 2 (live in Claude prüfen)

Die Logik ist per Unit-Tests abgedeckt. Die echten Propstack-Antworten lassen sich aber nur mit dem Live-Key prüfen. Nach dem Deployment:

| Prüfung | Frage an Claude |
|---|---|
| Kontaktsuche + Detail | „Suche den Kontakt <Name> und zeig mir die Details.“ |
| Objektsuche mit Filtern | „Welche verfügbaren Mietobjekte über 1.000 m² haben wir in <Ort>?“ |
| Deals eines Objekts | „Welche Interessenten gibt es für Objekt <ID>?“ |
| Pipeline-Status | „Wie steht die Pipeline <Name>? Mit Summen je Phase.“ (Summen stichprobenartig mit Propstack vergleichen) |
| Merkmale / Felder / Stammdaten | „Welche Kontakt-Merkmale gibt es?“, „Welche Custom-Felder haben Objekte?“ |
| Auswertung | „Wie viele Kontakte haben wir je Quelle?“ (Gesamtzahl mit Propstack vergleichen) |
| Filter mit Listen | Suche mit zwei Merkmalen gleichzeitig. Prüft, ob Propstack `group[]=` versteht |
| Audit-Log | Danach in D1: `SELECT * FROM audit_log ORDER BY ts DESC LIMIT 10;` |

## Bekannte Grenzen (bewusste Entscheidungen Phase 1)

- **Aktiv-Status:** `GET /v1/brokers` hat laut Doku kein Aktiv-Flag. Jeder Nutzer, den V1 liefert, gilt als aktiv. **Einmal mit echtem Key prüfen:** Taucht ein deaktivierter Propstack-Nutzer noch in `/v1/brokers` auf? Wenn ja, greift das Offboarding nicht. Dann auf `GET /v2/brokers?email=…` umstellen, das hat `active`, `archived` und `blocked`.
- **Rollen:** Alle Propstack-Rollen dürfen sich anmelden. Ein Funktionspostfach, das in Propstack als (technischer) Nutzer existiert, kommt durch.
- **Offboarding-Verzögerung:** Access-Token 1 h plus Cache 1 h beim Refresh. Nach dem Deaktivieren in Propstack bleibt der Zugriff also noch bis zu ~2 h bestehen. Refresh-Tokens laufen 30 Tage (Standard der Library), werden aber stündlich gegen 3b geprüft.
- **Google-Konto sperren reicht nicht:** Der Refresh fragt Google nicht erneut. Offboarding heißt: den Propstack-Nutzer deaktivieren bzw. entfernen.
