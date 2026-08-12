# Comparables-Report (Google Drive → Slack + K&P-PDF)

Liest **alle Mietangebote aus dem Google Drive**, extrahiert die Konditionen und liefert **Vergleichsmieten pro Region** – Median, Spanne und n. Läuft als monatlicher GitHub-Actions-Cron (`.github/workflows/comparables-report.yml`, 1. des Monats 05:00 UTC), Entrypoint `python -m comparables_handler.main`.

Eigenständiges Paket – **kein Code-Sharing mit `src/`** oder den anderen Handlern.

Umsetzung der Asana-Aufgabe [Comparables-Report aus Mietangeboten](https://app.asana.com/1/1207989209959731/task/1213887655130097).

## Ablauf

1. **Discovery** – zwei Wege gleichzeitig: Titel-Suche (`Mietangebot` im Dateinamen) plus Rekursion über die Ordner `03. Leasing` und `Mietangebote` (IDs in `config.SEED_FOLDER_IDS`). Verknüpfungen werden aufgelöst, Shared Drives eingeschlossen.
2. **Datei-Dedup** – dasselbe Angebot liegt im Drive typischerweise 3–5× in verschiedenen Ordnern. Zusammengefasst wird über die Inhalts-Prüfsumme (`md5Checksum`), ersatzweise Größe + MIME-Typ. Gemessen am 12.08.2026: **~70 Treffer → ~22 verschiedene Dokumente.** Ohne diesen Schritt ginge jede Kopie einzeln an Claude.
3. **Regel-Ausschluss vor dem LLM-Call** – eigene Vorlagen (`Vorlage`, `Muster`, …), die Kromeich-Büromiete (`Mietangebot-Kromeich GmbH-*`) und Anlagen-/Beiblatt-Dateien fliegen am Dateinamen raus und kosten keinen Token.
4. **Extraktion** – PDFs gehen als Dokument-Block **direkt an Claude** (liest auch gescannte Angebote und Tabellen-Layouts, an denen eine Textextraktion scheitert). DOCX/PPTX/XLSX werden zu Text aufbereitet, Google Docs/Slides/Sheets über die Drive-API exportiert. Ergebnisse landen im Extraktions-Cache.
5. **Versions-Dedup** – liegen mehrere Fassungen zu Objekt + Anbieter vor, zählt nur die jüngste (Angebotsdatum, ersatzweise Drive-`modifiedTime`). Realer Fall: das VIR21-Angebot existiert in drei Fassungen (16.03., 20.03., 30.04.2026).
6. **Normalisierung** – **eine Zeile pro Laufzeit-Option**. Absolute Mieten werden über die Fläche in €/m²/Monat umgerechnet, Jahresmieten auf den Monat. Effektivmiete = Kaltmiete geglättet um die mietfreie Zeit. Unplausible Werte werden **mit Grund** ausgeschlossen, nicht gelöscht.
7. **Aggregation** – Median, Spanne und n je Leitregion (2-stellige PLZ, ab n=3) und je Postleitzone (1-stellig, immer), plus Gesamtzeile.
8. **Ausgabe** – Slack-Post in den Zielkanal, CSV-Datensatz und optional das K&P-PDF; jede Dokument-Entscheidung als JSONL-Zeile.

## Betriebsmodi

| Modus | Slack-Post | CSV + JSONL + PDF | Zweck |
|---|---|---|---|
| `NO_WRITE=true` | nein | ja | Testen mit echten Drive-Daten, beliebig wiederholbar |
| `DRY_RUN=true` | nein (nur ins Log) | ja | Report inhaltlich prüfen, bevor das Team ihn sieht |
| `DRY_RUN=false` | ja | ja | Normalbetrieb |

### Scharfschalten

Der Cron läuft **bewusst noch im Dry-Run**. Zwei Dinge sind vor dem Scharfschalten zu klären:

1. **Zielkanal.** Es gibt (Stand 12.08.2026) keinen Leasing-/Comparables-Kanal im Workspace; Default ist deshalb `#objekte` (`C07GH7AN80J`). Ein eigener Kanal ist sinnvoller – dann `COMPARABLES_CHANNEL` im Workflow setzen.
2. **Inhaltliche Abnahme** des ersten Reports (Actions → *Comparables Report* → Run workflow, `dry_run: true`), insbesondere der extrahierten Kaltmieten gegen die Quell-PDFs.

Danach im Workflow `DRY_RUN: ${{ github.event.inputs.dry_run || 'false' }}` setzen.

## Umgebungsvariablen

| Variable | Pflicht | Default | Bedeutung |
|---|---|---|---|
| `GOOGLE_CLIENT_ID` | ja | – | OAuth-Client (wie Kontakt-Pipeline) |
| `GOOGLE_CLIENT_SECRET` | ja | – | OAuth-Client |
| `GOOGLE_REFRESH_TOKEN_DRIVE` | ja | – | Refresh-Token **mit `drive.readonly`** (siehe unten) |
| `ANTHROPIC_API_KEY` | ja | – | Claude-Extraktion |
| `SLACK_BOT_TOKEN` | nur scharf | – | Bot-Token für den Report-Post |
| `COMPARABLES_CHANNEL` | nein | `C07GH7AN80J` (#objekte) | Zielkanal |
| `DRY_RUN` | nein | `true` | Report bauen, aber nicht posten |
| `NO_WRITE` | nein | `false` | Reiner Lese-/Loglauf |
| `MAKE_PDF` | nein | `false` | K&P-PDF erzeugen |
| `PDF_PATH` | nein | `comparables_report.pdf` | Ausgabepfad des PDF |
| `KP_DESIGN_DIR` | nein | `~/.claude/skills/synced/kp-design` | Quelle der K&P-Schriften |
| `MAX_DOCUMENTS` | nein | `0` | Kostenbremse (0 = alle); gekappte Dokumente werden als Fehler gemeldet |
| `DATASET_PATH` | nein | `comparables_dataset.csv` | CSV-Datensatz |
| `EXTRACTION_CACHE_PATH` | nein | `comparables_cache.jsonl` | Extraktions-Cache (leer = aus) |
| `DECISION_LOG_PATH` | nein | `comparables_decisions.jsonl` | Entscheidungslog |

## Secrets-Setup: Drive-Zugang

⚠️ **Die bestehenden `GOOGLE_REFRESH_TOKEN*`-Secrets reichen nicht.** Sie sind auf `gmail.readonly` ausgestellt; Drive-Aufrufe damit scheitern mit `insufficient authentication scopes`. Es braucht ein eigenes Token:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_config(
    {"installed": {
        "client_id": "...", "client_secret": "...",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }},
    scopes=["https://www.googleapis.com/auth/drive.readonly"],
)
print("Refresh Token:", flow.run_local_server(port=0).refresh_token)
```

Mit dem Konto anmelden, das Zugriff auf die Leasing-Ordner hat, und das Ergebnis als Secret `GOOGLE_REFRESH_TOKEN_DRIVE` hinterlegen. In der Google Cloud Console muss die **Drive API** aktiviert sein.

**Slack:** bestehender Bot, Scope `chat:write`; der Bot muss im Zielkanal Mitglied sein (`/invite @Bot`).

## Lokale Ausführung

```bash
pip install -r requirements.txt
NO_WRITE=true MAKE_PDF=true python -m comparables_handler.main
```

Tests (ohne Netz/Credentials):

```bash
pip install -r requirements-dev.txt
pytest tests/comparables_handler/ -v
```

## Auswertung

Der CSV-Datensatz (`comparables_dataset.csv`, Semikolon-getrennt, Excel-fähig) enthält **auch die ausgeschlossenen Zeilen mit Grund** – so ist nachvollziehbar, warum ein Angebot nicht im Median steht.

```bash
# Warum wurden Zeilen ausgeschlossen?
jq -r 'select(.uebersprungen) | "\(.datei)  ->  \(.uebersprungen)"' comparables_decisions.jsonl

# Extrahierte Kaltmieten je Objekt gegen die Quelle prüfen
jq -r 'select(.angebot.ist_mietangebot) | "\(.angebot.objekt): \(.angebot.optionen[].kaltmiete_eur_qm) €/m²  \(.quelle_link)"' comparables_decisions.jsonl
```

## Voraussetzung im Team

Die Auswertung ist nur so gut wie die Ablage: **jedes ein- und ausgehende Mietangebot gehört in den Drive-Leasing-Ordner** (Team-Regel aus der Asana-Aufgabe). Angebote, die nur im Mail-Postfach liegen, sieht der Job nicht.

## Bekannte Einschränkungen

- **Regions-Labels** sind kuratiert (`regions.py`). Unbekannte Leitregionen erscheinen als „PLZ-Gebiet 23" – die Zahl bleibt korrekt, nur die Beschriftung fehlt.
- **Dünne Datenbasis:** bei ~20 Angeboten erreicht kaum eine Leitregion n=3. Die Postleitzone trägt dann die Aussage; der Post weist das explizit aus.
- **Ohne PLZ keine Region.** Nennt ein Angebot nur den Ort, fällt die Zeile mit Grund aus der Statistik.
- **Ein Angebot pro Dokument.** Sammel-Dokumente mit mehreren Objekten liefern nur das erste – im Korpus bislang nicht vorgekommen.
- **Datei-Dedup über Prüfsumme:** inhaltlich identische, aber neu gerenderte PDFs (andere Bytes) gelten als zwei Dateien. Der Versions-Dedup in Schritt 5 fängt das ab, sofern Objekt und Anbieter erkannt wurden.
- **PDF-Schriften:** ohne den `kp-design`-Skill rendert das PDF mit Standardschriften – vollständig, aber nicht CI-treu.
- Der Slack-Post trägt **keine Datei-Anhänge**; CSV und PDF hängen am Actions-Lauf (90 Tage).

## Explizit außerhalb des Scopes

- **Propstack als Datenbasis** – laut Vorabanalyse ungeeignet: nur 1 von 20 abrufbaren Miet-Einheiten hatte einen Preis (Juni-Analyse: 944 von 1018 ohne Preis). Der Nebenbefund „`/units`-Listenendpoint liefert nur 20 Einheiten – Key-Scope prüfen" ist weiterhin offen und gehört nicht in diesen Handler.
- Abgeschlossene Mietverträge (nur indikative Angebote werden ausgewertet)
- Schreiben nach Propstack oder ins Drive
- Gesuch-Intake (separate Aufgabe)
