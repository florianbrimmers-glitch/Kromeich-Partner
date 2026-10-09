# Propstack MCP Server – Kromeich GmbH

Remote-MCP-Server auf Cloudflare Workers. Über ihn arbeitet das Team aus Claude heraus mit Propstack.
Basis ist die Cloudflare-Vorlage [`remote-mcp-google-oauth`](https://github.com/cloudflare/ai/tree/main/demos/remote-mcp-google-oauth).

**Stand: Phase 1.** Login über Google und genau ein Tool: `whoami`.

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
npm test            # Unit-Tests der Prüflogik 3a/3b
npm run type-check
```

### 1. Google-OAuth-Client (GCP)

1. Google Cloud Console → Projekt der Kromeich GmbH → **APIs & Dienste → OAuth-Zustimmungsbildschirm**.
   - Nutzertyp: **Intern**. Damit können sich nur Konten aus dem Workspace anmelden.
   - Scopes: `openid`, `email`, `profile`. Mehr nicht.
2. **Anmeldedaten → Anmeldedaten erstellen → OAuth-Client-ID**, Typ **Webanwendung**.
   - Autorisierte Weiterleitungs-URIs:
     - `https://propstack-mcp.<subdomain>.workers.dev/callback` (Produktion; die Subdomain steht im Cloudflare-Dashboard unter Workers → Subdomain)
     - `http://localhost:8788/callback` (lokale Tests; besser ein eigener Dev-Client)
3. Client-ID und Client-Secret notieren. Nur für die Secrets unten, nie ins Repo.

### 2. Propstack-API-Key

Propstack → **Verwaltung → API-Schlüssel**. Ein V1-Key mit Leserecht auf Nutzer genügt für Phase 1. Laut Spezifikation hat der Key keine Löschrechte.

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

Prüfen: `curl -i -X POST https://propstack-mcp.<subdomain>.workers.dev/mcp` muss `401` liefern.

### 6. Connector in Claude eintragen

- **Team/Enterprise (empfohlen, einmal für alle):** Ein Org-Owner geht zu claude.ai → **Admin-Einstellungen → Connectors → Add custom connector**. Name: `Propstack`, URL: `https://propstack-mcp.<subdomain>.workers.dev/mcp`. Client-ID und Secret leer lassen (Dynamic Client Registration).
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

## Bekannte Grenzen (bewusste Entscheidungen Phase 1)

- **Aktiv-Status:** `GET /v1/brokers` hat laut Doku kein Aktiv-Flag. Jeder Nutzer, den V1 liefert, gilt als aktiv. **Einmal mit echtem Key prüfen:** Taucht ein deaktivierter Propstack-Nutzer noch in `/v1/brokers` auf? Wenn ja, greift das Offboarding nicht. Dann auf `GET /v2/brokers?email=…` umstellen, das hat `active`, `archived` und `blocked`.
- **Rollen:** Alle Propstack-Rollen dürfen sich anmelden. Ein Funktionspostfach, das in Propstack als (technischer) Nutzer existiert, kommt durch.
- **Offboarding-Verzögerung:** Access-Token 1 h plus Cache 1 h beim Refresh. Nach dem Deaktivieren in Propstack bleibt der Zugriff also noch bis zu ~2 h bestehen. Refresh-Tokens laufen 30 Tage (Standard der Library), werden aber stündlich gegen 3b geprüft.
- **Google-Konto sperren reicht nicht:** Der Refresh fragt Google nicht erneut. Offboarding heißt: den Propstack-Nutzer deaktivieren bzw. entfernen.
