# Notion „Feld-Mapping“ – Korrekturen vom 10.11.2026 (noch einzutragen)

Dieser Text gehört als neuer Abschnitt ans Ende der Notion-Seite „🔧 Propstack API – Feld-Mapping (Logistik)“.

**Stand 10.11.2026: nicht eingetragen.** Der Notion-Workspace hat sein Kontingent an freien Blöcken verbraucht. Löschen hilft dabei nicht: Notion zählt alle jemals erzeugten Blöcke, nicht die vorhandenen (Notion-Hilfe „Understanding block usage“). Neue Abschnitte lassen sich erst anlegen, wenn der Workspace auf einen bezahlten Tarif wechselt oder nur noch ein Mitglied hat (weitere Personen als Gäste).

Bereits in Notion stehen Kurzhinweise direkt an den überholten Stellen. Das ging, weil Text in bestehenden Absätzen keine neuen Blöcke braucht:

- Projekt-Felder: Hinweis zu den Landing-Page-Toggles
- Korrektur 4 (`note`): Überschrift und Text, dazu die Wiederholung in Korrektur 23
- Korrektur 6 (Bilder): `image[title]`
- Korrektur 24 (`relationships`): Überschrift und Text
- Korrektur 29 (Provision): Vermerk, dass die Regel am 10.11.2026 bestätigt wurde
- Korrektur 31 (`unit_id`)
- Korrektur 34 (Koordinaten): Ergänzung zum Gegenlesen

Alles ab der Trennlinie unverändert nach Notion übernehmen.

---

## Korrekturen 10.11.2026 — empirisch verifiziert

Gemessen am 09./10.11.2026 beim Live-Test des Propstack-MCP-Servers (Connector für Claude). Testdatensätze, alle mit dem Merkmal `MCP-TEST`: Projekte **603710** und **613378**, Einheiten **6274457**, **6274458** und **6375202**. Gelesen wurde durchgehend per Einzel-GET mit `?new=1`. Diesen Parameter nennt die Seite bisher nirgends — er erklärt, warum frühere Läufe Notiz und Verknüpfungen für nicht lesbar hielten. Die Korrekturen 4, 6, 23, 24, 29, 31 und 34 sowie der Hinweis zu den Landing-Page-Toggles tragen seit dem 10.11.2026 einen Kurzhinweis; hier steht die ausführliche Fassung.

### 44. `GET /v1/units/:id?new=1` liefert, was im Einzel-GET angeblich fehlt

Mit `?new=1` stehen im Einzel-GET einer Einheit:

- `note` — das UI-Feld „Interne Notizen“ (Korrektur 45)
- `relationships` als Liste (Korrektur 46)
- die Standard-Flächen- und Technikfelder mit Wert: `rs_category`, `total_floor_space`, `industrial_area`, `usable_floor_space`, `plot_area`, `hall_height`, `floor_load`
- Status, `rented`, Betreuer, die Custom Fields und die Bilder mit `title` und `is_floorplan`

Ein Teil der Felder kommt in diesem Format als Objekt (`{"label": …, "value": …}` bzw. `{"value": …, "pretty_value": …}`) statt als nackter Wert — beim Auslesen `value` nehmen.

Belegt an Einheit **4465616**, dem Testobjekt der Korrektur 27: `industrial_area` 3206, `total_floor_space` 3429, `usable_floor_space` 223, `hall_height` 8 und `floor_load` 5000 stehen im Einzel-GET mit `?new=1`.

Die Korrekturen 12 und 27 beschreiben den GET **ohne** den Parameter; der wurde hier nicht nachgemessen. Für Sammelabfragen bleibt `expand=1` der Kanal.

### 45. `note` ist schreibbar — Korrektur 4 war falsch

> ⚠️ **Nie blind schreiben.** Ein PUT mit `note` setzt das ganze Feld neu. An Bestandsobjekten stehen dort von Hand gepflegte Interne Notizen (Beispiel: Einheit 5220033). Erst lesen, dann den bisherigen Text plus Ergänzung zurückschreiben. Ist der bisherige Text nicht lesbar — das gilt für jedes Projekt —, nicht schreiben.

**Einheit:** `PUT /v1/units/:id` mit `{"property":{"note":"…"}}` wird gespeichert. Belegt an Einheit **6375202**: nur `note` geschrieben, danach per `GET …?new=1` gegengelesen, der Text stand vollständig da. Dass `note` das UI-Feld „Interne Notizen“ ist, zeigt Bestandsobjekt **5220033**: Die dort von Hand gepflegten Notizen kommen unter genau diesem Key zurück.

**Projekt:** `POST /v1/projects` mit `note` im `project`-Objekt wird gespeichert — in der Oberfläche unter „Interne Notizen“ bestätigt (Projekt **613378**, Florian Brimmers, 10.11.2026). Der Projekt-GET liefert `note` aber nie, auch nicht mit `?new=1`. Die Beobachtung aus Korrektur 4 („der Key erscheint im GET gar nicht“) stimmt also, der Schluss „nicht schreibbar“ nicht.

**Regeln:**

- Interne Angaben gehören nach `note`. Das How-to nennt für die Internen Notizen: Link zum Exposé bzw. zur Website, Mandat, Mietpreise, Provisionsregelungen, Projektname des Entwicklers.
- Einheit: per `?new=1` lesen, anhängen, zurückschreiben.
- Projekt: `note` nur beim Anlegen setzen. An einem bestehenden Projekt würde ein PUT den vorhandenen Text ungesehen überschreiben.
- `bemerkung` ist nur noch Änderungsprotokoll (Entscheidung Florian Brimmers, 10.11.2026): der Eintrag „Angelegt …“ und Vermerke, was geändert wurde und warum. Das Team liest das Feld kaum — nichts hineinschreiben, was jemand lesen muss. Offene Punkte gehören in die Prüfaufgabe.

### 46. `relationships` ist lesbar — an Einheit und Projekt

`GET /v1/units/:id?new=1` und `GET /v1/projects/:id` liefern `relationships` als Liste. Jeder Eintrag trägt `id`, `name`, `internal_name` (`owner` oder `partner`) und `client_id`. Im GET heißt der Kontakt also `client_id`, beim Schreiben `related_client_id`. Belegt an Einheit **6274457** und Projekt **603710**.

- Von Hand in der Oberfläche hinterlegte Kontakte („Ansprechpartner → Kontakt“) sind `internal_name: "partner"` mit `name: null` (Bestandsobjekt 6324578). Per API geht dasselbe ohne `name`.
- Am **Projekt** hinkt die Liste: Eine frisch gesetzte Verknüpfung erschien dort erst nach dem nächsten Speichern des Projekts. Zeigt die Liste die Verknüpfung nicht, als Gegenprobe denselben PUT noch einmal senden — die Ablehnung „bereits mit dem Kontakt verbunden“ bestätigt sie, ohne dass etwas doppelt entsteht.
- Der Umweg über die paginierte Liste `GET /v1/relationships` (Korrektur 24) ist für die Prüfung eines einzelnen Datensatzes nicht mehr nötig.

### 47. `show_units_on_landing_page` ist der Schalter „Einheitenliste im Exposé anzeigen“

Der Projekt-GET führt das Feld `show_units_on_landing_page` (Boolean). Es lässt sich flach im `project`-Objekt setzen und im GET gegenlesen. Belegt per PUT an Projekt **603710** (vorher nicht gesetzt, danach `true`); Projekt **613378** wurde per POST mit `true` angelegt und liefert `true`.

Abgleich mit der Oberfläche (Florian Brimmers, 10.11.2026), in beide Richtungen:

- Projekt 613378, Feld `true`: „Einheitenliste im Exposé anzeigen“ war **an**, „Auf der Landing Page auf die jeweiligen Einheiten verlinken“ war **aus**.
- Projekt 613122, Feld nicht gesetzt: „Einheitenliste im Exposé anzeigen“ war **aus**.

Der Feldname führt also in die Irre — das Feld steuert die Einheitenliste im Exposé. Für die Verlinkung auf der Landing Page liefert der Projekt-GET kein Feld; dieser Schalter bleibt Handarbeit in der Oberfläche.

Damit sind zwei der drei Projekt-Schalter aus dem How-to per API erreichbar: „Mietprojekt“ (`for_rent`) und „Einheitenliste im Exposé anzeigen“. Achtung bei Altbestand: Projekte aus früheren API-Läufen tragen `for_rent: false`, obwohl sie vermietet werden (gesehen an Projekt 613122).

### 48. Koordinaten: Der exakte `lng` kann verzögert ankommen — und Bestandskoordinaten sind kein Maßstab

Ergänzt Korrektur 34.

- **Ein Durchgang des Stufen-Tricks reicht nicht immer.** An Projekt **603710** zeigte der Einzel-GET nach dem ersten Durchgang noch den Zwischenwert `7.68`. Nach einer Sekunde Pause und einem zweiten Durchgang stand der exakte Wert da.
- **Der exakte Wert kann verzögert ankommen.** An Projekt **613378** stand im Einzel-GET nach zwei Durchgängen und auch 35 Sekunden später noch die vierstellige Stufe `7.6886`. Stunden später — ohne weiteren Schreibzugriff — stand dort der exakte Wert `7.688554`. Gespeichert wurde also richtig, nur das Gegenlesen hinkte. Korrektur 34 nennt den Einzel-GET als belastbaren Kanal; direkt nach der Schreibfolge ist auch er es nicht immer.
- **Regel im MCP:** Liegt der gelesene Wert innerhalb von 0,0001° (unter 10 m), gilt er als gesetzt und wird mit Hinweis gemeldet — keine Wiederholschleife. Größere Abweichungen bleiben ein Befund.
- **Straßengenaue Treffer von OpenStreetMap sind brauchbar.** Für „Am Scheid, 56204 Hillscheid“ (ohne Hausnummer) liefert Nominatim `50.4109007 / 7.6809298`. Die von Hand angelegte Einheit **6282819** (dieselbe Adresse; laut How-to zieht die Oberfläche die Koordinaten dort aus dem Adress-Dropdown) trägt `50.4109821 / 7.6811256` — unter 20 m Abstand. Ohne Hausnummer also setzen und als „nur straßengenau“ melden, nicht weglassen.
- **Bestandskoordinaten sind kein Maßstab.** Bestandsobjekt **5220033** (dieselbe Adresse) trug `50.4367 / 7.7047`. Die Rückwärtssuche zeigt dort einen Rettungspunkt im Wald bei Höhr-Grenzhausen, gut 3 km vom Gewerbegebiet entfernt. Der Vergleich mit diesem Wert ließ OpenStreetMap zunächst fälschlich ungenau aussehen. Am 10.11.2026 auf `50.4109821 / 7.6811256` korrigiert (Vorgabe Florian Brimmers). Vor so einem Vergleich prüfen, was am Punkt tatsächlich liegt.

### 49. Bilder: `image[title]` setzt den Bildtitel

Beim Multipart-Upload (Korrektur 6) nimmt Propstack ein zusätzliches Feld `image[title]` an; im GET der Einheit steht es als `title` am Bild. Belegt an Bild **56077346** (Einheit 6375202). Ohne `image[title]` wird der Dateiname zum Titel — im Bestand stehen deshalb Titel wie „Screenshot 2025-10-15 175444“ oder „img_p9“ (Einheit 4465616).

Das How-to verlangt benannte Bilder. **Regel:** jedes Bild mit sprechendem Titel hochladen („Außenansicht“, „Hallenfläche“, „Grundriss EG“), nie mit dem Dateinamen.

### 50. `unit_id` ist nicht global eindeutig

Korrektur 31 nennt `unit_id` „GLOBAL eindeutig“. Der Bestand widerlegt das:

- Einheit **6373955** (Projekt 613119) und Einheit **6373961** (Projekt 613122) tragen beide `unit_id` „Lager“ — beide am 09.11.2026 per API angelegt, im Abstand von 48 Sekunden.
- Einheit **6282819** (Projekt 604473) und Einheit **4465616** (Projekt 439534) tragen beide „Unit 1“.

Der 400er `Einheitennummer ist bereits vergeben` ist damit nicht bestritten, nur seine Reichweite: Über Projektgrenzen hinweg greift er nicht. Ob er je Projekt gilt oder nur für Objekte ohne Projekt, ist nicht gemessen.

**Regel:** Einheitennummern innerhalb eines Projekts eindeutig vergeben; projektlose Einzelobjekte weiter ohne `unit_id`. Für eine Dublettenprüfung taugt `unit_id` nur zusammen mit `project_id`.

### 51. Streng nach How-to — und für die Provisionsfelder gilt Korrektur 29 weiter

Vorgabe von Florian Brimmers (10.11.2026) nach einer Rückmeldung von Oguzhan: Anlage und Pflege halten sich streng an die Team-How-tos „Objekte in Propstack anlegen“ und „Projekte in Propstack anlegen“ (Drive: K & P → Allgemein → Knowledge Sharing → Propstack).

Für die Provisions-Custom-Felder hat Florian Brimmers am selben Tag entschieden: **Korrektur 29 ist richtig und gilt weiter.**

- `provision_extern` setzen — „Provisionsfrei“ bzw. „provisionspflichtig für den Mieter“. Der MCP leitet das Feld selbst aus der Provisionsaussage ab, auch wenn die Einheit die Provision vom Projekt übernimmt. Bei Kauf bleibt es leer.
- `provision_interne_notiz` setzen — Herkunft der Aussage und Sonderregeln, **kurz**: „Provisionsfrei bestätigt (Eigentümer, TT.MM.JJJJ)“, „Tischregel, gedeckelt bei 3 NKM“. Kein Bericht über den Lauf. Im MCP kommt der Wert aus dem Parameter `internal_commission`.
- Dieselbe Regelung steht laut How-to zusätzlich in den **Internen Notizen** (`note`, Korrektur 45). Der MCP schreibt beide Stellen aus der einen Angabe.
- `provision` und `provision_intern` nicht anfangen, `provisionspflichtig` nie setzen — unverändert.
- Zwischenstand, der nicht mehr gilt: Der MCP hatte `provision_interne_notiz` in Version 0.9.6 für einige Stunden gesperrt (Fehldeutung von „streng nach How-to“). Seit 0.9.8 ist das Feld wieder frei.

Das How-to nennt für provisionspflichtige Objekte nur den Provisionshinweis (die Staffel), keinen Text für die Außenprovision. Wechselt ein Objekt von „Provisionsfrei“ auf die Staffel, weist der MCP das ab, bis `courtage` mit angegeben ist — sonst stünde im Exposé weiter „Provisionsfrei“.

Was der MCP aus dem How-to außerdem erzwingt — Verstöße werden abgewiesen, nicht nur gemeldet:

- Überschrift und Projektname mit „(XX)“ = erste zwei Ziffern der PLZ, Format „Logistikhalle in (XX) Ort“
- Beschreibung, Lage und Ausstattung ohne Eigentümernamen (Korrektur 33), ohne die Straße des Objekts und ohne Preise
- Lage mit Entfernungen in km als Liste, nichts geschätzt; Ausstattung als Liste statt Komma-Kette
- Bilder nur mit Titel (Korrektur 49)

### 52. Offene Punkte — nicht gemessen

- GET **ohne** `?new=1`: ob `note` und `relationships` dort weiterhin fehlen (so wurden die Korrekturen 4 und 24 gemessen)
- Korrektur 47: der Weg zurück auf `false` ist ungetestet; `for_rent` ist in beide Richtungen getestet (Projekt 613378)
- Reichweite des `unit_id`-400ers (Korrektur 50)
- `title` bei Bildern über `remote_photo_url` und das Grundriss-Kennzeichen (`is_floorplan`) beim Upload
- `firing_types` (Oberfläche: „Wesentlicher Energieträger“) steht im GET mit `?new=1`; die zulässigen Werte sind unbekannt, das Feld bleibt Handarbeit
