# Setup-Anleitung: Kontakt-Import Automatisierung

Diese Anleitung beschreibt, wie Sie die benötigten API-Zugänge einrichten und als GitHub Secrets hinterlegen.

## Benötigte Secrets

Alle Secrets werden unter **Repository → Settings → Secrets and variables → Actions** angelegt.

---

### 1. Google Gmail API (OAuth2)

Sie benötigen: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`

#### Schritt 1: Google Cloud Projekt erstellen
1. Gehen Sie zu [Google Cloud Console](https://console.cloud.google.com/)
2. Erstellen Sie ein neues Projekt (oder verwenden Sie ein bestehendes)
3. Aktivieren Sie die **Gmail API** unter "APIs & Services → Library"

#### Schritt 2: OAuth2 Credentials erstellen
1. Gehen Sie zu "APIs & Services → Credentials"
2. Klicken Sie auf "+ Create Credentials → OAuth client ID"
3. Wählen Sie "Desktop app" als Application type
4. Notieren Sie sich **Client ID** und **Client Secret**

#### Schritt 3: Refresh Token generieren
1. Installieren Sie lokal: `pip install google-auth-oauthlib`
2. Führen Sie folgendes Python-Skript aus:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": "IHR_CLIENT_ID",
            "client_secret": "IHR_CLIENT_SECRET",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    },
    scopes=["https://www.googleapis.com/auth/gmail.readonly"],
)
creds = flow.run_local_server(port=0)
print("Refresh Token:", creds.refresh_token)
```

3. Melden Sie sich mit dem Gmail-Konto an, das durchsucht werden soll
4. Kopieren Sie den **Refresh Token**

#### GitHub Secrets anlegen
- `GOOGLE_CLIENT_ID` → Client ID aus Schritt 2
- `GOOGLE_CLIENT_SECRET` → Client Secret aus Schritt 2
- `GOOGLE_REFRESH_TOKEN` → Refresh Token aus Schritt 3

---

### 1b. Google Drive API (OAuth2) – für den Comparables-Report

Sie benötigen zusätzlich: `GOOGLE_REFRESH_TOKEN_DRIVE`

⚠️ Das Token aus Schritt 1 reicht **nicht**: es ist auf `gmail.readonly` ausgestellt, der
Comparables-Report liest aber Google Drive. Ein Token mit zu kleinem Scope scheitert mit
`insufficient authentication scopes`.

1. Aktivieren Sie in der Google Cloud Console zusätzlich die **Google Drive API**
2. Führen Sie das Skript aus Schritt 3 erneut aus – mit diesem Scope:

```python
scopes=["https://www.googleapis.com/auth/drive.readonly"],
```

3. Melden Sie sich mit dem Konto an, das Zugriff auf die Leasing-Ordner hat
4. Legen Sie den Refresh Token als GitHub Secret `GOOGLE_REFRESH_TOKEN_DRIVE` an

`GOOGLE_CLIENT_ID` und `GOOGLE_CLIENT_SECRET` aus Schritt 1 werden mitbenutzt.
Details: `comparables_handler/README.md`.

---

### 2. Anthropic API Key

Secret: `ANTHROPIC_API_KEY`

1. Gehen Sie zu [console.anthropic.com](https://console.anthropic.com/)
2. Erstellen Sie unter "API Keys" einen neuen Key
3. Legen Sie ihn als GitHub Secret `ANTHROPIC_API_KEY` an

---

### 3. Apollo.io API Key

Secret: `APOLLO_API_KEY`

1. Melden Sie sich bei [app.apollo.io](https://app.apollo.io/) an
2. Gehen Sie zu **Settings → Integrations → API**
3. Kopieren Sie den API Key
4. Legen Sie ihn als GitHub Secret `APOLLO_API_KEY` an

---

### 4. Propstack API Key

Secret: `PROPSTACK_API_KEY`

1. Der API Key ist bereits bekannt aus dem bestehenden Setup
2. Legen Sie ihn als GitHub Secret `PROPSTACK_API_KEY` an

---

### 5. Slack Bot Token

Secret: `SLACK_BOT_TOKEN`

1. Gehen Sie zu [api.slack.com/apps](https://api.slack.com/apps)
2. Erstellen Sie eine neue App (oder verwenden Sie eine bestehende)
3. Unter "OAuth & Permissions" fügen Sie den Scope `chat:write` hinzu
4. Installieren Sie die App im Workspace
5. Kopieren Sie den **Bot User OAuth Token** (beginnt mit `xoxb-`)
6. Stellen Sie sicher, dass der Bot im Channel `#visitenkarten` eingeladen ist (`/invite @BotName`)
7. Legen Sie den Token als GitHub Secret `SLACK_BOT_TOKEN` an

---

## Workflow testen

### Manueller Test (Dry Run)
1. Gehen Sie zu **Actions → Daily Contact Import → Run workflow**
2. Wählen Sie `dry_run: true`
3. Klicken Sie auf "Run workflow"
4. Prüfen Sie die Logs – es sollten Emails gelesen und Kontakte erkannt werden, aber keine angelegt

### Manueller Test (Live)
1. Wie oben, aber mit `dry_run: false`
2. Prüfen Sie anschließend in Propstack, ob die Kontakte korrekt angelegt wurden
3. Prüfen Sie den Slack-Channel `#visitenkarten` auf die Zusammenfassung

### Automatischer Lauf
Der Workflow läuft automatisch **Montag bis Freitag um 8:00 Uhr CET** (6:00 UTC).
