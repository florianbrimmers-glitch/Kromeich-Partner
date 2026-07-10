# #events-Handler (Slack → Marketing-Event-Tabelle)

Wertet den Slack-Kanal **#events** (`C07N95AQRB2`) aus und trägt Veranstaltungen in die Google-Tabelle **„Messen & Events"** ein (Drive: *01. Allgemein / 02. Marketing / 04. Events*, ID `1ppUJOOduq4Bdjw4mpxokfLlUHFuRWmRfCqf9xCHIbKw`). Läuft als täglicher GitHub-Actions-Cron (`.github/workflows/events-handler.yml`, 03:30 UTC), Entrypoint `python -m events_handler.main`.

Eigenständiges Paket – kein Code-Sharing mit `src/` oder den anderen Handlern (bewusst gespiegelt).

## Ablauf

1. Nachrichten der letzten 27h aus #events lesen. Eigene ✅-markierte Nachrichten werden übersprungen (Verarbeitungsmarker, idempotent). Bot-/Slackbot-Posts werden **mitgelesen** (dort landen die Einladungen).
2. Pro Post: Datei-Anhänge laden (weitergeleitete Mails sind meist **text/html**), grob zu Text reduzieren, zusammen mit Dateititel + Nachrichtentext an Claude (`claude-opus-4-8`) geben.
3. Extraktion: alle konkreten Veranstaltungen (mit Termin) → `Datum, Event, Branche, Ort, Kosten, Anmeldelink`. Reine Werbung/Newsletter ohne Termin → `ist_event=false` (ignoriert).
4. Je erkanntem Event eine Zeile an die Tabelle anhängen (Spalten: `Datum · Event · Branche · Ort · Kosten (nur Ticket) · Funktion KP · Spannend für · Notiz/Link`). **„Funktion KP" und „Spannend für" bleiben leer** (füllt ein Mensch); „Notiz/Link" = Slack-Permalink (+ ggf. Anmeldelink).
5. ✅-Reaction + Thread-Antwort je Post. Jede Entscheidung landet als JSONL-Zeile im Entscheidungslog (Actions-Artefakt).

## Betriebsmodi

| Modus | Sheet-Writes | ✅ + Reply | JSONL-Log | Zweck |
|---|---|---|---|---|
| `NO_WRITE=true` | keine | keine | ja | Testen mit echten Slack-Daten, ohne Google-Credentials |
| `DRY_RUN=true` (**Default**) | keine (nur erkennen/loggen) | ja | ja | Testbetrieb – Zeilen werden vorbereitet, aber nicht geschrieben |
| `DRY_RUN=false` | Zeilen werden angehängt | ja | ja | Normalbetrieb |

## Umgebungsvariablen

| Variable | Pflicht | Default | Bedeutung |
|---|---|---|---|
| `SLACK_BOT_TOKEN` | ja | – | Bot-Token (Scopes: `channels:history`, `channels:read`, `chat:write`, `reactions:read`, `reactions:write`, **`files:read`**) |
| `ANTHROPIC_API_KEY` | ja | – | Claude-Extraktion (`claude-opus-4-8`) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | nur für Writes | – | Service-Account-JSON mit Sheets-Scope; Tabelle für dessen E-Mail freigeben (**empfohlen**) |
| `GOOGLE_SHEETS_REFRESH_TOKEN` | Alternative | – | OAuth-Refresh-Token mit Sheets-Scope (+ `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`) |
| `DRY_RUN` | nein | `true` | Erkennen/loggen ohne Sheet-Writes |
| `NO_WRITE` | nein | `false` | Reiner Lese-/Loglauf, überstimmt alles |
| `SCAN_HOURS` | nein | `27` | Scan-Fenster |
| `SCAN_LATEST_HOURS` | nein | `0` | Obere Fenstergrenze (0 = bis jetzt), für Backfill |
| `DECISION_LOG_PATH` | nein | `events_decisions.jsonl` | Pfad des Entscheidungslogs |

## Google-Sheets-Zugriff (nur für scharfen Betrieb nötig)

Für echte Tabellen-Writes (`DRY_RUN=false`) braucht der Handler Google-Credentials mit dem Scope `https://www.googleapis.com/auth/spreadsheets`:

- **Empfohlen – Service-Account:** in der Google Cloud einen Service-Account anlegen, JSON-Key als Secret `GOOGLE_SERVICE_ACCOUNT_JSON` hinterlegen, und die Tabelle „Messen & Events" für die Service-Account-E-Mail als Bearbeiter freigeben. Kein User-Token nötig.
- **Alternative – OAuth:** einen Refresh-Token mit Sheets-Scope erzeugen und als `GOOGLE_SHEETS_REFRESH_TOKEN` hinterlegen (nutzt die bestehenden `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`).

Der Lese-/Extraktionsteil (NO_WRITE) ist davon unabhängig und sofort testbar.

## Lokale Ausführung

```bash
pip install -r requirements.txt
NO_WRITE=true SCAN_HOURS=336 python -m events_handler.main
```

Tests (ohne Netz/Credentials):

```bash
pip install -r requirements-dev.txt
pytest tests/events_handler/ -v
```

## Bekannte Einschränkungen

- Zeilen werden **unten an die Tabelle angehängt** (nicht in die Monats-Abschnitte einsortiert) – bewusst simpel; Sortierung/Einordnung macht ein Mensch.
- Kein Abgleich gegen bereits in der Tabelle stehende Events; Doppelte werden über den ✅-Marker auf Slack-Ebene vermieden (jede Nachricht nur einmal verarbeitet).
- Sehr große HTML-Anhänge werden zu Text reduziert und auf ~16.000 Zeichen gekürzt.
