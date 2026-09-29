# Propstack-MCP-Server (Kromeich & Partner)

Ein MCP-Server auf Cloudflare Workers, über den das ganze Team aus Claude heraus Objekte in Propstack anlegen und pflegen kann – ohne dass jemand einen Propstack-API-Schlüssel sieht.

- **Anmeldung:** Cloudflare Access mit dem Firmenkonto. Zusätzlich lässt der Server nur Adressen auf `@kromeichpartner.de` zu.
- **Schlüssel:** Die Propstack-Schlüssel liegen nur als verschlüsselte Worker-Secrets in Cloudflare.
- **Hausregeln im Server:** Sie gelten für jeden Nutzer, nicht nur für eine Claude-Session.
  - `provisionspflichtig` wird nie gesetzt.
  - `mezzanineflache` (ein Euro-Feld) wird nie beschrieben.
  - Keine 0-m²-Flächen.
  - Keine öffentlichen Preisfelder.
  - Keine Eigentümernamen in Exposé-Texten.
  - Die Bemerkung wird nur vorne ergänzt.
  - Prüfungsaufgaben gehen immer an Lena.
  - Löschen gibt es nicht.
- **API-Macken** behandelt der Server intern: Einzelfelder werden einzeln geschrieben, Ganzzahlen korrekt übergeben, und nach jedem Schreiben wird über den `expand`-Kanal nachgelesen.
- **Protokoll:** Jeder Schreibzugriff wird mit Nutzer und Zeit festgehalten, in den Worker-Logs und im KV-Speicher `propstack-mcp-audit-kv` (1 Jahr).

## Werkzeuge

| Lesen | Schreiben |
|---|---|
| `einheit_lesen`, `einheiten_suchen` | `projekt_anlegen`, `projekt_aktualisieren`, `eigentuemer_setzen` |
| `projekt_lesen`, `projekte_suchen` | `einheit_anlegen`, `einheit_aktualisieren` |
| `kontakte_suchen` | `provision_setzen`, `vermietet_setzen`, `status_setzen` |
| `feld_nachschlagen` (Typ und Einheit eines Custom Fields) | `bemerkung_ergaenzen`, `bild_hochladen` |
| `pipelines_lesen`, `deals_lesen` | `pruefaufgabe_anlegen` (immer an Lena), `deals_aktualisieren` |

## Einmalige Einrichtung

Bereits erledigt:
- Die KV-Speicher `propstack-mcp-oauth-kv` und `propstack-mcp-audit-kv` sind angelegt, die IDs stehen in `wrangler.jsonc`.

### 1. Neue Propstack-Schlüssel ausstellen

Der bisherige Skill enthält die Propstack-Schlüssel und den Slack-Bot-Token im Klartext und ist an alle verteilt. Deshalb:

1. In Propstack unter *Einstellungen → API* zwei neue Schlüssel anlegen: einen für Objekte und einen für Aufgaben.
2. Die alten Schlüssel löschen, sobald der Server läuft.
3. Den Slack-Bot-Token in Slack neu ausstellen.

Die neuen Schlüssel nirgends hineinkopieren außer in Schritt 4.

### 2. Cloudflare Access (Zero Trust)

1. Cloudflare-Dashboard → **Zero Trust**. Beim ersten Mal den Teamnamen festlegen.
2. *Integrations → Identity providers*: **Google Workspace** (Firmenkonten) hinzufügen, als Rückfall One-time PIN.
3. *Access controls → Applications → Create new application → SaaS application*:
   - **Name:** `Propstack MCP`
   - **Protokoll:** OIDC
   - **Redirect URL:** `https://propstack-mcp.<dein-subdomain>.workers.dev/callback` (die genaue Adresse steht nach dem ersten Deploy unter *Workers & Pages*)
   - **Policy:** *Include → Emails ending in* `@kromeichpartner.de`
   - Unter *Advanced settings* **Refresh tokens** einschalten, damit sich niemand täglich neu anmelden muss.
4. Diese fünf Werte kopieren: Client ID, Client secret, Token endpoint, Authorization endpoint, Key endpoint.

### 3. Worker mit dem Repo verbinden (automatisches Deploy)

1. *Workers & Pages → Create → Import a repository* → `florianbrimmers-glitch/kromeich-partner`.
2. Einstellungen:
   - **Root directory:** `propstack-mcp`
   - **Build command:** `npm ci`
   - **Deploy command:** `npx wrangler deploy`
   - **Produktionsbranch:** der Branch, auf dem der Server liegt (nach dem Merge `main`)
3. Danach deployt jeder Push auf diesen Branch automatisch.

### 4. Secrets im Worker setzen

*Workers & Pages → propstack-mcp → Settings → Variables and Secrets*, jeweils als **Secret**:

| Secret | Wert |
|---|---|
| `PROPSTACK_OBJ_KEY` | neuer Objekte-Schlüssel |
| `PROPSTACK_TASK_KEY` | neuer Aufgaben-Schlüssel |
| `ACCESS_CLIENT_ID` | aus Schritt 2 |
| `ACCESS_CLIENT_SECRET` | aus Schritt 2 |
| `ACCESS_TOKEN_URL` | Token endpoint |
| `ACCESS_AUTHORIZATION_URL` | Authorization endpoint |
| `ACCESS_JWKS_URL` | Key endpoint |
| `COOKIE_ENCRYPTION_KEY` | Zufallswert, z. B. `openssl rand -hex 32` |

Danach einmal neu deployen (*Deployments → Retry*) oder einen Commit pushen.

### 5. In Claude für das Team freischalten

1. Claude (Admin) → *Organisationseinstellungen → Connectors → Custom connector hinzufügen*.
2. **URL:** `https://propstack-mcp.<dein-subdomain>.workers.dev/mcp`
3. Jedes Teammitglied verbindet den Connector einmal und meldet sich mit dem Firmenkonto an.

### 6. Skill austauschen

1. Den Ordner `skill/propstack-expose-workflow/` als ZIP packen.
2. In den Claude-Organisationseinstellungen unter *Skills* den bisherigen Skill `propstack-expose-workflow` damit ersetzen.

Die neue Version enthält **keine Schlüssel mehr**, sie arbeitet nur mit den MCP-Werkzeugen.

## Entwicklung

```sh
npm ci
npm test                      # Regeltests; Lesetest gegen Propstack nur mit PROPSTACK_OBJ_KEY in der Umgebung
npm run type-check
npx wrangler deploy --dry-run # Bauen ohne Veröffentlichen
```

Für lokale Tests `.dev.vars.example` nach `.dev.vars` kopieren (liegt in `.gitignore`).

## Protokoll lesen

Im Dashboard: *Workers & Pages → propstack-mcp → Logs* (Einträge `audit`). Oder im KV-Speicher `propstack-mcp-audit-kv`; die Schlüssel sind nach Zeit sortiert (`log:<Zeitstempel>:…`).
