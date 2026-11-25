# #objekte-Handler (Slack → Propstack)

Verarbeitet Status-Meldungen aus dem Slack-Kanal **#objekte** (`C07GH7AN80J`) und zieht sie automatisch in Propstack nach – mit zwei Sicherheitsstufen. Läuft als täglicher GitHub-Actions-Cron (`.github/workflows/objekte-handler.yml`, 02:00 UTC), Entrypoint `python -m objekte_handler.main`.

Eigenständiges Paket – **kein Code-Sharing mit `src/`** (Visitenkarten-Pipeline).

## Ablauf

1. Nachrichten (inkl. Thread-Antworten) der letzten 50 h aus #objekte lesen (Cron; lokal Standard 26 h); Nachrichten mit eigenem ✅ des Bots werden übersprungen (Verarbeitungsmarker, macht das Polling idempotent).
2. **Vollzugsmeldungen aussortieren** (Änderung vom 19.11.2026, vor jeder KI): Berichte über Erledigtes sind kein Auftrag – keine Klassifikation, keine Aufgabe, kein ✅. Erkannt werden „neues Objekt angelegt …“ am Anfang der Nachricht und die Signatur „Gesendet mit Claude“ (Berichte aus Claude-Sitzungen). Regel und Belege: `vollzug.py`.
3. Klassifikation per Claude: `status_anweisung` / `fehlt_in_ps` / `flaechenupdate` / `ignorieren` + Extraktion von Adresse, Objektname, Aktion, Größen-Hinweis.
4. Objekt-Matching gegen `GET /v1/units?q=` mit lokaler Nachfilterung (Straße + **exakte Hausnummer**; mehrere Einheiten am selben Objekt über Flächenangabe wie "die kleine Einheit").
5. Entscheidung:
   - **Stufe A** (eindeutig + reversibel, nur bei `DRY_RUN=false`): `rented=true` setzen (Objekt-Status bleibt unberührt), Doku-Notiz, offene Deals per Absage-Aktivität (Grund 256998 "Fläche nicht mehr verfügbar") schließen.
     - Abgesagt werden nur Deals der Vermietung (Pipelines „300 …“ und Deals ohne Pipeline), nie ein Deal in der Abschluss-Phase (100 %) und nie Deals der Verkaufs-Pipelines („200 …“, „Kaltenkirchen“). Was nicht angetastet wurde, steht in der Slack-Antwort.
     - Mehrere Einheiten an einer Adresse gelten nur dann als „ganzes Objekt“, wenn weder die Nachricht noch ihr Thread eine einzelne Einheit nennt („Halle 2“, „Hallen 1 und 2“, „die hintere Halle“, „Teilfläche“) – sonst Stufe B.
     - Eine Quadratmeterzahl muss auf ±15 % zu genau einer Einheit passen. Ist bei „die kleine/große Einheit“ die kleinste/größte schon vermietet, entscheidet ein Mensch – der Handler weicht nie auf die nächste freie aus.
     - Ist die Einheit gesetzt und scheitert ein späterer Schritt (Doku-Notiz, eine Absage), läuft der Rest trotzdem; die Antwort im Thread lautet dann „Nur teilweise erledigt …“ und der Lauf endet rot.
   - **Stufe B** (mehrdeutig oder konsequenzreich): Review-Aufgabe an den Objekt-Verantwortlichen (Fallback: Sammelpostfach 254958, heute Lena Klinnert), fällig +2 Werktage, mit Original-Text, Permalink und vorbereiteter Aktion.
6. Rückmeldung als Thread-Reply + ✅-Reaction; jede Entscheidung landet als JSONL-Zeile im Entscheidungslog (nur lokal, siehe unten).

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

## Befund vom 19.11.2026: Was der Handler wirklich tut

Nur gelesen, über alle Nutzer:

- **Stufe A lief seit Juli zweimal** (08/2026 und 09/2026). Praktisch erzeugt der Handler Review-Aufgaben – 82 davon sind offen.
- **47 dieser 82 (57 %) antworten auf Vollzugsmeldungen.** 20× „neues Objekt angelegt …“ wurde zu „Objekt fehlt in Propstack: bitte anlegen“ (zusammen mit 5 Berichten 25 von 30 offenen Aufgaben dieser Art), 27× wurde ein Bericht aus einer Claude-Sitzung („… – Abgleich mit Propstack“, „Update: …“) zur Aufgabe „Flächenupdate abgleichen“ oder „Slack #objekte prüfen“. Die Automatisierung hat hier ihre eigenen Erfolgsmeldungen als Arbeit zurückgespielt. Abgestellt mit Schritt 2; der Bestand lässt sich mit `scripts/pruefaufgaben_aufraeumen.py` schließen (erst nach Freigabe).
- **Ein Lauf ist jetzt rot, wenn eine Nachricht nicht verarbeitet werden konnte** oder Slack nicht lesbar war. Der Cron liest 50 h zurück: Was gescheitert ist, holt der nächste Lauf von selbst nach; was verarbeitet ist, trägt das ✅ und wird übersprungen. Älteres per `workflow_dispatch` mit größerem `scan_from_hours`.
- Ein POST (Aufgabe, Notiz, Absage) wird nach einem Serverfehler oder Timeout nicht mehr wiederholt (sonst drohen doppelte Aufgaben und Absagen); nur 429 wird wiederholt. GET und PUT (`rented=true`) werden weiter wiederholt.

Offen (Entscheidung nötig, nicht geändert): Stufe A setzt nur `rented=true`. Der Connector schließt nach den Feldregeln vollständig – Status „Abgeschlossen“ (163676), „Status Logistik“ und „Aktiv“ auf Inaktiv –, damit die Einheit aus Exposéversand und Website fällt (`propstack-mcp/src/propstack/field-rules.ts`). Was der Handler schließt, bleibt dort aktiv. Am 19.11.2026 standen 7 Einheiten als vermietet **und** in „Vermarktung“.

## Befund vom 25.11.2026: Lauf mit 5 Review-Aufgaben, davon 3 unnötig

Nur gelesen (Propstack und Slack):

- **Remscheid – LIP Invest** (Exposé-PDF von Marek): „Objekt fehlt in Propstack“. Das Objekt steht seit dem 20.03.2026
  in Propstack (5159361, Am Weidenbroich 20-22); Marek schrieb eine Minute später „Hab ich schon ordentlich angelegt“.
  Der Handler prüft bei `fehlt_in_ps` nicht, ob es das Objekt schon gibt, und liest Folgenachrichten nicht als Antwort.
- **Hillwood Porta Westfalica und Kirchlengern** („neues Objekt angelegt …“ von Oguzhan): Die Vollzugsregel las
  „– nicht vermietet“ als Hinweis wie „ist aber schon vermietet“. Behoben: „nicht vermietet“ zählt nicht mehr.
- Die zwei „bitte anlegen“ von Marek (Frasers Unna, Marq Ense-Höingen) sind echte Aufträge; der Titel lautet nur
  „bitte anlegen“, weil der Link in der Nachricht davor steht.
- Nebenbefund: Die Anlage vom 24.11. hat bei Hillwood Dubletten erzeugt. Je Park standen Halle 2/3 (Kirchlengern
  002–004) schon seit 08/2026 bzw. 03/2025 im Bestand, ohne Projekt; am 24.11. kamen dieselben Hallen mit gleicher
  Fläche noch einmal im Projekt dazu – 7 Datensätze doppelt (Bünde 5766185/6571928, 5766186/6571938; Kirchlengern
  3158471/6572519, 3158472/6572520, 3158474/6572521; Porta Westfalica 5766203/6572506, 5766204/6572508).

Das ✅ heißt bei diesem Handler „verarbeitet“, nicht „erledigt“: Es steht auch an Nachrichten, zu denen nur eine
Review-Aufgabe angelegt wurde. Was passiert ist, steht in der Antwort im Thread.

## Bekannte Einschränkungen

- **Editierte Nachrichten** werden nach Verarbeitung (✅) nicht erneut verarbeitet – bei Korrekturen bitte eine neue Nachricht schreiben.
- **Thread-Antworten** auf Threads, deren Ursprungsnachricht älter als `THREAD_LOOKBACK_HOURS` (96h) ist, werden nicht erkannt.
- Ein echter Auftrag, der über Claude gepostet wird und die Signatur „Gesendet mit Claude“ trägt, gilt als Vollzugsmeldung und wird nicht verarbeitet. Wer den Handler ansprechen will, schreibt ohne Signatur.
- `ignorieren`-Nachrichten bekommen bewusst **kein** ✅ (kein Bot-Lärm an LinkedIn-Links); sie werden in der Fenster-Überlappung des Folgelaufs ggf. einmal erneut klassifiziert.
- Crash zwischen Propstack-Write und ✅ kann beim nächsten Lauf Task-Duplikate erzeugen (`rented=true` ist idempotent) – bewusster Trade-off, damit kein ✅ ohne ausgeführte Aktion entsteht.

## Explizit außerhalb des Scopes

- Exposé-PDF-Verarbeitung (Workflow abgeschaltet)
- Objekt-Neuanlage aus Nachrichten (nur Review-Aufgabe an den Fallback-Sitz)
- Newsletter-Parsing der Flächenupdates (nur Review-Aufgabe)
- Änderungen an Objekt-Status, Suchprofilen oder Kontakten
