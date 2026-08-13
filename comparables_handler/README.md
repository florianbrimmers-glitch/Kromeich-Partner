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

### Gemessener Stand (12.08.2026, echte API)

Erhoben mit `scripts/propstack_miet_audit.py` und einem vollständigen Lauf:

| | |
|---|---|
| Einheiten in Propstack | ~2.050 |
| davon Mietobjekte | ~1.980 |
| **belegte Hallen-/Lagermieten (Datenpunkte)** | **333** |
| davon an Standorten | 221 |
| ausgeschlossen | 10 |
| Mieten anderer Flächenarten (nicht im Report) | 335 |

**Paginierung, zwei getrennte Befunde.**

Erstens die Seitengröße – der Nebenbefund „`/units` liefert nur 20 Einheiten" lag am fehlenden Parameter, nicht am Key-Scope:

| Aufruf | Ergebnis |
|---|---|
| `per=100` | **100 Einheiten** ✅ |
| `per_page=100` | 20 ❌ (wird ignoriert) |
| `limit=100` / ohne Parameter | 20 |

Der Listen-Endpoint respektiert also `per`. `objekte_handler/propstack.py` liegt damit **richtig**.

Zweitens – und schwerwiegender – **die Sortierung muss stabil sein.** Ohne `sort_by` sortiert Propstack offenbar nach Änderungszeit: bearbeitete Einheiten wandern nach vorn, die Seiten verschieben sich *während* der Paginierung und Einheiten fallen durchs Raster. Zwei direkt aufeinanderfolgende Läufe am 13.08.2026:

| Aufruf | Lauf 1 | Lauf 2 | Abweichung |
|---|---|---|---|
| ohne Sortierung | 2013 | 2027 | 107 bzw. 121 IDs nur in einem Lauf |
| `sort=id` / `order_by=id` | 2051 | 2021 | ebenfalls instabil (Parameter wird ignoriert) |
| **`sort_by=id&order=asc`** | **2134** | **2134** | **identisch** |

Die instabile Variante verlor also rund **120 Einheiten pro Lauf** – und jeden Lauf andere. Für einen monatlichen Report wäre das Rauschen ohne Marktbewegung. Nur `sort_by` greift (`config.PROPSTACK_SORTIERUNG`).

**Mieten stehen in Custom Fields, je Flächenart getrennt** und bereits als €/m². Ausgewertet werden nur die Felder, die es in der Propstack-**Maske** gibt:

| Feld | belegt | Median |
|---|---|---|
| `intern_mietpreis_hallenflache` | 161 | 7,50 |
| `mietpreis_hallenflache` | 62 | 6,45 |

**`*_miete_m_von` / `_bis` werden NICHT gelesen** (`ALTIMPORT_FELDER_IGNORIERT`). Diese Felder existieren in der Maske nicht und werden von niemandem gepflegt – sie stammen aus einem Alt-Import. Nachgewiesen am 13.08.2026 an „Stettiner Straße 2, Neuss": in der Maske sind Kaltmiete und beide Intern-Mietpreis-Felder **leer**, `lagerflache_miete_m_von` trug dennoch **1,00 €/m²** – zusammen mit einer zerschossenen Flächenangabe („26.000 m²" als 26), `preisangabe = "auf Anfrage"` und `object_type = LIVING`. Über den Bestand lagen **119 von 128** Werten dieses Felds unter „auf Anfrage", Minimum 1,00 €/m².

Das kostet Datenpunkte (245 → 113 Standorte), ist aber der Unterschied zwischen gepflegten und erfundenen Zahlen.

**Bereinigung im CRM** (`scripts/propstack_altimport_pruefen.py`, ausgeführt am 13.08.2026): 288 Werte in 113 Einheiten wurden gesichert und in drei Kategorien geteilt.

- **A – unplausibel und ohne internen Mietpreis: 39 Werte in 21 Einheiten geleert.** Fast alle saßen auf Einheiten, deren Flächen ebenfalls zerschossen sind (1–57 m²), z.B. Stettiner Straße 2 Neuss 1,00 €/m², Hamborner Straße Duisburg Mezzanine 350,00, Heinrich-Hertz-Straße Erkrath NK 23,00.
- **B – plausibel, interner Mietpreis vorhanden: unangetastet.** Redundant, der interne Wert gewinnt ohnehin.
- **C – plausibel, kein interner Mietpreis: NICHT migriert** (Entscheidung K&P). Das sind interne Einschätzungen; sie dürfen nicht nach außen und gehören nicht in die Report-Basis.

Bei der A-Bereinigung wurden **4 Einheiten zu viel geleert und wiederhergestellt**: bei Mezzanine- und Serviceflächen sind 2,00 €/m² ein normaler Preis, die 2,50er-Untergrenze gilt nur für Halle/Lager. Die Plausibilitätsprüfung im Skript misst deshalb Nebenkosten an NK-Grenzen und Mieten an Mietgrenzen (`ist_plausibel(feld, wert)`); eine flächenartabhängige Untergrenze fehlt noch – vor einem erneuten `--apply A` ist die CSV durchzusehen. Die Sicherung in `altimport_backup.json` macht jeden Schritt umkehrbar.

Die Standardfelder sind ebenfalls unbrauchbar: `base_rent` ist in 6 von 1.978 Einheiten gefüllt und mischt €/m² (6,00) mit absoluten Monatsmieten (19.848) – ohne Unterscheidungsmerkmal nicht sicher normalisierbar, deshalb in `STANDARDFELDER_IGNORIERT`.

**„Auf Anfrage" ist kein Ausschlussgrund.** K&P pflegt die publizierte Preisaussage im Custom Field `preisangabe` (nicht im Standard-Flag `price_on_inquiry`). 267 von 369 Einheiten mit hinterlegter Miete stehen dort auf „auf Anfrage" – öffentlich nicht genannt, intern bekannt ist genau der Normalfall. Ein Veto würde die wertvollsten Daten wegwerfen; das Feld fließt nur in die Zählung ein.

**Drei Fallen, die im echten Datenbestand scharf sind:**

1. `stellplatzmiete` / `lkw_stellplatzmiete` tragen 20–70 € **pro Stellplatz** (95 Einheiten). Eine Namens-Heuristik auf „miete" hätte sie als €/m² gelesen und jeden Median zerstört. Deshalb wird **ausschließlich** gesucht, was in `FLAECHENARTEN` explizit steht.
2. In `*_gesamt`-Flächenfeldern steckt bei ~190 Einheiten die deutsche Tausendertrennung in einem Dezimalfeld: `lagerflache_gesamt = 10.403` wird als „10,40 m²" angezeigt. Das ist ein **Datenfehler in Propstack**, nicht im Parser. Die Fläche wird verworfen und der Verdacht als Hinweis in den Datensatz geschrieben – die **Miete bleibt gültig**, denn sie steht schon als €/m². Ohne diese Trennung hingen 190 Datenpunkte an einer Flächenangabe, die sie nicht brauchen.

3. **Platzhalter-Mieten unter dem Marktniveau.** Die Untergrenze lag ursprünglich bei 1,00 €/m² – damit rutschte genau ein Platzhalter durch: „Stettiner Straße 2, Neuss" mit 1,00 €/m², während dieselbe Adresse andere Einheiten mit 3,00 führt. Die Grenze liegt jetzt bei **2,50 €/m²**; darunter gibt es für Hallen-/Lagerflächen keinen echten Markt. Betroffen sind fünf Werte (1,00 / 2,00 / 2,00 / 2,00 / 2,30), alle mit Grund im Datensatz.

Die betroffenen Einheiten lassen sich aus dem Datensatz ziehen:

```bash
grep "Tausendertrennung" comparables_dataset.csv | cut -d';' -f3,29
```

**Vor der Abnahme einmal ausführen:**

```bash
PROPSTACK_API_KEY=xxx python3 scripts/propstack_miet_audit.py --json audit.json
```

## Flächenarten im Report

**Ausgewertet wird nur `Halle/Lager`** (Stand 13.08.2026) – Büro, Mezzanine, Service- und Keller/Archivflächen sind bewusst draußen. Sie bleiben in `config.FLAECHENARTEN` definiert und lassen sich jederzeit wieder aufnehmen:

```bash
FLAECHENARTEN="Halle/Lager,Büro" python -m comparables_handler.main
```

Dauerhaft: `config.FLAECHENARTEN_STANDARD` erweitern. Die nicht ausgewerteten Mieten werden **gezählt und geloggt** („Flächenart nicht im Report"), damit die Auslassung sichtbar bleibt – im letzten Lauf 335 Datenpunkte.

Freitext-Nutzungsarten aus den Drive-Angeboten („Logistik", „Halle", „Lagerfläche") werden über `config.NUTZUNGSART_SYNONYME` auf `Halle/Lager` abgebildet, damit Drive- und Propstack-Zeilen im selben Abschnitt landen. Unbekannte Bezeichnungen bleiben unverändert und fallen dann durch den Report-Filter – mit Grund im Datensatz, nicht still.

## Ablauf (Propstack)

1. **Laden** – `GET /units` paginiert (`per` + `page`, `expand=1`, `marketing_type=RENT`), Kaufobjekte fallen raus.
2. **Eine Zeile je Flächenart** – für jede Flächenart aus `config.FLAECHENARTEN` wird geprüft, ob eine Miete hinterlegt ist; anschließend filtert der Report auf die ausgewerteten Arten. Welches Feld gegriffen hat, steht als `miete_feld` in jeder Zeile.
3. **Keine Umrechnung** – die Custom Fields stehen bereits in €/m²/Monat. Ein Betrag über 25 €/m² ist deshalb kein Umrechnungsfall, sondern ein Datenfehler (absolute Monatsmiete im €/m²-Feld) und wird **mit Grund** ausgeschlossen.
4. **Fläche nur als Kontext** – eine unplausible Fläche verwirft das Flächenfeld, nicht den Datenpunkt.
5. **Aggregation** – getrennt je Flächenart, dann je Region.

## Ablauf (Drive)

1. **Discovery** – zwei Wege gleichzeitig: Titel-Suche (`Mietangebot` im Dateinamen) plus Rekursion über die Ordner `03. Leasing` und `Mietangebote` (IDs in `config.SEED_FOLDER_IDS`). Verknüpfungen werden aufgelöst, Shared Drives eingeschlossen.
2. **Datei-Dedup** – dasselbe Angebot liegt im Drive typischerweise 3–5× in verschiedenen Ordnern. Zusammengefasst wird über die Inhalts-Prüfsumme (`md5Checksum`), ersatzweise Größe + MIME-Typ. Gemessen am 12.08.2026: **~70 Treffer → ~22 verschiedene Dokumente.** Ohne diesen Schritt ginge jede Kopie einzeln an Claude.
3. **Regel-Ausschluss vor dem LLM-Call** – eigene Vorlagen (`Vorlage`, `Muster`, …), die Kromeich-Büromiete (`Mietangebot-Kromeich GmbH-*`) und Anlagen-/Beiblatt-Dateien fliegen am Dateinamen raus und kosten keinen Token.
4. **Extraktion** – PDFs gehen als Dokument-Block **direkt an Claude** (liest auch gescannte Angebote und Tabellen-Layouts, an denen eine Textextraktion scheitert). DOCX/PPTX/XLSX werden zu Text aufbereitet, Google Docs/Slides/Sheets über die Drive-API exportiert. Ergebnisse landen im Extraktions-Cache.
5. **Versions-Dedup** – liegen mehrere Fassungen zu Objekt + Anbieter vor, zählt nur die jüngste (Angebotsdatum, ersatzweise Drive-`modifiedTime`). Realer Fall: das VIR21-Angebot existiert in drei Fassungen (16.03., 20.03., 30.04.2026).
6. **Normalisierung** – **eine Zeile pro Laufzeit-Option**. Absolute Mieten werden über die Fläche in €/m²/Monat umgerechnet, Jahresmieten auf den Monat. Effektivmiete = Kaltmiete geglättet um die mietfreie Zeit. Unplausible Werte werden **mit Grund** ausgeschlossen, nicht gelöscht.
7. **Aggregation** – Median, Spanne und n je Leitregion (2-stellige PLZ, ab n=3) und je Postleitzone (1-stellig, immer), plus Gesamtzeile.
8. **Ausgabe** – Slack-Post in den Zielkanal, CSV-Datensatz und optional das K&P-PDF; jede Dokument-Entscheidung als JSONL-Zeile.

## Kennzahlen-Tabelle (Marktbericht-Layout)

Zusätzlich zur regionalen Auswertung baut der Report eine Kennzahlen-Tabelle im Stil der üblichen Logistik-Marktberichte – je Flächenart:

```
                                     n  Ø-MIETE  SPITZE  2025-08  MEDIAN  VERÄNDERUNG
Bedeutende Logistikmärkte
   Berlin                            8     8,55   11,38     9,55    9,72       +1,8 %
   Düsseldorf                       89     6,49    8,90     5,75    6,50      +13,0 %
   …
Bedeutende Logistikmärkte gesamt    152     6,85    9,50     6,26    6,90      +10,2 %
Sonstige Standorte
   Ruhrgebiet                      111     6,37    8,50     6,16    6,50       +5,5 %
   Übrige Logistikregionen          85     5,61    8,48     4,86    5,49      +13,0 %
Sonstige Standorte gesamt          196     6,04    8,50     5,49    6,00       +9,3 %
Gesamt                             348     6,39    9,30     6,15    6,25       +1,6 %
Anteil intern bekannter Konditionen                        46,7 %  46,0 %  -0,7 %-Pkte.
Anteil bereits vermieteter Flächen                          1,4 %   6,3 %  +4,9 %-Pkte.
Anteil mit Nebenkosten-Angabe                               0,0 %   3,4 %  +3,4 %-Pkte.
```

**Lesart:**

- **`n` zählt Standorte, nicht Einheiten.** Ein Multi-Unit-Objekt ist EIN Marktdatenpunkt: gemessen am 13.08.2026 trugen 14 Einheiten der Neue Ritterstraße 34 alle identisch 8,50 €/m², und die 10 größten Standorte stellten 21 % aller Datenpunkte. Ungewichtet verschob das den Berlin-Median um 1,67 €/m². Je Standort geht der Median seiner Einheiten ein; `AGGREGATION=einheit` schaltet auf Zählung je Einheit um (relevant für „was zahlt ein Mieter", nicht für „wie hoch ist das Marktniveau"). Die Einheitenzahl bleibt als `n_einheiten` erhalten und der CSV-Datensatz enthält weiterhin jede Einheit.
- `n` addiert sich über die Gruppen, die **Mietwerte nicht** – sie werden je Gruppe über alle Datenpunkte neu berechnet (anders als beim Flächenumsatz in den Marktberichten, wo die Zwischensumme wirklich eine Summe ist).
- **Ø-Miete** ist das arithmetische Mittel, **nicht flächengewichtet**. Marktberichte gewichten üblicherweise über die Fläche; das ginge hier nur mit den Propstack-Flächen, und die sind bei ~190 Einheiten fehlerhaft erfasst. Ein kaputtes Gewicht verdirbt den Wert stärker als das fehlende.
- **Spitze** ist das `SPITZENMIETE_PERZENTIL` (95.) Perzentil, **nicht das Maximum**: ein einzelner Ausreißer soll das Spitzenniveau nicht bestimmen. Das Maximum steht in der Spanne-Spalte der regionalen Auswertung. `SPITZENMIETE_PERZENTIL = 1.0` ergibt das echte Maximum. Bei wenigen Datenpunkten nähert sich die Spitzenmiete zwangsläufig dem Maximum – bei n=3 ist kein Spitzensegment abgrenzbar.
- Die **Veränderung** vergleicht den Median. Ø-Miete und Spitze weisen den aktuellen Stand aus; beide werden aber im Snapshot mitgeschrieben (`…|durchschnitt`, `…|spitze`), sodass die Zeitreihe später ohne Datenverlust auf sie erweiterbar ist.
- Anteile werden in **Prozentpunkten** verändert ausgewiesen.

Die Marktgrenzen stehen in `config.MARKTGEBIETE_TOP` und `MARKTGEBIET_RUHR` und sind eine **fachliche Festlegung, die K&P bestätigen sollte** – etwa ob Krefeld (PLZ 47) zum Ruhrgebiet oder zu Düsseldorf zählt und ob Aachen (52) zu Köln gehört. Märkte ohne Datenpunkt erscheinen nicht als Leerzeile; die Reihenfolge der Top-Märkte ist fest, damit die Tabelle monatlich gleich aussieht.

### Zeitreihe (Voraussetzung der Veränderungsspalte)

**Propstack führt keine Miethistorie.** Ein Periodenvergleich lässt sich daraus nicht ableiten – er entsteht nur, weil jeder Lauf seine Mediane in `comparables_snapshots.json` fortschreibt (`SNAPSHOT_PATH`).

- Beim **ersten Lauf bleibt die Veränderungsspalte leer** und der Report sagt das auch. Es wird keine Basis erfunden.
- Verglichen wird mit dem Stand vor `VERGLEICH_MONATE` (12) Monaten, Toleranz ±`VERGLEICH_TOLERANZ_MONATE` (3). Fehlt ein passender Stand, bleibt die Spalte leer statt gegen eine unpassende Basis zu rechnen.
- Zwei Läufe im selben Monat ersetzen sich, statt zwei Stände zu erzeugen.
- Die Datei wird vom Workflow **ins Repository zurückgeschrieben** (Schritt „Zeitreihe fortschreiben", nur auf `main`). Ein Actions-Cache reicht nicht: er kann evakuiert werden, und dann bricht die Zeitreihe ab.
- `NO_WRITE=true` schreibt die Zeitreihe **nicht** fort – Testläufe verfälschen sie also nicht.

Lokal testen ohne die echte Zeitreihe anzufassen:

```bash
SNAPSHOT_PATH=/tmp/snap.json PROPSTACK_API_KEY=xxx NO_WRITE=true MAKE_PDF=true \
  python -m comparables_handler.main
```

## Vertraulichkeit: interne und externe Fassung

163 der 225 Mieten stehen in `intern_mietpreis_*` – Konditionen, die K&P aus Mandaten und Anfragen kennt und die der Vermieter **nicht veröffentlicht**. Vorgabe K&P (13.08.2026): solche Werte dürfen einzeln nicht nach außen. Der Report erzeugt deshalb aus **derselben Auswertung** zwei PDFs (`VERTRAULICHKEIT`, Default `beide`):

| | `comparables_report.pdf` (intern) | `comparables_report_extern.pdf` |
|---|---|---|
| Zeilen unter `MIN_N_EXTERN` (5) | ja | **nein** |
| Einzelwerte-Block (n < 3) | ja | **nein** |
| Objektliste „Erfasste Objekte" | ja | **nein** |
| Fußzeile | „nur zur internen Verwendung" | „Weitergabe nur an den Adressaten" |

Maßstab ist die **Zuordenbarkeit**, nicht die Zahl selbst: ein Median über 114 Standorte gehört keinem Objekt, eine Zeile mit n=1 ist exakt die Miete eines Objekts. Deshalb fällt die Objektliste weg (sie ist der Schlüssel von Wert zu Objekt), während Spannen und Perzentile über den Gesamtbestand stehen bleiben.

`MIN_N_EXTERN = 5` liegt bewusst über `MIN_N_LEITREGION = 3`. Am Stand 13.08.2026 unterdrückt das in der externen Fassung 44 Zeilen; München (n=1) und Leipzig/Halle (n=1) verschwinden, Berlin (n=5) bleibt.

**Der Slack-Post ist immer die interne Fassung** – er geht in einen internen Kanal. Auch der CSV-Datensatz bleibt vollständig; er ist ein Arbeitsdatensatz, kein Weitergabe-Dokument.

## Ablage in Asana

Jeder Lauf legt den Monatsbericht als **Unteraufgabe** unter einer festen Oberaufgabe ab, mit beiden PDFs im Anhang:

```
03. (VER) Vermietung / Leasingpaket
  └─ Vergleichsmieten – Monatsberichte              <- Oberaufgabe, 1217454616756224
       ├─ Vergleichsmieten August 2026
       │    ├─ Vergleichsmieten_August_2026.pdf         (intern)
       │    └─ Vergleichsmieten_August_2026_extern.pdf  (freigegeben)
       └─ Vergleichsmieten September 2026
```

Die Beschreibung der Unteraufgabe trägt die Kennzahlen (Median, Ø, Spitze, Mediane je Markt), die Quellenzählung, den Link auf den Actions-Lauf und den Hinweis, welche der beiden Dateien nach außen darf.

**Der Asana-MCP-Connector kann keine Dateien anhängen** – es gibt dort nur ein Lese-Tool für Attachments. Der Upload läuft deshalb über die REST-API (`POST /attachments`, multipart) mit einem **Personal Access Token**: dasselbe Secret, das der `events_handler` nutzt (`ASANA_ACCESS_TOKEN`, Fallback-Namen siehe `config.ASANA_TOKEN_ENV_NAMES`). Ohne Token wird die Ablage übersprungen und der Grund geloggt; der Report selbst läuft weiter.

**Idempotenz:** der Aufgabenname (`Vergleichsmieten <Monat> <Jahr>`) ist der Schlüssel. Läuft der Job im selben Monat erneut, wird die bestehende Unteraufgabe aktualisiert – kein Duplikat. Die Anhänge werden dabei **ersetzt**, nicht übersprungen: erst den neuen hochladen, dann den alten entfernen. Überspringen wäre falsch, weil ein Wiederholungslauf den neueren Stand trägt; am 13.08.2026 wäre so die nicht CI-treue Fassung unter dem Namen des aktuellen Monats liegengeblieben. Schlägt der Upload fehl, behält die Aufgabe den alten Stand statt keinen.

**Nachgewiesen am 13.08.2026** (Läufe [31700073360](https://github.com/florianbrimmers-glitch/Kromeich-Partner/actions/runs/31700073360) und [31700822006](https://github.com/florianbrimmers-glitch/Kromeich-Partner/actions/runs/31700822006)): Unteraufgabe angelegt, beide PDFs hängen dran, beim zweiten Lauf ersetzt statt dupliziert. Das Secret heißt im Repository **`ASANA_TOKEN`** – `ASANA_ACCESS_TOKEN` ist leer, die Fallback-Liste deckt das ab.

**`ASANA_UPLOAD` ist Opt-in (Default aus)** und bewusst **nicht** an `DRY_RUN` gekoppelt: `DRY_RUN` hält den Slack-Post zurück, bis der Report inhaltlich abgenommen ist, während die Asana-Ablage ein internes Archiv ist und schon vorher laufen soll. Umgekehrt darf ein lokaler Testlauf mit gesetztem Token nicht ungefragt Aufgaben anlegen. `NO_WRITE=true` schaltet auch Asana ab und loggt stattdessen die Beschreibung, die entstanden wäre.

Der CSV-Datensatz wird **nicht** angehängt (`ASANA_ATTACH_DATASET=true` schaltet ihn zu): er enthält jede Einheit mit Adresse und Miete, und ein Anhang wandert leichter weiter als eine Zeile im Log.

## Betriebsmodi

| Modus | Slack-Post | CSV + JSONL + PDF | Zweck |
|---|---|---|---|
| `NO_WRITE=true` | nein | ja | Testen mit echten Daten, beliebig wiederholbar (schreibt die Zeitreihe nicht fort) |
| `DRY_RUN=true` | nein (nur ins Log) | ja | Report inhaltlich prüfen, bevor das Team ihn sieht |
| `DRY_RUN=false` | ja | ja | Normalbetrieb |

### Lauf von Hand starten

`workflow_dispatch` greift erst, wenn `comparables-report.yml` auf dem **Default-Branch** liegt – solange die Datei nur im Feature-Branch liegt, antwortet GitHub mit **404**, auch wenn man den Branch als Ref angibt. Für die Abnahmeläufe wurde deshalb vorübergehend ein `push`-Trigger auf dem Feature-Branch verwendet. Nach dem Merge nach `main` läuft *Actions → Comparables Report → Run workflow* normal.

### Scharfschalten

Der Cron läuft **bewusst noch im Dry-Run**. Drei Dinge sind vor dem Scharfschalten zu klären:

0. **Feldbelegung gegenprüfen** – `scripts/propstack_miet_audit.py` laufen lassen. Die Feldnamen in `config.FLAECHENARTEN` sind am 12.08.2026 gegen den echten Bestand verifiziert; kommen in Propstack neue Custom Fields dazu, gehören sie dort ergänzt.
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
| `VERTRAULICHKEIT` | nein | `beide` | `intern` / `extern` / `beide` – welche PDF-Fassung(en) entstehen |
| `PDF_PATH` | nein | `comparables_report.pdf` | Ausgabepfad der internen Fassung; die externe hängt `_extern` an |
| `KP_DESIGN_DIR` | nein | `~/.claude/skills/synced/kp-design` | Erste Suchstelle für die K&P-Schriften; fehlt sie, greift `assets/fonts` im Repository (siehe dortige README) |
| `ASANA_UPLOAD` | nein | `false` | Monatsbericht als Asana-Unteraufgabe ablegen (Opt-in) |
| `ASANA_ACCESS_TOKEN` | für Asana | – | Personal Access Token; Fallbacks: `ASANA_TOKEN`, `ASANA_PAT`, `ASANA_API_KEY`, `ASANA_API_TOKEN`, `ASANA_PERSONAL_ACCESS_TOKEN` |
| `ASANA_PARENT_TASK_ID` | nein | `1217454616756224` | Oberaufgabe, unter der die Monatsberichte hängen |
| `ASANA_ATTACH_DATASET` | nein | `false` | zusätzlich die CSV anhängen |
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

- **Propstack kennt keine Laufzeit-Optionen**, keine mietfreie Zeit und keine Indexierung. Die Effektivmiete entspricht dort der Kaltmiete; die Spalte wird im PDF automatisch weggelassen, wenn sie nichts hinzufügt. Diese Konditionen stehen nur in den Drive-Angeboten.
- **Propstack-Mieten sind eigene Angebotsmieten**, keine Marktmieten Dritter. Für die Marktsicht braucht es `QUELLE=beide`.
- **Die 25-€/m²-Grenze** trennt plausible €/m²-Werte von Datenfehlern. Eine echte Büromiete über 25 €/m² (Innenstadt-Toplage) würde damit fälschlich ausgeschlossen – im Logistik-Portfolio bislang kein Fall, bei Büroflächen im Auge behalten.
- **Fehlende Flächen:** bei ~190 Einheiten ist die Flächenangabe in Propstack fehlerhaft (siehe oben). Der Median der Fläche pro Region ist deshalb weniger belastbar als der Mietmedian.
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
- Korrektur der fehlerhaften Flächenangaben in Propstack (~190 Einheiten mit Tausendertrennung in einem Dezimalfeld) – der Handler meldet sie, ändert aber nichts im CRM.
