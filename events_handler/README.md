# #events-Handler (Slack → Asana-Eventliste)

Wertet den Slack-Kanal **#events** (`C07N95AQRB2`) aus und legt Veranstaltungen als Aufgaben im Asana-Projekt **„Marketing"**, Abschnitt **„Events"** an (Projekt `1211638618946856`, Abschnitt `1211803155426815`). Läuft als täglicher GitHub-Actions-Cron (`.github/workflows/events-handler.yml`, 03:30 UTC), Entrypoint `python -m events_handler.main`.

Eigenständiges Paket – kein Code-Sharing mit `src/` oder den anderen Handlern (bewusst gespiegelt).

> **Zielsystem:** Ursprünglich war das Ziel die Google-Tabelle „Messen & Events". Die Google-Anbindung (OAuth) war hakelig und wurde nie scharf geschaltet; mit Marlene abgestimmt liegt die Liste jetzt in Asana, wo der Abschnitt „Events" bereits gepflegt wird.

## Ablauf

1. Nachrichten der letzten 27h aus #events lesen. Eigene ✅-markierte Nachrichten werden übersprungen (Verarbeitungsmarker, idempotent). Bot-/Slackbot-Posts werden **mitgelesen** (dort landen die Einladungen).
2. Pro Post: Datei-Anhänge laden (weitergeleitete Mails sind meist **text/html**), grob zu Text reduzieren, zusammen mit Dateititel + Nachrichtentext an Claude (`claude-opus-4-8`) geben.
3. Extraktion: alle konkreten Veranstaltungen (mit Termin) → `Datum, Event, Branche, Ort, Kosten, Anmeldelink`. Reine Werbung/Newsletter ohne Termin → `ist_event=false` (ignoriert).
4. Je erkanntem Event eine Asana-Aufgabe im Abschnitt „Events":
   - **Name:** `<Datum> <Event-Name>` – folgt der bestehenden Konvention des Abschnitts (z.B. „24.-26.03 LogiMat", „06.-08.10 Expo Real").
   - **Beschreibung:** Branche, Ort, Kosten (nur Ticket), Anmelde-/Info-Link, Slack-Permalink als Quelle.
   - **„Funktion KP" und „Spannend für" werden NICHT gefüllt** – das sind Wertungen, die ein Mensch ergänzt (ein Hinweis dazu steht in der Beschreibung).
5. ✅-Reaction + Thread-Antwort je Post. Jede Entscheidung landet als JSONL-Zeile im Entscheidungslog (Actions-Artefakt).

## Betriebsmodi

| Modus | Asana-Writes | ✅ + Reply | JSONL-Log | Zweck |
|---|---|---|---|---|
| `NO_WRITE=true` | keine | keine | ja | Testen mit echten Slack-Daten, ohne Asana-Token |
| `DRY_RUN=true` (**Default**) | keine (nur erkennen/loggen) | **keine** | ja | Testbetrieb – Aufgaben werden vorbereitet, aber nicht angelegt |
| `DRY_RUN=false` | Aufgaben werden angelegt | ja | ja | Normalbetrieb |

**Wichtig:** Im `DRY_RUN` werden ✅ und Thread-Antwort bewusst **unterdrückt**. Sonst gälte der Post als erledigt, obwohl noch keine Asana-Aufgabe existiert – im scharfen Betrieb würde er übersprungen und das Event nie in der Liste landen. Nebeneffekt: derselbe Post wird in jedem Dry-Run-Lauf erneut ausgewertet (kostet Claude-Tokens, schreibt aber nichts).

## Umgebungsvariablen

| Variable | Pflicht | Default | Bedeutung |
|---|---|---|---|
| `SLACK_BOT_TOKEN` | ja | – | Bot-Token (Scopes: `channels:history`, `channels:read`, `chat:write`, `reactions:read`, `reactions:write`, **`files:read`**) |
| `ANTHROPIC_API_KEY` | ja | – | Claude-Extraktion (`claude-opus-4-8`) |
| `ASANA_ACCESS_TOKEN` | nur für Writes | – | Asana Personal Access Token (Repo-Secret) |
| `ASANA_PROJECT_ID` | nein | `1211638618946856` | Ziel-Projekt („Marketing") |
| `ASANA_SECTION_ID` | nein | `1211803155426815` | Ziel-Abschnitt („Events"); zum Testen auf einen Test-Abschnitt umbiegbar |
| `DRY_RUN` | nein | `true` | Erkennen/loggen ohne Asana-Writes |
| `NO_WRITE` | nein | `false` | Reiner Lese-/Loglauf, überstimmt alles |
| `SCAN_HOURS` | nein | `27` | Scan-Fenster |
| `SCAN_LATEST_HOURS` | nein | `0` | Obere Fenstergrenze (0 = bis jetzt), für Backfill |
| `DECISION_LOG_PATH` | nein | `events_decisions.jsonl` | Pfad des Entscheidungslogs |

## Asana-Zugriff (nur für scharfen Betrieb nötig)

Für echte Writes (`DRY_RUN=false`) braucht der Handler einen **Asana Personal Access Token**:

1. In Asana unter *Meine Einstellungen → Apps → Entwicklerkonsole → Personal Access Tokens* einen Token erzeugen.
2. Im GitHub-Repo als Secret `ASANA_ACCESS_TOKEN` hinterlegen (*Settings → Secrets and variables → Actions*).
3. Der Token-Besitzer muss Zugriff auf das Projekt „Marketing" haben.

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

- Aufgaben werden **an den Abschnitt „Events" angehängt** (nicht chronologisch einsortiert) – bewusst simpel; Sortierung macht ein Mensch.
- Kein Abgleich gegen bereits in Asana stehende Events; Doppelte werden über den ✅-Marker auf Slack-Ebene vermieden (jede Nachricht nur einmal verarbeitet).
- `due_on` wird nicht gesetzt: die Event-Termine im Abschnitt stehen im Aufgaben-**Namen** (oft Zeiträume wie „24.-26.03", die kein einzelnes Datum sind).
- Sehr große HTML-Anhänge werden zu Text reduziert und auf ~16.000 Zeichen gekürzt.
