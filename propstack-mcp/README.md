# Propstack MCP Server – Kromeich GmbH

Remote-MCP-Server auf Cloudflare Workers. Über ihn arbeitet das Team aus Claude heraus mit Propstack.
Basis ist die Cloudflare-Vorlage [`remote-mcp-google-oauth`](https://github.com/cloudflare/ai/tree/main/demos/remote-mcp-google-oauth).

Live unter `https://propstack-mcp.kromeichpartner.workers.dev/mcp`, als Organisations-Connector in Claude eingetragen.

- **Phase 1 (abgenommen 09.10.2026):** Login über Google, Propstack-Nutzer-Abgleich, `whoami`.
- **Phase 2 (abgenommen 14.10.2026):** Lese-Tools und Audit-Log in D1.
- **Phase 3:** Kontakte und Objekte anlegen und ändern, mit Dublettenprüfung, Snapshot und Gegenlesen. Keine Lösch-Tools.

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

- **Merkmale:** Propstack verknüpft mehrere Merkmale mit ODER. `tag_match: "all"` bildet die UND-Schnittmenge serverseitig (je Merkmal max. 5.000 Treffer). `aggregate` kann nur ODER und lehnt `all` ab.
- **Orte:** `query` ist Propstacks unscharfe Volltextsuche (findet z. B. auch „Leverkusener Str.“ in Mannheim). `city`/`zip_prefix` filtern exakt nach dem Ort- bzw. PLZ-Feld. Bei `status_ids` meldet `search_objects`, wie viele passende Objekte **keinen Status** haben.
- **Pipeline-Werte:** Deals ohne Phase dieser Pipeline (z. B. unqualifiziert) werden als `outside_stages` gemeldet. Hat kein Deal einen Preis, gibt es keine Summen statt „0 €“. Die Gewichtung nutzt die in Propstack hinterlegte Phasen-Wahrscheinlichkeit. Eine Phase „Absage“ sollte dort 0 % haben.

Bewusste Lücken: Ein einzelner Deal per ID und die Kontakt-Status-Liste sind nur in der V2-Doku vorhanden. Deals werden daher über `search_deals` abgerufen, Kontakte lassen sich nicht nach Status gruppieren.

## Schreib-Tools (Phase 3)

| Tool | Zweck |
|---|---|
| `create_contact` | Kontakt (Person) anlegen |
| `update_contact` | Kontakt ändern, Merkmale hinzufügen/entfernen (taggen), Notiz **anhängen** |
| `create_object` | Objekt (Einheit) anlegen |
| `update_object` | Objekt ändern (Eckdaten, Status, Preise, Flächen, Texte, Custom-Felder) |

**Ablauf jedes Writes:**
1. Eingaben prüfen. Custom-Felder werden gegen `list_fields` validiert (Name, Typ, Auswahlwerte), sonst verwirft Propstack sie still.
2. Dublettenprüfung (siehe unten). Bei Treffer wird nichts geschrieben, Claude bekommt den vorhandenen Datensatz.
3. **Write-Log mit Snapshot** in D1 (`write_log`): Nutzer, Anfrage, bei Updates die vorherigen Werte der geänderten Felder. **Fail-closed:** Kann der Eintrag nicht geschrieben werden, wird nichts nach Propstack geschrieben.
4. Schreiben. Bei 429 gibt es einen Retry. Bei 5xx/Timeout gibt es **keinen** Retry, die Meldung lautet „Status unklar, bitte prüfen“.
5. **Gegenlesen:** Der Datensatz wird neu geladen und jedes angefragte Feld verglichen. Was Propstack nicht übernommen hat, steht als `not_applied` im Ergebnis und im Write-Log (`done_with_gaps`).

**Regeln (Entscheidungen Florian):**
- Betreuer ist **immer** der angemeldete Nutzer. Propstack zeigt als Ersteller/Bearbeiter den API-Key-Inhaber. Wer es wirklich war, steht im Write-Log und in der Herkunftsnotiz („Angelegt über Claude (Propstack MCP) von …“).
- Kontakt-Dubletten: gleiche **persönliche E-Mail** blockiert immer. Ein Override ist dort nicht möglich, weil Propstack Kontakte per E-Mail zusammenführt und sonst den vorhandenen überschreiben würde. Ohne persönliche E-Mail blockieren gleiche **Mobilnummer** und **Name + Firma**. **Festnetz**, gleicher Name ohne Firma und **generische Adressen** (info@, vertrieb@ …) erzeugen nur Warnungen. **Systemadressen** (noreply …) werden als „vermutlich kein echter Kontakt“ gemeldet.
- Objekt-Dubletten: Adresse (Straße/Nr./PLZ normalisiert) **oder** Geokoordinaten ≤ 30 m **plus** Vermarktungsart **plus** Einheit blockieren. Gleiche Adresse mit anderer Vermarktungsart oder Einheit ist nur ein Hinweis.
- **Override** (`allow_duplicate_reason`): nur mit Begründung (≥ 15 Zeichen). Die Begründung wird im Write-Log protokolliert.
- **Testdaten:** `test: true` setzt das Merkmal `MCP-TEST`. Fehlt es, legt der Connector es einmalig an. Löschen kann nur Florian manuell.
- Notizen werden bei Updates nur ergänzt (mit Datum und Nutzer), nie ersetzt.

**Objekte – Regeln aus dem Notion-Feld-Mapping („Propstack API – Feld-Mapping“, Korrekturen) und dem Skill `propstack-expose-workflow`:**
- **Einzel-PUTs:** `rs_category`, `total_floor_space`, `industrial_area`, `hall_height`, `floor_load`, `broker_id`, `rented` und der Status verwirft Propstack im POST und in PUTs mit mehreren Feldern still (HTTP 200). Diese Felder werden nach dem Anlegen bzw. Ändern **einzeln** geschrieben. Ein fehlgeschlagener Einzel-PUT bricht die übrigen nicht ab und steht als `write_errors` im Ergebnis.
- **Gegenlesen:** Der Einzel-GET liefert Flächen, Kategorie, Hallenhöhe, Status-ID usw. gar nicht. Gelesen wird deshalb über `GET /v1/units?expand=1&per=100&property_ids[]=ID`, Status über `status.id`, Betreuer über `broker.id`. Frisch angelegte Objekte fehlen dort kurz, deshalb gibt es Retries nach 1,5 s und 4 s. Felder, die kein Kanal zurückliefert, stehen als `not_verifiable` im Ergebnis (nicht als Fehler). `get_object` nutzt denselben Weg.
- **Nicht angeboten:** `object_type` (leitet Propstack aus `rs_type` ab), `base_rent`/`total_rent` (Mietpreise nie öffentlich), `property_space_value` (berechnet), `note` (nicht schreibbar). `lat`/`lng` dienen nur der Dublettenprüfung und werden nicht gespeichert, weil sie unzuverlässig haften.
- **Preise (Entscheidung Florian, 15.10.2026):** Interne Preise (`intern_mietpreis_hallenflache` / `_buro` / `_mezzanine`) dürfen immer gesetzt werden. **Öffentliche Preise** (`price` nur bei BUY, `base_rent` nur bei RENT, Custom-Felder `mietpreis_*`) nur, wenn der Nutzer sie ausdrücklich ansagt oder auf Nachfrage bestätigt. Dann setzt Claude `public_price_confirmed: true`, und die Bestätigung steht im Write-Log. Ohne Bestätigung weist das Tool ab und fordert zur Nachfrage auf. Ohne öffentlichen Preis gilt `price_on_inquiry: true`, auch bei Kaufobjekten.
- **Interne Notizen** landen im Custom-Feld `bemerkung` (Herkunftsnotiz beim Anlegen, `bemerkung_append` hängt mit Datum und Nutzer an). Beschreibung, Lage, Ausstattung und Sonstiges sind **exposé-sichtbar**.
- **Custom-Felder:** Zahlen nur als nackte Zahl mit Dezimalpunkt. Text wie `"10,5"` wird abgewiesen, ebenso m²-Werte mit drei Nachkommastellen (Tausenderpunkt-Verdacht). Auswahlfelder werden per Name oder Option-ID angenommen und als **Option-ID** gesendet. **Gesperrt:** `provisionspflichtig` (nur `null`), `mezzanineflache` (Einheit Euro, stattdessen `mezzanineflache_gesamt`/`_verfugbar`), `bemerkung` (nur über `bemerkung_append`). `list_fields` zeigt Einheit, Option-IDs und Sperren.
- **Flächen gespiegelt:** Exposé und Teamansicht lesen die Flächen-Custom-Felder. Aus `industrial_area`, `usable_floor_space`, `total_floor_space` und `hall_height` füllt das Tool deshalb automatisch `lagerflache`/`_gesamt`, `buroflache`/`_gesamt`, `gebaudeflache_gesamt` und `hallenhohe`. Ist das Objekt nicht vermietet, kommen auch die `*_verfugbar`-Felder dazu, bei „Preis auf Anfrage“ außerdem `preisangabe`. Explizit übergebene Custom-Felder haben Vorrang. Bei Updates werden fehlende Varianten auch an Altobjekten nachgezogen.
- **Vermietet** (`rented: true`, Team-Prozess): Das Tool setzt automatisch `free_from` „vermietet“, `status_logistik` und `aktiv` auf Inaktiv und die verfügbaren Flächen auf „X m² (vermietet)“. `status_logistik`/`aktiv` stehen **nur bei Status Vermarktung oder Reserviert** (und nicht vermietet) auf Aktiv, sonst auf Inaktiv; sie werden beim Anlegen und bei jedem Status- oder Vermietungswechsel neu gesetzt. Grund: Objekte in Akquise oder Vorbereitung dürfen nicht in Automatisierungen wie Exposéversand oder Webseite landen. Testobjekte bekommen zusätzlich `kein_automatischer_exposeversand` = Ja. Den Status (163676 Abgeschlossen) setzt man weiterhin separat.
- **Flächen:** nie 0 m². `total_floor_space` = Halle + Mezzanine, ohne Büro (Regel seit 13.08.2026).
- `floor_load` (Bodentragkraft) in **kg/m²**. Propstack hängt die Einheit selbst an, 5 t/m² entsprechen also 5000.
- `unit_id` ist in ganz Propstack eindeutig. Bei Einzelobjekten ohne Projekt weglassen.
- Nicht enthalten: Firmenkontakte (brauchen Propstack-V2), Deals anlegen/ändern, Löschen.

## Phase 3b: Projekte, Eigentümer, Bilder, Prüfaufgabe (Entscheidung Florian, 15.10.2026)

| Tool | Zweck |
|---|---|
| `create_project` | Projekt (Standort) anlegen, optional mit Eigentümer. Dublettenprüfung über die Adresse |
| `set_project_owner` | Eigentümer-Kontakt (eigener Shop) mit einem Projekt verknüpfen |
| `add_images` | Bilder per öffentlicher https-URL an Objekt oder Projekt hängen |

- **Projekt:** Wrapper `project`, `country` DEU, Betreuer = Nutzer. Was Propstack im Sammel-Request still verwirft, wird erkannt und **einzeln nachgesetzt**. `note` ist nicht schreibbar; offene Punkte gehen über `review_notes` in die Prüfaufgabe. Testprojekte erkennt man am Namenspräfix `MCP-TEST`, weil Projekte keine Merkmale haben.
- **Eigentümer:** `PUT /projects/{id}` mit `relationships_attributes` (`related_client_id`, nicht `client_id`). Der Projekt-GET zeigt frische Verknüpfungen nicht, deshalb prüft das Tool über eine Gegenprobe. Es sendet denselben Aufruf ein zweites Mal; Propstack lehnt Doppelte mit „bereits mit dem Kontakt verbunden“ ab, und genau das bestätigt die Verknüpfung. Ist die Antwort nicht eindeutig, meldet das Tool „nicht prüfbar“ und vermerkt es im Write-Log. Die Relationship-Liste ließ sich live nicht zuverlässig auswerten. „Existiert bereits“ zählt als Erfolg. Bei einem fremden Shop kommt eine klare Meldung.
- **Bilder:** Nur öffentliche https-URLs (`remote_photo_url`). Ein Chat-Upload lässt sich über einen Remote-MCP nicht zuverlässig weiterreichen. Jede URL wird vorher geprüft (erreichbar, `Content-Type: image/*`, mit User-Agent), sonst entstehen leere Bildobjekte, die man nur in der UI löschen kann. Das erste Bild eines Objekts wird Titelbild.
- **Prüfaufgabe automatisch** nach `create_project` und `create_object`:
  - an Lena (254958), bei `test: true` an den Nutzer selbst;
  - `is_reminder: true`, fällig am nächsten Werktag 9:00, Text in ASCII;
  - Inhalt: Link, Ersteller, Lücken (`not_applied`/`not_verifiable`), Fehler, Hinweise, offene Punkte.
  - Schlägt sie fehl, bleibt der Datensatz angelegt; im Ergebnis steht `review_task.error`.
- **Bilder als Datei** (`image_upload_url`, für Claude Code und Cowork):
  - Das Tool liefert eine Einmal-Adresse `…/upload/images/<token>`: 15 Minuten gültig, an Nutzer und genau ein Objekt/Projekt gebunden, Token mit 256 Bit, liegt in KV.
  - Die Sitzung lädt per `curl -F "image[photo]=@bild.jpg" <adresse>` hoch. Der Worker reicht die Dateien per Multipart (`image[photo]`) an Propstack weiter, mit Write-Log (`tool = image_upload`) und Audit.
  - Erlaubt sind JPEG, PNG und WebP, erkannt an den Datei-Bytes. Max. 15 MB je Bild, max. 20 Bilder je Adresse.
  - Ist eine Datei ungültig, wird nichts hochgeladen. Der Propstack-Key verlässt den Server nicht.
- **API-Key:** Der Key „MCP-Server“ braucht in Propstack zusätzlich Schreibrechte für Projekte, Relationships, Bilder und Aufgaben.
- **Nicht enthalten:** Dokumente (PDF), `update_project`, Post in #objekte, Löschen. Im reinen claude.ai-Chat ohne Code-Ausführung gibt es keinen Datei-Upload, dort nur `add_images` per URL.

## Phase 4: Massenänderungen (plan → apply_plan → undo_plan)

| Tool | Zweck |
|---|---|
| `plan` | Auswahl (ID-Liste oder Filter wie bei den Such-Tools) und Änderung festlegen. **Ändert nichts in Propstack.** Liefert `plan_id`, Anzahl und Vorschau |
| `apply_plan` | Bestätigten Plan ausführen, in Etappen |
| `undo_plan` | Ausgeführten Plan rückgängig machen |

- **Änderungen:** Merkmale hinzufügen/entfernen (Kontakte und Objekte); bei Kontakten Betreuer, Quelle, Kontaktstatus; bei Objekten Status und vermietet; Custom-Felder. Bei Objekten mit Merkmalen braucht es eine Live-Prüfung, ob `add_group_ids`/`sub_group_ids` greifen. Das Ergebnis meldet es sonst als `not_applied`.
- **Regeln:**
  - Höchstens 500 Datensätze je Plan.
  - Die Plan-ID verfällt 10 Minuten nach dem Planen (Spezifikation). Danach muss neu geplant werden, weil sich der Bestand geändert haben kann.
  - Nur wer geplant hat, darf ausführen. Claude muss die Vorschau zeigen und eine ausdrückliche Bestätigung einholen.
- **Gleiche Regeln wie Einzeländerungen:** `apply_plan` schreibt jeden Datensatz über `update_contact` bzw. `update_object`. Es gelten dieselben Prüfungen (Einzel-PUTs, Spiegelung, Preissperre, aktiv/inaktiv, Gegenlesen). Jeder Datensatz bekommt einen eigenen Write-Log-Eintrag (`tool = apply_plan:<id>`).
- **Etappen:** Pro Tool-Aufruf höchstens ~40 Propstack-Requests. Das reicht für etwa 13 Kontakte oder 4–8 Objekte. Claude ruft `apply_plan` erneut auf, bis `remaining = 0`. Bei unklarem Propstack-Status (5xx/Timeout/429) hält der Lauf an. Mit Workers Paid lässt sich das Budget erhöhen (`BULK_REQUEST_BUDGET`).
- **Rückgängig:** 7 Tage lang (Entscheidung Florian), jeder Nutzer darf es auslösen.
  - Je Datensatz wird der gesicherte Stand vorher hergestellt, als Rohwert und nicht als Anzeigewert.
  - Felder, die seitdem jemand anders geändert hat, werden **übersprungen** und gemeldet.
  - Merkmale werden nur zurückgenommen, wenn der Plan sie wirklich gesetzt bzw. entfernt hat.
  - Bemerkungen werden nie zurückgesetzt.
- **Speicher:** D1-Tabellen `bulk_plan` und `bulk_item` (`migrations/0003_bulk_plans.sql`), Löschfrist 12 Monate per Cron.

Write-Log auswerten:

```sql
SELECT ts, user_email, tool, entity, entity_id, status, not_applied, override_reason FROM write_log ORDER BY id DESC LIMIT 20;
```

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

Propstack → **Verwaltung → API-Schlüssel**. Ein V1-Key, laut Spezifikation **ohne Löschrechte**. Ab Phase 2 braucht er **Leserechte** auf: Nutzer, Kontakte (inkl. Quellen), Objekte (inkl. Status), Projekte, Deals, Deal-Pipelines, Merkmale und Custom-Felder. Ab Phase 3 zusätzlich **Anlegen und Bearbeiten** von Kontakten und Objekten sowie **Anlegen** von Merkmalen (nur für `MCP-TEST`). **Keine Löschrechte.** Fehlt ein Recht, meldet das Tool „Zugriff verweigert (401/403)“.

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

### 5c. Nach einem Deployment mit neuen oder geänderten Tools

Claude speichert die Tool-Liste zwischen. Nach jedem Deployment, das Tools hinzufügt oder ändert:
1. **Organisationseinstellungen → Konnektoren → Propstack → Tools → neu laden** (Org-Owner).
2. Jede Person: **Anpassen → Konnektoren → Propstack** → Tools neu laden bzw. trennen und neu verbinden. Danach einen **neuen** Chat öffnen.

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

Ergebnis des ersten Live-Tests (09.10.2026) und Korrekturen: Merkmale wurden per ODER verknüpft (78 + 85 → 135 statt 28), jetzt gibt es `tag_match`. Die Ortssuche war unscharf (Mannheim bei „Leverkusen“), jetzt gibt es `city`/`zip_prefix`. Objekte ohne Status fielen stillschweigend weg, jetzt werden sie gemeldet. Betreuer kamen nur als ID, jetzt mit `broker_name`. Pipeline-Summen zeigten 0 € ohne Hinweis, jetzt `values_available`/`outside_stages`. Datenbefunde (kein Code): Keine Kontakte haben eine Quelle gesetzt, Deals haben keine Preise, „Absage“ ist in Propstack mit 5 % gewichtet, und `last_contact_at` liegt teils in der Zukunft.

## Bekannte Grenzen (bewusste Entscheidungen Phase 1)

- **Aktiv-Status:** `GET /v1/brokers` hat laut Doku kein Aktiv-Flag. Jeder Nutzer, den V1 liefert, gilt als aktiv. **Einmal mit echtem Key prüfen:** Taucht ein deaktivierter Propstack-Nutzer noch in `/v1/brokers` auf? Wenn ja, greift das Offboarding nicht. Dann auf `GET /v2/brokers?email=…` umstellen, das hat `active`, `archived` und `blocked`.
- **Rollen:** Alle Propstack-Rollen dürfen sich anmelden. Ein Funktionspostfach, das in Propstack als (technischer) Nutzer existiert, kommt durch.
- **Offboarding-Verzögerung:** Access-Token 1 h plus Cache 1 h beim Refresh. Nach dem Deaktivieren in Propstack bleibt der Zugriff also noch bis zu ~2 h bestehen. Refresh-Tokens laufen 30 Tage (Standard der Library), werden aber stündlich gegen 3b geprüft.
- **Google-Konto sperren reicht nicht:** Der Refresh fragt Google nicht erneut. Offboarding heißt: den Propstack-Nutzer deaktivieren bzw. entfernen.
