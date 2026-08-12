# Comparables-Report (Propstack + Drive → Slack + K&P-PDF)

Liefert **Vergleichsmieten pro Region** – Median, Spanne und n. Läuft als monatlicher GitHub-Actions-Cron (`.github/workflows/comparables-report.yml`, 1. des Monats 05:00 UTC), Entrypoint `python -m comparables_handler.main`.

Eigenständiges Paket – **kein Code-Sharing mit `src/`** oder den anderen Handlern.

Umsetzung der Asana-Aufgabe [Comparables-Report aus Mietangeboten](https://app.asana.com/1/1207989209959731/task/1213887655130097).

## Datenquellen

Steuerung über `QUELLE`:

| `QUELLE` | Inhalt |
|---|---|
| `propstack` (Default) | Die in Propstack gepflegten Mieten – **Angebotsmieten der eigenen Mandate**. Strukturiert, keine LLM-Extraktion nötig. |
| `drive` | Mietangebots-Dokumente aus dem Google Drive – vor allem **erhaltene Fremdangebote** (Mileway, HIH, Westcore …). Braucht Claude zur Extraktion. |
| `beide` | Union beider Quellen; jede Zeile trägt ihre Herkunft in der Spalte `quelle`. |

Die beiden Quellen überschneiden sich kaum und beantworten unterschiedliche Fragen: Propstack sagt, **was K&P verlangt**, das Drive sagt, **was der Markt anbietet**. Für einen belastbaren Marktmedian ist `beide` die vollständigere Basis; die Herkunft steht in jeder Zeile und im Slack-Post.

### Zur Größe der Datenbasis

**Wenige Mieten bei vielen Objekten ist der Normalfall, kein Datenfehler.** Mietkonditionen werden am Markt nicht geteilt – Vermieter veröffentlichen sie nicht. Was K&P kennt, stammt aus eigenen Mandaten, Beratungsprojekten und konkreten Anfragen. Jeder einzelne Wert ist damit eine **belegte** Kondition und nicht aus einem Marktbericht geschätzt. Der aussagekräftige Maßstab ist deshalb die **absolute Zahl** der bekannten Mieten, nicht ihr Anteil am Gesamtbestand.

Daraus folgen zwei Design-Entscheidungen:

- Der Report führt die **Anzahl belegter Mieten** als Kernaussage. Eine Abdeckungsquote wird nicht als Kennzahl geführt, weil sie eine Normalität als Mangel darstellen würde.
- Regionen mit weniger als `MIN_N_LEITREGION` (3) Datenpunkten werden **nicht unterdrückt**, sondern als **Einzelwerte** ausgewiesen – ohne Median-Anspruch, aber mit den konkreten Werten. Ein einzelner belegter Mietwert ist im Kundengespräch wertvoll; er darf nur nicht wie ein Median auftreten.

Ein Sonderfall bleibt ein echtes Warnsignal: findet der Lauf in **keiner einzigen** Einheit einen Betrag, ist das kein Datenmangel, sondern ein Hinweis auf einen falschen Feldnamen. Nur dieser Fall wird als Fehler gemeldet.

### Zum Nebenbefund „/units liefert nur 20 Einheiten"

Die Asana-Aufgabe notierte diesen Punkt als offen. Er ist unabhängig von der Preis-Abdeckung und betrifft, wie viele Einheiten überhaupt gelesen werden:

`objekte_handler/propstack.py` schickt `per: 100`, der funktionierende Aufruf im `propstack-pipeline-report`-Skill dagegen `per_page: 100` + `page`. Ignoriert Propstack `per`, fällt die Antwort auf die Default-Seitengröße **20** zurück. Dieser Handler schickt deshalb **beide** Parameternamen und paginiert konsequent – sonst wären selbst bei perfekter Pflege nur 20 Einheiten sichtbar.

Zusätzlich können Mieten in Standardfeldern (`base_rent`, `price`, …) **oder in Custom Fields** stehen; geprüft werden beide (`config.KALTMIETE_FELDER`, `CUSTOM_FIELD_MIETE_MARKER`). Einheiten mit `price_on_inquiry` („auf Anfrage") werden getrennt gezählt.

**Vor der Abnahme einmal ausführen:**

```bash
PROPSTACK_API_KEY=xxx python3 scripts/propstack_miet_audit.py --json audit.json
```

Das Skript prüft die Paginierungs-Varianten gegeneinander und zählt über **alle** Einheiten, welche Felder Beträge tragen. Ergebnis: wie viele Mieten tatsächlich hinterlegt sind und in welchem Feldnamen – der gehört dann in `KALTMIETE_FELDER` nach vorn.

## Ablauf (Propstack)

1. **Laden** – `GET /units` paginiert (`per_page` + `page`, `expand=1`, `marketing_type=RENT`), Kaufobjekte fallen raus.
2. **Feld-Auflösung** – Kaltmiete, Nebenkosten und Fläche aus den Kandidatenfeldern; welches Feld gegriffen hat, steht als `miete_feld` in jeder Zeile.
3. **Normalisierung** – Beträge über `ABSOLUT_SCHWELLE_EUR_QM` (25 €/m²) gelten als absolute Monatsmiete und werden über die Fläche in €/m² umgerechnet. Fehlt die Fläche, bleibt der Wert stehen und fällt der Plausibilitätsprüfung **mit Grund** auf – nie stillschweigend.
4. **Aggregation** – wie unten, gemeinsam mit den Drive-Zeilen.

## Ablauf (Drive)

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

Der Cron läuft **bewusst noch im Dry-Run**. Drei Dinge sind vor dem Scharfschalten zu klären:

0. **Feldnamen bestätigen** – `scripts/propstack_miet_audit.py` einmal laufen lassen (siehe oben) und das häufigste Mietfeld in `KALTMIETE_FELDER` nach vorn setzen. Dabei zeigt sich auch, wie viele Mieten pro Region zusammenkommen und ob `QUELLE=beide` zusätzliche Datenpunkte bringt.
1. **Zielkanal.** Es gibt (Stand 12.08.2026) keinen Leasing-/Comparables-Kanal im Workspace; Default ist deshalb `#objekte` (`C07GH7AN80J`). Ein eigener Kanal ist sinnvoller – dann `COMPARABLES_CHANNEL` im Workflow setzen.
2. **Inhaltliche Abnahme** des ersten Reports (Actions → *Comparables Report* → Run workflow, `dry_run: true`), insbesondere der extrahierten Kaltmieten gegen die Quell-PDFs.

Danach im Workflow `DRY_RUN: ${{ github.event.inputs.dry_run || 'false' }}` setzen.

## Umgebungsvariablen

| Variable | Pflicht | Default | Bedeutung |
|---|---|---|---|
| `QUELLE` | nein | `propstack` | `propstack` / `drive` / `beide` |
| `PROPSTACK_API_KEY` | für Propstack | – | v1-Key (dasselbe Secret wie die anderen Handler) |
| `PROPSTACK_KEY_OBJEKTE` | nein | – | Optionaler Override für den units-Zugriff |
| `GOOGLE_CLIENT_ID` | für Drive | – | OAuth-Client (wie Kontakt-Pipeline) |
| `GOOGLE_CLIENT_SECRET` | für Drive | – | OAuth-Client |
| `GOOGLE_REFRESH_TOKEN_DRIVE` | für Drive | – | Refresh-Token **mit `drive.readonly`** (siehe unten) |
| `ANTHROPIC_API_KEY` | für Drive | – | Claude-Extraktion (Propstack braucht kein LLM) |
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

Nur nötig für `QUELLE=drive` oder `beide`. Der Propstack-Zweig nutzt das bestehende `PROPSTACK_API_KEY`.

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

# Propstack (Default)
PROPSTACK_API_KEY=xxx NO_WRITE=true MAKE_PDF=true python -m comparables_handler.main

# beide Quellen
QUELLE=beide PROPSTACK_API_KEY=xxx GOOGLE_CLIENT_ID=… GOOGLE_CLIENT_SECRET=… \
  GOOGLE_REFRESH_TOKEN_DRIVE=… ANTHROPIC_API_KEY=… NO_WRITE=true \
  python -m comparables_handler.main
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

Die Auswertung ist nur so gut wie die Pflege:

- **Propstack:** Miete und Fläche an der Einheit hinterlegen. Ist die Miete unbekannt, `price_on_inquiry` setzen – dann erscheint die Einheit als „auf Anfrage" statt als Datenlücke.
- **Drive:** jedes ein- und ausgehende Mietangebot in den Leasing-Ordner ablegen (Team-Regel aus der Asana-Aufgabe). Angebote, die nur im Mail-Postfach liegen, sieht der Job nicht.

## Bekannte Einschränkungen

- **Propstack liefert nur eine Zeile je Einheit** – keine Laufzeit-Optionen, keine mietfreie Zeit, keine Indexierung. Die Effektivmiete entspricht dort der Kaltmiete. Diese Konditionen stehen nur in den Drive-Angeboten.
- **Propstack-Mieten sind eigene Angebotsmieten**, keine Marktmieten Dritter. Für die Marktsicht braucht es `QUELLE=beide`.
- **Absolut vs. €/m²** wird über die Schwelle von 25 €/m² unterschieden. Eine echte Büro-Kaltmiete über 25 €/m² würde fälschlich als Absolutbetrag gelesen – für Logistik-/Hallenflächen unkritisch, bei Büroflächen in Innenstadtlage im Auge behalten.
- **Regions-Labels** sind kuratiert (`regions.py`). Unbekannte Leitregionen erscheinen als „PLZ-Gebiet 23" – die Zahl bleibt korrekt, nur die Beschriftung fehlt.
- **Dünne Datenbasis:** bei ~20 Angeboten erreicht kaum eine Leitregion n=3. Die Postleitzone trägt dann die Aussage; der Post weist das explizit aus.
- **Ohne PLZ keine Region.** Nennt ein Angebot nur den Ort, fällt die Zeile mit Grund aus der Statistik.
- **Ein Angebot pro Dokument.** Sammel-Dokumente mit mehreren Objekten liefern nur das erste – im Korpus bislang nicht vorgekommen.
- **Datei-Dedup über Prüfsumme:** inhaltlich identische, aber neu gerenderte PDFs (andere Bytes) gelten als zwei Dateien. Der Versions-Dedup in Schritt 5 fängt das ab, sofern Objekt und Anbieter erkannt wurden.
- **PDF-Schriften:** ohne den `kp-design`-Skill rendert das PDF mit Standardschriften – vollständig, aber nicht CI-treu.
- Der Slack-Post trägt **keine Datei-Anhänge**; CSV und PDF hängen am Actions-Lauf (90 Tage).

## Explizit außerhalb des Scopes

- Abgeschlossene Mietverträge – ausgewertet werden **Angebotsmieten** (Propstack-Mandate und indikative Angebote), keine Vertragsmieten.
- Schreiben nach Propstack oder ins Drive – der Handler liest ausschließlich.
- Gesuch-Intake (separate Aufgabe)
- Reparatur von `objekte_handler/propstack.py` (schickt `per: 100` statt `per_page`) – dieser Handler umgeht das Problem für sich; der Fix am bestehenden Handler ist eine eigene Änderung.
