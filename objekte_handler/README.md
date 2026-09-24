# #objekte-Handler (Slack → Propstack)

Verarbeitet Status-Meldungen aus dem Slack-Kanal **#objekte** (`C07GH7AN80J`) und zieht sie automatisch in Propstack nach – mit zwei Sicherheitsstufen. Läuft als täglicher GitHub-Actions-Cron (`.github/workflows/objekte-handler.yml`, 02:00 UTC), Entrypoint `python -m objekte_handler.main`.

Eigenständiges Paket – **kein Code-Sharing mit `src/`** (Visitenkarten-Pipeline).

## Ablauf

1. Nachrichten (inkl. Thread-Antworten) der letzten 26h aus #objekte lesen; Nachrichten mit eigenem ✅ des Bots werden übersprungen (Verarbeitungsmarker, macht das Polling idempotent).
2. Klassifikation per Claude: `status_anweisung` / `fehlt_in_ps` / `flaechenupdate` / `ignorieren` + Extraktion von Adresse, Objektname, Aktion, Größen-Hinweis.
3. Objekt-Matching gegen `GET /v1/units?q=` mit lokaler Nachfilterung (Straße + **exakte Hausnummer**; mehrere Einheiten am selben Objekt über Flächenangabe wie "die kleine Einheit").
4. Entscheidung:
   - **Stufe A** (eindeutig + reversibel, nur bei `DRY_RUN=false`): `rented=true` setzen (Objekt-Status bleibt unberührt), Doku-Notiz, offene Deals per Absage-Aktivität (Grund 256998 "Fläche nicht mehr verfügbar") schließen.
   - **Stufe B** (mehrdeutig oder konsequenzreich): Review-Aufgabe an den Objekt-Verantwortlichen (Fallback: Sammelpostfach 254958, heute Lena Klinnert), fällig +2 Werktage, mit Original-Text, Permalink und vorbereiteter Aktion.
5. Rückmeldung als Thread-Reply + ✅-Reaction; jede Entscheidung landet als JSONL-Zeile im Entscheidungslog (nur lokal, siehe unten).

## Betriebsmodi

| Modus | Propstack-Writes | ✅ + Thread-Reply | JSONL-Log | Zweck |
|---|---|---|---|---|
| `NO_WRITE=true` | keine | keine | ja | Testen mit echten Slack-Daten, beliebig wiederholbar |
| `DRY_RUN=true` | nur Review-Tasks (Stufe B) | ja | ja | Testbetrieb – alles läuft als Stufe B |
| `DRY_RUN=false` | Stufe A + B | ja | ja | Normalbetrieb |

**Scharf geschaltet seit 09.07.2026:** Der Cron läuft mit `DRY_RUN=false` (Stufe A + B). Manuelle Läufe via `workflow_dispatch` defaulten aus Sicherheitsgründen weiterhin auf Dry-Run; lokal ist `DRY_RUN=true` der Default.

## Umgebungsvariablen

| Variable | Pflicht | Default | Bedeutung |
|---|---|---|---|
| `SLACK_BOT_TOKEN` | ja | – | Bot-Token (siehe Scopes unten) |
| `ANTHROPIC_API_KEY` | ja | – | Claude-Klassifikation |
| `PROPSTACK_API_KEY` | ja | – | Propstack-v1-Key (units, deals, tasks) – dasselbe Secret wie die Kontakt-Pipelines |
| `PROPSTACK_KEY_OBJEKTE` | nein | – | Optionaler Override: separater Key für units/deals |
| `PROPSTACK_KEY_TASKS` | nein | – | Optionaler Override: separater Key für Aktivitäten/Tasks |
| `DRY_RUN` | nein | `true` | Alles als Stufe B (Cron setzt explizit `false`) |
| `NO_WRITE` | nein | `false` | Reiner Lese-/Loglauf, überstimmt alles |
| `SCAN_HOURS` | nein | `26` | Scan-Fenster (24h Tageslauf + 2h Überlappung) |
| `SCAN_LATEST_HOURS` | nein | `0` | Obere Fenstergrenze (0 = bis jetzt), für Backfill |
| `THREAD_LOOKBACK_HOURS` | nein | `96` | Wie weit zurück Threads nach neuen Replies durchsucht werden |
| `DECISION_LOG_PATH` | nein | `objekte_decisions.jsonl` | Pfad des Entscheidungslogs |

## Secrets-Setup

Der Handler nutzt das bestehende GitHub Secret `PROPSTACK_API_KEY` (wie die Kontakt-Pipelines).

⚠️ **Hinweis Key-Rotation:** Ältere Propstack-Keys standen im Klartext in alten Skill-Dateien (`propstack-pipeline-report`, `propstack-expose-workflow`). Falls diese Keys noch gültig sind, in Propstack unter *Verwaltung → API-Schlüssel* rotieren und das Secret `PROPSTACK_API_KEY` aktualisieren. Wer später getrennte Keys möchte, kann sie als `PROPSTACK_KEY_OBJEKTE`/`PROPSTACK_KEY_TASKS` hinterlegen – sie überstimmen dann `PROPSTACK_API_KEY`. Keys niemals im Repo, in Logs oder in Skill-Dateien führen.

**Slack:** Der bestehende Bot wird mitgenutzt. Benötigte Scopes: `channels:history`, `channels:read`, `chat:write`, `reactions:read`, `reactions:write`. Der Bot muss Mitglied in #objekte sein (`/invite @Bot`).

## Lokale Ausführung

```bash
pip install -r requirements.txt
NO_WRITE=true DRY_RUN=true SCAN_HOURS=168 python -m objekte_handler.main
```

Tests (ohne Netz/Credentials):

```bash
pip install -r requirements-dev.txt
pytest tests/objekte_handler/ -v
```

## Auswertung des Entscheidungslogs

Das Entscheidungslog entsteht nur beim lokalen Lauf (`DECISION_LOG_PATH`); Cron-Läufe
laden es nicht hoch. Zum Auswerten den Handler lokal gegen das gewünschte Zeitfenster
laufen lassen (Beispiel oben, `SCAN_HOURS` passend gesetzt), dann z.B.:

```bash
# Verteilung der Nachrichtentypen
jq -r '.classification.typ // "fehler"' objekte_decisions.jsonl | sort | uniq -c

# Alle Stufe-B-Entscheidungen mit Grund
jq -r 'select(.decision.tier == "B") | "\(.message_ts)  \(.decision.grund)"' objekte_decisions.jsonl

# Fehler
jq -r 'select(.fehler) | "\(.message_ts)  \(.fehler)"' objekte_decisions.jsonl
```

## Bekannte Einschränkungen

- **Editierte Nachrichten** werden nach Verarbeitung (✅) nicht erneut verarbeitet – bei Korrekturen bitte eine neue Nachricht schreiben.
- **Thread-Antworten** auf Threads, deren Ursprungsnachricht älter als `THREAD_LOOKBACK_HOURS` (96h) ist, werden nicht erkannt.
- `ignorieren`-Nachrichten bekommen bewusst **kein** ✅ (kein Bot-Lärm an LinkedIn-Links); sie werden in der Fenster-Überlappung des Folgelaufs ggf. einmal erneut klassifiziert.
- Crash zwischen Propstack-Write und ✅ kann beim nächsten Lauf Task-Duplikate erzeugen (`rented=true` ist idempotent) – bewusster Trade-off, damit kein ✅ ohne ausgeführte Aktion entsteht.

## Explizit außerhalb des Scopes

- Exposé-PDF-Verarbeitung (Workflow abgeschaltet)
- Objekt-Neuanlage aus Nachrichten (nur Review-Aufgabe an den Fallback-Sitz)
- Newsletter-Parsing der Flächenupdates (nur Review-Aufgabe)
- Änderungen an Objekt-Status, Suchprofilen oder Kontakten
