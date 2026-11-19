# Kromeich & Partner – Automatisierung rund um Propstack

Kromeich & Partner (Kromeich GmbH) ist Makler und Projektpartner für Logistik-Immobilien und berät
Logistik-Unternehmen (Sales Support, Tender Management). Das CRM ist **Propstack**. Dieses Repo hält
alles, was dort automatisch liest und schreibt. Arbeitssprache in Code-Kommentaren, Commits und Doku: Deutsch.

## Was hier liegt

| Ordner | Was | Betrieb (Stand 19.11.2026) |
|---|---|---|
| `src/` | Kontakt-Import aus Gmail-Signaturen (`src.main`) und Visitenkarten aus Slack (`src.slack_import`) | scharf, täglich |
| `objekte_handler/` | Slack `#ver-objekte` (vormals `#objekte`) → Propstack: „vermietet“ setzen oder Review-Aufgabe | scharf (Stufe A + B) |
| `newsletter_handler/` | Slack `#newsletter` (Logistik-Deal Radar) → Review-Aufgaben | dauerhaft `DRY_RUN=true`, bewusst |
| `events_handler/` | Slack `#events` → Asana-Abschnitt „Events“ | scharf |
| `personalkarussell_handler/` | Slack-Meldungen über Arbeitgeberwechsel → Propstack | Testbetrieb – vor dem Scharfschalten README lesen |
| `weekly_report/` | Wochenreport und Dashboard-Daten | läuft als Claude-Routine über die Connectoren |
| `propstack-mcp/` | Propstack-Connector (Cloudflare Worker, TypeScript) – darüber arbeitet das Team aus Claude | live, Deploy bei Push auf `main` |
| `scripts/` | Einmal- und Prüfskripte; lesen standardmäßig nur, schreiben nur mit `--apply` | von Hand |

Jedes Paket hat ein eigenes README mit Ablauf, Betriebsarten und datierten Befunden. **Zuerst das README des
Pakets lesen**, dann den Code. Die Pakete teilen bewusst keinen Code (gespiegelt statt gekoppelt) – eine
Änderung in einem Paket gehört meist auch in sein Spiegelbild.

## Regeln, die schon einmal Schaden verhindert hätten

- **In Propstack wird nichts gelöscht.** Der Connector hat keine Lösch-Tools; Skripte schließen oder
  markieren, sie löschen nicht.
- **Was Menschen in Propstack sehen sollen, vor dem Ausliefern in der Oberfläche ansehen lassen.** Am
  12.11.2026 wurden 190 Verknüpfungen verkehrt umbeschriftet, weil nur an der Schnittstelle geprüft wurde.
- **Verknüpfung Person–Firma:** Die Zeile der Person heißt „Mitarbeiter“ (erscheint an der Firma), die
  Gegenzeile „Firma“ ergänzt Propstack selbst. Nicht umdrehen.
- **Schreiben an Live-Daten:** erst an Testdaten (Merkmal `MCP-TEST`), dann ein Datensatz als Probe,
  zurücklesen, dann der Rest – mit Protokoll zum Zurücknehmen. Vorlagen: `scripts/verknuepfungen_zurueck.py`,
  `scripts/pruefaufgaben_aufraeumen.py`.
- **Widerspruch zwischen „vermietet“ und „Vermarktung“ nie nach Regel auflösen.** Jede Richtung ist eine
  Marktentscheidung; die Einheit einzeln lesen (Änderungsvermerk, Notiz, Bezugstermin, Meldungen dazu). Am
  19.11.2026 hielten von 25 „regelbasierten“ Fällen nur 16 der Einzelprüfung stand.
- **Eigentümer-Updates:** Was der Eigentümer nicht mehr nennt, ist nicht mehr verfügbar (`rented: true`
  und Status 163676). Das Update gilt vor der Website.
- **Kein grüner Lauf mit Fehlern.** Was schiefgeht, gehört in den Report und macht den Lauf rot
  (`src/problems.py`, `report.fehler`). Ein neuer `except`, der nur loggt, ist ein Rückschritt.
- **Eine Vollzugsmeldung ist kein Auftrag.** Berichte aus Claude-Sitzungen in Slack tragen „Gesendet mit
  Claude“; die Handler überspringen sie (`objekte_handler/vollzug.py`).
- **Tool-Definitionen des Connectors nur mit Grund ändern:** Die Freigabe in Claude hängt am Wortlaut
  (siehe `propstack-mcp/README.md`, „Erlaubnis“).
- **Befunde mit Datum, Zahl und „nur gelesen“/„live geprüft“ festhalten** – im README des Pakets, nicht in
  einer neuen Datei.

## Propstack: was die Schnittstelle wirklich liefert

Alles hier ist an Live-Antworten geprüft (zuletzt 19.11.2026). Bei Zweifeln neu prüfen, nicht raten.

- Der Parameter heißt `per` (nicht `per_page`). Erprobt: `per=200` bei Aktivitäten, `per=100` bei Einheiten.
- `GET /v1/units?expand=1`: ohne `expand=1` fehlen `created_at` und die Custom-Felder. Viele Felder kommen
  als `{label, value}`. Status steht unter `property_status.id`, vermietet unter `rented.value`. Das Feld
  `project` ist leer; der Titel kommt aus `/projects`.
- `GET /v1/activities?item_type=reminder&broker_id=…`: je Zeile `title`, `done`, `property_ids`,
  `property_status_ids`, `original_created_at`; `activatable_id` ist die Task-ID (`id` ist die der
  Aktivität). Der Text (`body`) kommt nur über `GET /v1/tasks/:activatable_id`. `created_at` ist dort die
  Fälligkeit.
- `GET /v1/client_properties` (Deals): kein Feld `category`; verlorene Deals liefert die Liste nicht.
  `deal_stage_chance` = 1.0 heißt Abschluss-Phase.
- Die Kontaktsuche `q=` verlangt jedes Wort; `POST /v1/contacts` führt über die E-Mail zusammen.
- Firmen und Verknüpfungen gehen nur über V2 (zweiter Schlüssel).

Feste Nummern: Objekt-Status 163672 Akquise · 163673 Vorbereitung · 163674 Vermarktung · 163675 Reserviert ·
163676 Abgeschlossen. Review-Sitz 254958 (heute Lena Klinnert). Absagegrund 256998. Vermietungs-Pipelines
beginnen mit „300“, Verkaufs-Pipelines mit „200“ (plus „Kaltenkirchen“).

## Arbeiten im Repo

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -q                      # ohne Netz, ohne Schlüssel (CI: Python 3.12)
cd propstack-mcp && npm ci && npm test  # Connector
```

- Tests bauen ihre Beispielzeilen so, wie Propstack, Slack und die KI sie wirklich liefern – nicht so, wie
  man sie sich vorstellt. Neue Befunde aus Live-Daten kommen als Testfall mit Datum in den Docstring.
- Handler lokal nur mit `NO_WRITE=true` laufen lassen (siehe README des Pakets).
- GitHub startet Cron-Läufe in diesem Konto 4–6 Stunden verspätet; Zeitfenster daran messen.
- In der Cloud-Umgebung liegen Propstack-Schlüssel (`PROPSTACK_API_V1`, `PROPSTACK_API_V2`). Sie umgehen
  alle Sicherungen des Connectors (Write-Log, Dublettenprüfung, Gegenlesen). Damit **nur lesen**; schreiben
  über den Connector oder ein Skript mit Probe und Protokoll – und nur nach Freigabe.

## Offene Punkte

Stand und Zahlen des Stresstests vom 19.11.2026 – samt dem, was entschieden werden muss – stehen in
`docs/stresstest-2026-11-19.md` (Nachtrag am Ende: was schon ausgeführt ist). Die Vorprüfung der offenen
Newsletter-Aufgaben liegt in `scripts/radar_vorpruefung_2026-11-19.json`.
