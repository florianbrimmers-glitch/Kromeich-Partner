# #objekte-Handler (Slack → Propstack)

Verarbeitet Status-Meldungen aus dem Slack-Kanal **#objekte** (`C07GH7AN80J`) und zieht sie automatisch in Propstack nach – mit zwei Sicherheitsstufen. Läuft als täglicher GitHub-Actions-Cron (`.github/workflows/objekte-handler.yml`, 02:00 UTC), Entrypoint `python -m objekte_handler.main`.

Eigenständiges Paket – **kein Code-Sharing mit `src/`** (Visitenkarten-Pipeline).

## Ablauf

1. Nachrichten (inkl. Thread-Antworten) der letzten 26h aus #objekte lesen; Nachrichten mit eigenem ✅ des Bots werden übersprungen (Verarbeitungsmarker, macht das Polling idempotent).
2. Klassifikation per Claude: `status_anweisung` / `fehlt_in_ps` / `flaechenupdate` / `ignorieren` + Extraktion von Adresse, Objektname, Aktion, Größen-Hinweis.
3. Objekt-Matching gegen `GET /v1/units?q=` mit lokaler Nachfilterung (Straße + **exakte Hausnummer**; mehrere Einheiten am selben Objekt über Flächenangabe wie "die kleine Einheit").
4. Entscheidung:
   - **Stufe A** (eindeutig + reversibel, nur bei `DRY_RUN=false`): `rented=true` setzen (Objekt-Status bleibt unberührt), Doku-Notiz, offene Deals per Absage-Aktivität (Grund 256998 "Fläche nicht mehr verfügbar") schließen.
   - **Stufe B** (mehrdeutig oder konsequenzreich): Review-Aufgabe an den Objekt-Verantwortlichen (Fallback Oguzhan, 254958), fällig +2 Werktage, mit Original-Text, Permalink und vorbereiteter Aktion.
5. Rückmeldung als Thread-Reply + ✅-Reaction; jede Entscheidung landet als JSONL-Zeile im Entscheidungslog (Actions-Artefakt, 30 Tage).

## Betriebsmodi

| Modus | Propstack-Writes | ✅ + Thread-Reply | JSONL-Log | Zweck |
|---|---|---|---|---|
| `NO_WRITE=true` | keine | keine | ja | Testen mit echten Slack-Daten, beliebig wiederholbar |
| `DRY_RUN=true` (**Default**) | nur Review-Tasks (Stufe B) | ja | ja | Woche 1 – alles läuft als Stufe B |
| `DRY_RUN=false` | Stufe A + B | ja | ja | Normalbetrieb |

**Woche-1-Regel:** Der Cron läuft mit `DRY_RUN=true`. Scharfschalten erst nach dem Team-Review am **22.07.2026** ("Asana vs. Propstack"-Termin) – dazu im Workflow das Default von `DRY_RUN` auf `false` ändern.

## Umgebungsvariablen

| Variable | Pflicht | Default | Bedeutung |
|---|---|---|---|
| `SLACK_BOT_TOKEN` | ja | – | Bot-Token (siehe Scopes unten) |
| `ANTHROPIC_API_KEY` | ja | – | Claude-Klassifikation |
| `PROPSTACK_KEY_OBJEKTE` | ja | – | Propstack-Key mit Objekte-Rechten (units, deals) |
| `PROPSTACK_KEY_TASKS` | ja | – | Propstack-Key für Aktivitäten/Tasks ("Claude"-Key) |
| `DRY_RUN` | nein | `true` | Woche-1-Regel: alles als Stufe B |
| `NO_WRITE` | nein | `false` | Reiner Lese-/Loglauf, überstimmt alles |
| `SCAN_HOURS` | nein | `26` | Scan-Fenster (24h Tageslauf + 2h Überlappung) |
| `SCAN_LATEST_HOURS` | nein | `0` | Obere Fenstergrenze (0 = bis jetzt), für Backfill |
| `THREAD_LOOKBACK_HOURS` | nein | `96` | Wie weit zurück Threads nach neuen Replies durchsucht werden |
| `DECISION_LOG_PATH` | nein | `objekte_decisions.jsonl` | Pfad des Entscheidungslogs |

## Secrets-Setup (einmalig)

⚠️ **Propstack-Keys rotieren:** Die bisherigen Keys standen im Klartext in alten Skill-Dateien (`propstack-pipeline-report`, `propstack-expose-workflow`). In Propstack unter *Verwaltung → API-Schlüssel* neue Keys erzeugen und als GitHub Secrets `PROPSTACK_KEY_OBJEKTE` und `PROPSTACK_KEY_TASKS` hinterlegen. Keys niemals im Repo, in Logs oder in Skill-Dateien führen.

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

JSONL-Artefakte der Läufe herunterladen (Actions → Run → Artifacts), dann z.B.:

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
- Objekt-Neuanlage aus Nachrichten (nur Aufgabe an Oguzhan)
- Newsletter-Parsing der Flächenupdates (nur Review-Aufgabe)
- Änderungen an Objekt-Status, Suchprofilen oder Kontakten
