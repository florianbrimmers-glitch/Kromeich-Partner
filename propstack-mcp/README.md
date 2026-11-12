# Propstack MCP Server – Kromeich GmbH

Remote-MCP-Server auf Cloudflare Workers. Über ihn arbeitet das Team aus Claude heraus mit Propstack.
Basis ist die Cloudflare-Vorlage [`remote-mcp-google-oauth`](https://github.com/cloudflare/ai/tree/main/demos/remote-mcp-google-oauth).

Live unter `https://propstack-mcp.kromeichpartner.workers.dev/mcp`, als Organisations-Connector in Claude eingetragen.

- **Phase 1 (abgenommen 09.10.2026):** Login über Google, Propstack-Nutzer-Abgleich, `whoami`.
- **Phase 2 (abgenommen 14.10.2026):** Lese-Tools und Audit-Log in D1.
- **Phase 3:** Kontakte und Objekte anlegen und ändern, mit Dublettenprüfung, Snapshot und Gegenlesen. Keine Lösch-Tools.

## Tools (Phase 2)

| Tool | Zweck | Propstack-Endpunkt (V1) |
|---|---|---|
| `whoami` | Angemeldeter Nutzer und Propstack-ID; zeigt auch, ob der zweite Schlüssel für Firmen und Verknüpfungen hinterlegt ist | – |
| `search_contacts` / `get_contact` | Kontakte suchen bzw. abrufen; `get_contact` zeigt auch die verknüpften Kontakte (Firma bzw. Mitarbeiter) | `GET /contacts`, `GET /contacts/:id?include=relationships` |
| `search_objects` / `get_object` | Objekte (Einheiten) suchen bzw. abrufen, inkl. Bildern mit Titel; mit `owner_contact_id` der ganze Bestand eines Eigentümers | `GET /units`, `GET /units/:id?new=1`, `GET /contacts/:id?include=relationships` |
| `get_project` | Projekt abrufen: Name, Überschrift, Unterzeile, Adresse, Koordinaten, Provision, Texte, Bilder mit Titel, Links, Einheiten | `GET /projects/:id`, `GET /units?project_id=` |
| `search_deals` | Deals suchen und abrufen (Kontakt, Objekt, Phase, Preis) | `GET /client_properties` |
| `pipeline_status` | Pipelines mit Phasen; je Phase Anzahl, Summe Preis, gewichteter Wert | `GET /deal_pipelines`, `GET /client_properties` |
| `list_tags` | Merkmale je Entität mit IDs | `GET /groups`, `GET /super_groups` |
| `list_fields` | Custom-Felder je Entität | `GET /custom_field_groups` |
| `list_reference` | Objekt-Status, Kontakt-Quellen, Nutzer, Projekte mit IDs | `GET /property_statuses`, `/contact_sources`, `/brokers`, `/projects` |
| `aggregate` | Zählen nach Dimension, mit allen Such-Filtern; Deals je Phase mit Summen | `with_meta=1&per=1` → `meta.total_count` |
| `dashboard_daten` | Daten für das Dashboard „Objektanlage & Prüfaufgaben“, ein Dokument je Aufruf (siehe eigener Abschnitt) | `GET /units?expand=1`, `GET /projects`, `GET /activities?item_type=reminder` |

Grundsätze:
- **Kürzen:** Antworten enthalten nur relevante Felder (`src/propstack/mappers.ts`). Bei Kontakten werden Ausweis- und Steuernummer, Geburtsdaten, Einkommen, Nationalität und der Kundenportal-Token **nie** ausgegeben.
- **Texte in der Einzelansicht vollständig** (v0.9.17, Ansage Florian vom 11.11.2026: „Warum ist nicht der gesamte Teil zu sehen?“): `get_object`, `get_project` und `get_contact` zeigen Beschreibung, Lage, Ausstattung, Sonstiges, interne Notiz, Warnhinweis und alle Custom-Felder (auch die Bemerkung) in voller Länge.
  - Vorher wurde nach festen Grenzen abgeschnitten: Custom-Felder nach 300 Zeichen, Lage/Ausstattung/interne Notiz nach 1.500, Beschreibung nach 2.000. Das war keine Vorgabe von Propstack, sondern eine zu eng ausgelegte Kürzungsregel.
  - Zwei Folgen: Interne Notiz und Bemerkung werden nur angehängt – das Neueste am Ende war nicht mehr lesbar (Gifhorn 003: die Bemerkung brach mitten in einem Eintrag vom 02.08.2026 ab). Und ein gekürzt gelesener Exposé-Text hätte beim Überarbeiten als Ganzes zurückgeschrieben werden können – der Rest wäre verloren gewesen.
  - Sicherheitsgrenze: 10.000 Zeichen je Feld (so viel, wie `update_object`/`update_project` in einem Aufruf schreiben dürfen). Darüber kommen Anfang und Ende mit dem Hinweis „NICHT vollständig … taugt nicht als Vorlage zum Überschreiben“. Still abgeschnitten wird nichts mehr.
  - Listen (Suchergebnisse, Deal-Liste) bleiben kurz.
  - Live gegengelesen am 11.11.2026: Gifhorn 003 (3154266) zeigt die Bemerkung jetzt bis zum letzten Eintrag („… angeglichen … 8.423 m² statt 8.801 m²“). Am Testobjekt 6375202 ist die ganze Kette des Rückgängig-Tests lesbar: angeglichen, angeglichen, „Sammeländerung vom 2026-11-11 (Plan 253d2e6y5t6j) rückgängig gemacht …“, angeglichen. Der erste Rückgängig-Lauf (v0.9.14) hat erkennbar keinen Vermerk hinterlassen – genau der Fehler, den v0.9.15 behoben hat.
- **Begrenzen:** max. 50 Treffer pro Seite und max. 45 Propstack-Anfragen pro Tool-Aufruf. `aggregate` bricht bei mehr als 40 Gruppen mit einem Hinweis ab, statt Propstack zu fluten.
- **Fehler:** Propstack-Fehler (401/403/404/429/5xx) kommen als verständliche Meldung zurück, bei 429 mit Retry und Backoff. Interna werden nicht ausgegeben.
- **Sichtbarkeit:** Alle Abfragen laufen über einen API-Key (Entscheidung Florian). Jeder angemeldete Nutzer sieht alles, was der Key sieht. Propstack-Sichtbarkeitsregeln je Nutzer oder Team gelten im Connector nicht.

- **Merkmale:** Propstack verknüpft mehrere Merkmale mit ODER. `tag_match: "all"` bildet die UND-Schnittmenge serverseitig (je Merkmal max. 5.000 Treffer). `aggregate` kann nur ODER und lehnt `all` ab.
- **Orte:** `query` ist Propstacks unscharfe Volltextsuche (findet z. B. auch „Leverkusener Str.“ in Mannheim). `city`/`zip_prefix` filtern exakt nach dem Ort- bzw. PLZ-Feld. Bei `status_ids` meldet `search_objects`, wie viele passende Objekte **keinen Status** haben.
- **Pipeline-Werte:** Deals ohne Phase dieser Pipeline (z. B. unqualifiziert) werden als `outside_stages` gemeldet. Hat kein Deal einen Preis, gibt es keine Summen statt „0 €“. Die Gewichtung nutzt die in Propstack hinterlegte Phasen-Wahrscheinlichkeit. Eine Phase „Absage“ sollte dort 0 % haben.

- **Suche nach Eigentümer** (Ansage Florian, 11.11.2026): `search_objects` mit `owner_contact_id` (Kontakt-ID der Firma) liefert den ganzen Bestand eines Eigentümers.
  - **Zwei Wege**, weil der Eigentümer oft nur am Projekt hängt (Hillwood am 11.11.: bei 36 von 46 Einheiten): die Einheiten, an denen der Kontakt selbst als Eigentümer verknüpft ist, **und** alle Einheiten der Projekte, an denen er als Eigentümer verknüpft ist. Quelle ist `GET /contacts/:id?include=relationships` (je Eintrag `internal_name`, `project`, `property`; Form per Diagnose geprüft).
  - Das Ergebnis ist nach Projekt und Einheit sortiert (Einzelobjekte zuletzt) und nennt unter `owner` die Projekte mit Zahl der Einheiten, `objects_total`, `objects_via_projects` und `objects_linked_directly`. Archivierte zählen in `objects_total` mit, erscheinen in der Liste aber nur mit `archived: "include"`.
  - Mit den übrigen Filtern kombinierbar (Status, Ort, `object_ids` …), nicht mit `tag_match: "all"`. `sort_by` wirkt hier nicht – das steht dann im Hinweis.
  - **Lieber kein Ergebnis als ein lückenhaftes:** Liefert Propstack die Verknüpfungen nicht oder lassen sich die Einheiten nicht vollständig laden, bricht die Suche mit einer Meldung ab. Bis 30 Projekte wird je Projekt abgefragt, darüber der Bestand einmal geladen und gefiltert.
  - **Grenze:** Gefunden wird nur, was als Eigentümer verknüpft ist. Datensätze ohne Verknüpfung (z. B. leere Altimporte) sieht die Suche nicht. Ein Kontakt, der nur Ansprechpartner ist, liefert nichts – der Hinweis nennt dann die anderen Rollen; Eigentümer ist meist der Firmenkontakt.
  - **Regel für Eigentümer-Updates (Florian, 11.11.2026):** Was der Eigentümer in seinem monatlichen Update nicht mehr nennt, ist nicht mehr verfügbar. Ablauf: Bestand mit `owner_contact_id` holen (alle Seiten), mit dem Update abgleichen, Nichtgenanntes mit `rented: true` und `status_id: 163676` abschließen. In Massenänderungen (`plan`) ist der Eigentümer-Filter bewusst nicht enthalten – dort die IDs angeben.
  - **Das Update gilt vor der Website (Entscheidung Florian, 11.11.2026):** Bei fast allen Eigentümern ist der Newsletter deutlich aktueller als die Website. Führt die Website einen Standort noch als verfügbar, der im Update fehlt, wird er trotzdem geschlossen; der Widerspruch gehört in die interne Notiz. Anlass: Langenselbold (im April-Update noch genannt) und Ellerau fehlen im Hillwood-Update November 2026, standen auf hillwood.de am 11.11. aber als „Available“. Beide wurden am 11.11. geschlossen, mit diesem Vermerk. Eine Gegenprobe gegen die Website hatte der Connector zwischenzeitlich verlangt (v0.9.12); sie ist wieder entfernt.
  - **Doppelgänger sind nicht „vermietet“:** Ein Datensatz, der einen im Update genannten Standort doppelt führt (Hillwood: „Gommern“ 3063999 = Projekt Möckern), wird nicht auf vermietet gesetzt – der Standort ist ja verfügbar –, sondern gemeldet und archiviert (Aufgabe 159665757 an Lena, 11.11.2026).
  - **Live erprobt am 11.11.2026 (Hillwood, Kontakt 17366591):** 64 Objekte in 17 Projekten, davon 59 über Projekte und 14 direkt verknüpft. Der Abgleich vom 10.11. über die Ortssuche hatte nur 46 Objekte in 13 Projekten erfasst – Oberhausen, Borsdorf, Langenselbold und Ellerau fehlten. Mit Statusfilter zunächst 53 in Vermarktung und 11 abgeschlossen; nach dem Schließen von Langenselbold und Ellerau 45 und 19.

Bewusste Lücken: Ein einzelner Deal per ID und die Kontakt-Status-Liste sind nur in der V2-Doku vorhanden. Deals werden daher über `search_deals` abgerufen, Kontakte lassen sich nicht nach Status gruppieren.

## Schreib-Tools (Phase 3)

| Tool | Zweck |
|---|---|
| `create_contact` | Kontakt (Person) anlegen; mit Firma wird automatisch der Firmen-Datensatz verknüpft und bei Bedarf angelegt |
| `update_contact` | Kontakt ändern, Merkmale hinzufügen/entfernen (taggen), Notiz **anhängen** |
| `create_company` | Firma als eigenen Datensatz anlegen (Firmen-Datensatz) – braucht den zweiten Propstack-Schlüssel |
| `link_contact_company` | Person mit ihrem Firmen-Datensatz verknüpfen (für vorhandene Kontakte und Zweifelsfälle) – braucht den zweiten Propstack-Schlüssel |
| `create_object` | Objekt anlegen – Einzelobjekt oder Einheit eines Projekts (übernimmt dann Adresse, Überschrift, Texte, Provision und Koordinaten vom Projekt) |
| `update_object` | Objekt ändern (Eckdaten, Status, Aktiv, Preise, Flächen, Ausstattungsfelder, Provision, Texte, Custom-Felder, Koordinaten) |

**Ablauf jedes Writes:**
1. Eingaben prüfen. Custom-Felder werden gegen `list_fields` validiert (Name, Typ, Auswahlwerte), sonst verwirft Propstack sie still.
2. Dublettenprüfung (siehe unten). Bei Treffer wird nichts geschrieben, Claude bekommt den vorhandenen Datensatz.
3. **Write-Log mit Snapshot** in D1 (`write_log`): Nutzer, Anfrage, bei Updates die vorherigen Werte der geänderten Felder. **Fail-closed:** Kann der Eintrag nicht geschrieben werden, wird nichts nach Propstack geschrieben.
4. Schreiben. Bei 429 gibt es einen Retry. Bei 5xx/Timeout gibt es **keinen** Retry, die Meldung lautet „Status unklar, bitte prüfen“.
5. **Gegenlesen:** Der Datensatz wird neu geladen und jedes angefragte Feld verglichen. Was Propstack nicht übernommen hat, steht als `not_applied` im Ergebnis und im Write-Log (`done_with_gaps`).

**Regeln (Entscheidungen Florian):**
- Betreuer ist **immer** der angemeldete Nutzer. Propstack zeigt als Ersteller/Bearbeiter den API-Key-Inhaber. Wer es wirklich war, steht im Write-Log und in der Herkunftsnotiz („Angelegt über Claude (Propstack MCP) von …“).
- Kontakt-Dubletten: gleiche **persönliche E-Mail** blockiert immer. Ein Override ist dort nicht möglich, weil Propstack Kontakte per E-Mail zusammenführt und sonst den vorhandenen überschreiben würde. Ohne persönliche E-Mail blockieren gleiche **Mobilnummer** und **Name + Firma**. **Festnetz**, gleicher Name ohne Firma und **generische Adressen** (info@, vertrieb@ …) erzeugen nur Warnungen. **Systemadressen** (noreply …) werden als „vermutlich kein echter Kontakt“ gemeldet.
- Objekt-Dubletten: Adresse (Straße/Nr./PLZ normalisiert) **oder** Geokoordinaten ≤ 30 m **plus** Vermarktungsart **plus** Einheit blockieren. Gleiche Adresse mit anderer Vermarktungsart oder Einheit ist nur ein Hinweis.
- **Override** (`allow_duplicate_reason`): nur mit Begründung (≥ 15 Zeichen). Die Begründung wird im Write-Log protokolliert.
- **Testdaten:** `test: true` setzt das Merkmal `MCP-TEST`. Fehlt es, legt der Connector es einmalig an. Löschen kann nur Florian manuell.
- Notizen werden bei Updates nur ergänzt (mit Datum und Nutzer), nie ersetzt.

**Kontakte: Live-Abnahme am 12.11.2026 (v0.10.1 → Korrekturen in v0.10.2).** Anlass: Nach Objekten und Dashboard sind die Kontakte dran (Ansage Florian). Geprüft wurde an Testkontakten mit dem Merkmal `MCP-TEST`, so wie der E-Mail-Scan Kontakte anlegt.
- **Bestanden:**
  - `create_contact` mit allen Feldern (Anrede, Titel, Name, Firma, Position, E-Mail, Festnetz, Mobil, Adresse, Quelle, Merkmal, Notiz): Beim Zurücklesen stand jeder Wert richtig, Betreuer war der angemeldete Nutzer, die Herkunftsnotiz hing an.
  - Dubletten: gleiche E-Mail blockiert auch mit Begründung; gleiche Mobilnummer blockiert, egal wie sie geschrieben ist (`0171 3920055` gegen `+49 171 39200-55`).
  - `update_contact`: Felder, Merkmal dazu und weg, Notiz angehängt; dieselbe Notiz ein zweites Mal wird nicht doppelt angehängt. Die E-Mail eines anderen Kontakts wird abgewiesen, ein Merkmal, das es nicht gibt, steht unter `not_applied`, ein Betreuer, den es nicht gibt, wird von Propstack abgelehnt.
  - Suche nach Merkmal (`tag_match: all`, `exclude_tag_ids`), Telefonnummer und Name; Auswertung nach Betreuer.
  - Sammeländerung an vier Testkontakten (Merkmal dazu, Merkmal weg) samt `undo_plan`: Danach hatte jeder Kontakt wieder genau seine alten Merkmale.
- **Befund 1 – übersehene Dublette bei akademischem Titel (behoben in v0.10.2).** „max MCP-Testkontakt Abnahme“ bei derselben Firma wurde neben „Dr. Max MCP-Testkontakt Abnahme“ angelegt, ohne Blockade und ohne Warnung.
  - Ursache: Propstack stellt dem Anzeigenamen den Titel voran („Dr. Max …“). Der Vergleich lief gegen diesen Anzeigenamen.
  - Jetzt zählt Vor- und Nachname des vorhandenen Kontakts; vorangestellte Titel (Dr., Prof., Dipl.-Ing. …) werden auf beiden Seiten ignoriert.
  - Die Tests hatten das nicht gezeigt, weil ihre Beispielzeilen keinen Titel trugen. Sie sind jetzt so aufgebaut, wie Propstack die Zeilen liefert.
- **Befund 2 – Kontaktstatus und Kontakt-Quelle nehmen jede Zahl an (behoben in v0.10.2).** `client_status_id: 999999999` und `source_id: 999999999` standen danach am Kontakt; der Connector meldete beides als geändert. Propstack prüft diese Verweise nicht.
  - Erkennbar ist ein ungültiger Verweis beim Gegenlesen: Nur zu einer gültigen ID liefert Propstack das zugehörige Objekt mit (`client_source: {id, name}`), zu einer ungültigen nichts.
  - Der Connector nimmt einen solchen Wert jetzt sofort zurück: Er stellt den vorherigen Wert wieder her – oder leert das Feld, wenn schon der vorherige ungültig war – und meldet ihn unter `not_applied` („… gibt es in Propstack nicht – nicht übernommen“). Das gilt auch beim Anlegen und in Sammeländerungen.
  - Offen bleibt: Für den Kontaktstatus gibt es in der V1-Schnittstelle keine Liste. Gültige Werte kann Claude deshalb nicht nachschlagen, und in diesem Konto ist kein gültiger Status bekannt.
- **Kleinigkeit, behoben:** Wird eine Änderung als Dublette abgewiesen, heißt es im Ergebnis `updated: false` statt `created: false`.
- **Live-Nachtest mit v0.10.2 (12.11.2026, 18:24 Uhr) – bestanden:**
  - „Max MCP-Testkontakt Abnahme“ bei „MCP-TEST Musterfirma“ wird jetzt abgewiesen; genannt werden beide vorhandenen Kontakte, der mit Titel (38363861) und der ohne (38363864).
  - Ein Status, den es nicht gibt, wird zurückgenommen: Der Wert stand danach nicht mehr am Kontakt, gemeldet unter `not_applied`. Der zuvor testweise gesetzte ungültige Status ist damit ebenfalls weg.
  - Eine Quelle, die es nicht gibt: Am Kontakt mit gültiger Quelle (Homepage) stand danach wieder „Homepage“ („vorheriger Wert wiederhergestellt“); am Kontakt mit ungültiger Quelle ist das Feld jetzt leer.
- **Aus dem Nachtest, behoben in v0.10.3:** Wurde alles zurückgenommen, meldete das Ergebnis trotzdem `updated: true` bei leerem `changed`. Jetzt `updated: false`. In Sammeländerungen zählt ein solcher Kontakt als „mit Lücken“ und steht unter den Problemen; das Zurücknehmen ist im Abfragebudget eingerechnet. `get_contact` zeigt außerdem den Namen der Quelle (`source`), nicht nur die Nummer.
- **Was der Connector bei Kontakten nicht kann** (Abgleich mit dem täglichen Import `src/` und dem Skill `email-kontakt-scan`):
  - ~~Firmen-Datensätze anlegen und Personen mit ihrer Firma verknüpfen.~~ Gebaut in v0.11.0, siehe nächster Abschnitt.
  - Newsletter-Gruppen (Mailchimp) setzen – der tägliche Import ordnet jeden Kontakt einer Gruppe zu.
  - Die Aktivitäten eines Kontakts lesen (Notizen, Aufgaben, Termine) oder eine Gesprächsnotiz als Aktivität anlegen; möglich ist nur das Anhängen an das Notizfeld.
  - Kontaktstatus nachschlagen, DSGVO-Status und Newsletter-Kennzeichen ändern, Kontakte archivieren.
  - Custom-Felder für Kontakte gibt es in diesem Konto nicht (`list_fields` liefert keine); Kontakt-Quellen gibt es nur sechs, alle Portale.
  - Was davon gebaut wird, entscheidet Florian.

**Firmen und Verknüpfungen: `create_company` und `link_contact_company` (v0.11.0, 12.11.2026).** Anlass: Der tägliche Kontakt-Import legt zu jedem neuen Kontakt die Firma als eigenen Datensatz an und verknüpft beide. Kontakte, die über Claude entstehen, bekamen das nicht – die Firma stand nur als Text am Kontakt.
- **Zweiter Schlüssel.** Beides geht nur über die V2-Schnittstelle von Propstack. Der Server braucht dafür das Secret `PROPSTACK_API_KEY_V2` (gesetzt von Florian am 12.11.2026 im Cloudflare-Dashboard). Fehlt es, sind nur diese zwei Tools gesperrt – mit klarer Meldung, alles andere läuft weiter. `whoami` zeigt unter `firmen_und_verknuepfungen`, ob der Schlüssel hinterlegt ist. Verweigert Propstack den Zugriff, nennt die Meldung den zweiten Schlüssel.
- **Verknüpft wird automatisch (Entscheidung Florian, 12.11.2026, ab v0.12.0):** „Die Firmenverknüpfung soll bitte immer gesetzt werden“ – wie in den Import-Jobs, ohne dass jemand etwas tun muss. Zuerst (v0.11.x) gab `create_contact` nur einen Hinweis; das ist abgelöst.
  - `create_contact` mit Firma: Nach dem Anlegen der Person sucht der Connector den Firmen-Datensatz und verknüpft. Gibt es keinen, legt er ihn an – mit der Geschäftsadresse des Kontakts und, bei `test: true`, dem Merkmal `MCP-TEST` – und verknüpft dann. Das Ergebnis steht unter `company_link` (`linked`, `company`, `company_created`, `label`).
  - **Eine Ausnahme, damit keine Firmen-Dubletten entstehen:** Gibt es keinen gleichnamigen, aber einen ähnlich benannten Firmen-Datensatz, wird keine neue Firma angelegt. Passen mehrere, wird nur verknüpft, wenn genau einer exakt so heißt. In beiden Fällen nennt das Ergebnis die Kandidaten (`similar`, `candidates`), entschieden wird mit `link_contact_company`. Hintergrund: „Goodman“ (36103370) hat der tägliche Import am 02.09.2026 neben „Goodman Germany GmbH“ (17366550) angelegt – die Signatur war gut lesbar, sie nannte nur die Kurzform.
  - Der Kontakt ist in jedem Fall angelegt. Scheitert etwas an der Firma (Suche, Anlegen, Verknüpfen), steht das unter `company_link` samt dem Schritt zum Nachholen; ein Fehler des Tools wird daraus nicht.
  - Im Write-Log stehen Kontakt, Firma und Verknüpfung als einzelne Einträge unter `create_contact`.
  - Dafür ist die Beschreibung von `create_contact` ergänzt, die von `link_contact_company` ebenfalls. **Beide Tools müssen einmal neu erlaubt werden** (5c). `update_contact` verknüpft nicht automatisch: Bei einem Firmenwechsel müsste die alte Verknüpfung gelöst werden, und das kann der Connector nicht.
- **`get_contact` zeigt die verknüpften Kontakte (ab v0.12.0):** `linked_contacts` – an der Firma die Personen, an der Person die Firma. `this_contact_is` sagt, was der abgerufene Kontakt für den genannten ist („Mitarbeiter“ bzw. „Firma“). Gelesen wird mit derselben einen Anfrage wie bisher (`GET /contacts/:id?include=relationships`); bei mehr als 50 wird gekürzt und die Gesamtzahl genannt. Die Tool-Definition von `get_contact` ist unverändert.
- **`create_company`** legt den Datensatz in einem Aufruf an (`POST /v2/clients` mit `commercial: true`, Name im Feld `company`, kein Nachname – sonst zeigt Propstack „X (X)“). Betreuer ist der angemeldete Nutzer, die Herkunftsnotiz hängt an, `test: true` setzt `MCP-TEST`. Danach wird über V1 gegengelesen. Ist der Datensatz nicht als Firma gekennzeichnet, wird das einmal einzeln nachgesetzt; bleibt es dabei, steht es unter `not_applied`. Eine E-Mail-Adresse bekommt der Firmen-Datensatz bewusst nicht: Propstack führt Kontakte über die E-Mail zusammen, eine Person mit derselben Adresse würde den Firmen-Datensatz überschreiben.
- **Dublettenprüfung für Firmen.** Gleicher Name blockiert; Groß-/Kleinschreibung, Punkte und Rechtsform (GmbH, AG, GmbH & Co. KG …) zählen nicht. Ein nur längerer oder kürzerer Name („Goodman“ / „Goodman Germany GmbH“) ist ein Hinweis. Personen zählen nie als Firma, auch nicht, wenn sie fälschlich so markiert sind (erkennbar am Vornamen).
  - Befund beim Nachprüfen (nur lesend, 12.11.2026): Die Propstack-Suche verlangt **jedes Wort** der Eingabe. „Goodman Germany AG“ und „Goodman Germany GmbH & Co. KG“ finden „Goodman Germany GmbH“ nicht. Mit einer einzigen Suche – so sucht der tägliche Import – wäre die Dublette unsichtbar geblieben.
  - Deshalb sucht der Connector dreimal: mit dem ganzen Namen, ohne Rechtsform und mit dem ersten Wort allein. Die dritte Suche bringt kürzer benannte Datensätze als Hinweis ans Licht – im Konto stehen zum Beispiel „Goodman Germany GmbH“ (17366550) und „Goodman“ (36103370) nebeneinander.
  - Grenze: Tippfehler und andere Punktsetzung im ersten Wort („Goodmann“, „L.I.T.“ gegen „LIT“) findet die Suche nicht.
- **`link_contact_company`** verknüpft eine Person mit einem Firmen-Datensatz (`POST /v2/relationships`, `internal_name: associate`, `client_id` = Person, `related_client_id` = Firma, `name: "Firma"`). Vorher wird geprüft: `company_id` ist wirklich ein Firmen-Datensatz, `contact_id` eine Person, beide sind verschieden und noch nicht verknüpft. Gibt es die Verknüpfung schon, wird nichts geschrieben (`already_linked`). Danach wird gegengelesen: Steht die Verknüpfung nicht in Propstack, heißt es `linked: false`, lässt sie sich nicht lesen, `linked: "nicht prüfbar"` – nie ein angenommener Erfolg. Steht am Kontakt eine andere Firma als Text, kommt eine Warnung; verknüpft wird trotzdem.
- **Befund: Der tägliche Import beschriftet Verknüpfungen verkehrt herum.** Nur lesend geprüft am 12.11.2026 an allen 5.149 Kontakt-Verknüpfungen des Kontos.
  - Propstack führt jede Verknüpfung als zwei Zeilen: die angelegte und die Gegenrichtung, die es selbst ergänzt. `name` bezeichnet den verknüpften Kontakt aus Sicht von `client_id`. In der Oberfläche angelegte Verknüpfungen lauten: Person → Firma „Firma“, Firma → Person „Mitarbeiter“.
  - Der tägliche Import (`src/propstack_client.py`) schickt für die Person `name: "Mitarbeiter"`. Ergebnis: Am Kontakt steht die Firma als „Mitarbeiter“, an der Firma die Person als „Firma“. Betroffen sind rund 220 Verknüpfungen (Stichprobe 6 von 6 bestätigt; Beispiel vom 12.11.: Kontakt 38337398).
  - Richtig macht es `personalkarussell_handler` (`name: "Firma"`); so sehen rund 2.000 Verknüpfungen aus. Der Connector macht es ebenso. Trifft `link_contact_company` auf eine vertauscht beschriftete Verknüpfung, gilt sie als vorhanden und wird als vertauscht gemeldet (`label`, `warnings`).
  - Nicht Teil dieses Auftrags: den Import korrigieren (ein Wort) und die rund 220 vorhandenen Verknüpfungen richtigstellen. Das entscheidet Florian.
- **Was nicht geht:** Verknüpfungen lösen oder umbenennen (kein Lösch-Tool, harte Regel). Firma mit Firma verknüpfen (Mutter/Tochter). Andere Bezeichnungen als „Firma“ vergeben. Die Verknüpfungs-Kategorie setzt der Connector nicht: In der Oberfläche angelegte Verknüpfungen tragen sie auf beiden Seiten, per Schnittstelle angelegte nur an der Gegenrichtung – ein sichtbarer Unterschied ist nicht bekannt.
- **Fehlertexte:** Die V2-Schnittstelle meldet Fehler unter `details` (V1 unter `errors`). Beides wird durchgereicht.
- **Live-Abnahme mit v0.11.0 (12.11.2026, 19:33–19:36 Uhr) – bestanden, 16 von 16 Schritten.** An Testdaten (`MCP-TEST`), ausgeführt in einer frischen Sitzung; den Endzustand hat Claude danach unabhängig über die Propstack-Schnittstelle gegengelesen.
  - `whoami` meldet den zweiten Schlüssel als hinterlegt. Lesen und Schreiben auf Kontakte und Verknüpfungen funktionieren mit ihm.
  - `create_company` „MCP-TEST Musterfirma GmbH“ mit Adresse, Telefon, Website und Notiz: angelegt als 38366588, in einem Aufruf. In Propstack als Firma gekennzeichnet, Name im Feld Firma, kein Vor- oder Nachname, jedes Feld wie gesendet, Betreuer = Nutzer, Merkmal `MCP-TEST`, Herkunftsnotiz. Das Nachsetzen der Kennzeichnung war nicht nötig.
  - Dubletten: derselbe Name, „MCP-TEST Musterfirma AG“ und „mcp-test musterfirma“ wurden abgewiesen, jeweils mit Verweis auf 38366588 – auch unmittelbar nach dem Anlegen (die Suche findet neue Datensätze sofort).
  - `link_contact_company` Person 38363861 → Firma: `linked: true`, `label: "Firma"`. In Propstack stehen genau die zwei Zeilen einer in der Oberfläche angelegten Verknüpfung: Person → Firma „Firma“ (8001117), Firma → Person „Mitarbeiter“ mit Kategorie 5787 (8001118). Der zweite Aufruf meldet `already_linked` und legt nichts an.
  - Fehlbedienung: Firma als `contact_id`, Person als `company_id`, zweimal derselbe Datensatz, unbekannte ID – jeweils klare Meldung, nichts geschrieben.
  - `create_contact` mit der Firma „MCP-TEST Musterfirma GmbH“ nennt den Firmen-Datensatz und den nächsten Schritt; mit einer Firma, die es nicht gibt, kommt der Hinweis „keinen eindeutigen Firmen-Datensatz“. Beide neuen Personen ließen sich verknüpfen – die mit abweichendem Firmentext mit Warnung.
  - Endzustand: Firma 38366588 mit drei verknüpften Personen (38363861, 38366712, 38366717); je Person genau eine Zeile „Firma“, an der Firma drei Zeilen „Mitarbeiter“.
  - Live nicht ausgelöst und nur durch Tests abgedeckt: die Antwort 422 beim Verknüpfen (die Vorprüfung greift vorher) und das Nachsetzen der Firmen-Kennzeichnung.
- **Aus der Abnahme, behoben in v0.11.1:** `get_contact` zeigte die Website nicht – am Firmen-Datensatz ließ sich also nicht nachlesen, was `create_company` gesetzt hatte. Sie steht jetzt als `office_url` in der Ausgabe.

**Objekte – Regeln aus dem Notion-Feld-Mapping („Propstack API – Feld-Mapping“, Korrekturen) und dem Skill `propstack-expose-workflow`:**
- **Einzel-PUTs:** `rs_category`, `total_floor_space`, `industrial_area`, `hall_height`, `floor_load`, `broker_id`, `rented` und der Status verwirft Propstack im POST und in PUTs mit mehreren Feldern still (HTTP 200). Diese Felder werden nach dem Anlegen bzw. Ändern **einzeln** geschrieben. Ein fehlgeschlagener Einzel-PUT bricht die übrigen nicht ab und steht als `write_errors` im Ergebnis.
- **Gegenlesen:** Der Einzel-GET liefert Flächen, Kategorie, Hallenhöhe, Status-ID usw. gar nicht. Gelesen wird deshalb über `GET /v1/units?expand=1&per=100&property_ids[]=ID`, Status über `status.id`, Betreuer über `broker.id`. Frisch angelegte Objekte fehlen dort kurz, deshalb gibt es Retries nach 1,5 s und 4 s. Felder, die kein Kanal zurückliefert, stehen als `not_verifiable` im Ergebnis (nicht als Fehler). `get_object` nutzt denselben Weg.
- **Nicht angeboten:** `object_type` (leitet Propstack aus `rs_type` ab), `total_rent`, `property_space_value` (berechnet). Zu den Koordinaten siehe unten.
- **Preise (Entscheidung Florian, 15.10.2026):** Interne Preise (`intern_mietpreis_hallenflache` / `_buro` / `_mezzanine`) dürfen immer gesetzt werden. **Öffentliche Preise** (`price` nur bei BUY, `base_rent` nur bei RENT, Custom-Felder `mietpreis_*`) nur, wenn der Nutzer sie ausdrücklich ansagt oder auf Nachfrage bestätigt. Dann setzt Claude `public_price_confirmed: true`, und die Bestätigung steht im Write-Log. Ohne Bestätigung weist das Tool ab und fordert zur Nachfrage auf. Ohne öffentlichen Preis gilt `price_on_inquiry: true`, auch bei Kaufobjekten.
- **Interne Notizen** (How-to: Link, Mandat, Provisionsregelung, Projektname des Entwicklers) stehen im Feld `note` („Notiz“). Das Feld ist über `GET ?new=1` lesbar und trägt bei Bestandsobjekten genau diese Inhalte (live 09.11., Objekt 5220033). Die Notion-Seite hielt es für nicht schreibbar, weil der alte GET es nicht zeigt. Beim Ändern wird angehängt, nie ersetzt, und nur wenn der vorhandene Text lesbar ist. Übernimmt Propstack die Notiz nicht, setzt das Tool sie einzeln nach; hält sie auch dann nicht, landet der Text im Custom-Feld `bemerkung` und das Ergebnis meldet es (`internal_note_hint`).
- **Feld „Bemerkung“ = nur Änderungsprotokoll** (Entscheidung Florian, 10.11.2026: „Das Feld lesen wir quasi nie“). Dort stehen der Eintrag „Angelegt über Claude …“ und Änderungsvermerke (`bemerkung_append`: was geändert wurde und warum). Nichts, was jemand lesen muss: Offene Punkte stehen in der Prüfaufgabe und im Tool-Ergebnis, Fachliches in der internen Notiz. Hält Propstack eine interne Notiz nicht, weicht der Connector **nicht** mehr in die Bemerkung aus – der Text steht dann im Ergebnis und in der Prüfaufgabe zum Eintragen von Hand. Beschreibung, Lage, Ausstattung und Sonstiges sind **exposé-sichtbar**.
- **Custom-Felder:** Zahlen nur als nackte Zahl mit Dezimalpunkt. Text wie `"10,5"` wird abgewiesen, ebenso m²-Werte mit drei Nachkommastellen (Tausenderpunkt-Verdacht). Auswahlfelder werden per Name oder Option-ID angenommen und als **Option-ID** gesendet. **Gesperrt:** `provisionspflichtig`, `provision`, `provision_intern` (nur `null`), `mezzanineflache` (Einheit Euro, stattdessen `mezzanineflache_gesamt`/`_verfugbar`), `bemerkung` (nur über `bemerkung_append`). `list_fields` zeigt Einheit, Option-IDs und Sperren.
- **Flächen gespiegelt:** Exposé und Teamansicht lesen die Flächen-Custom-Felder. Aus `industrial_area`, `usable_floor_space`, `total_floor_space` und `hall_height` füllt das Tool deshalb automatisch `lagerflache`/`_gesamt`, `buroflache`/`_gesamt`, `gebaudeflache_gesamt` und `hallenhohe`. Ist das Objekt nicht vermietet, kommen auch die `*_verfugbar`-Felder dazu, bei „Preis auf Anfrage“ außerdem `preisangabe`. Explizit übergebene Custom-Felder haben Vorrang. Bei Updates werden fehlende Varianten auch an Altobjekten nachgezogen.
- **Vermietet** (`rented: true`, Team-Prozess): Das Tool setzt automatisch `free_from` „vermietet“, `status_logistik` und `aktiv` auf Inaktiv und die verfügbaren Flächen auf „X m² (vermietet)“. `status_logistik`/`aktiv` stehen **nur bei Status Vermarktung oder Reserviert** (und nicht vermietet) auf Aktiv, sonst auf Inaktiv; sie werden beim Anlegen und bei jedem Status- oder Vermietungswechsel neu gesetzt. Grund: Objekte in Akquise oder Vorbereitung dürfen nicht in Automatisierungen wie Exposéversand oder Webseite landen. Testobjekte bekommen zusätzlich `kein_automatischer_exposeversand` = Ja. Den Status (163676 Abgeschlossen) setzt man weiterhin separat.
- **Flächen:** nie 0 m². `total_floor_space` = Halle + Mezzanine, ohne Büro (Regel seit 13.08.2026).
- **„Gebäudefläche gesamt“ ist ebenfalls ohne Büro** (Entscheidung Florian, 11.11.2026): `gebaudeflache_gesamt` und `gebaudeflache_verfugbar` tragen denselben Wert wie die Gesamtfläche – so spiegelt sie das Tool schon immer. Befund am Hillwood-Bestand: Bei 42 von 46 Einheiten stand dort seit der Bereinigung im August noch Halle + Mezzanine + Büro.
  - **Angleichen** (v0.9.14): `update_object` mit `align_building_area: true` setzt `gebaudeflache_gesamt` auf die gespeicherte Gesamtfläche und hängt einen Änderungsvermerk mit altem und neuem Wert an. `gebaudeflache_verfugbar` zieht nur mit, wo es schon befüllt und das Objekt nicht vermietet ist – leere Felder bleiben leer, damit nichts Neues ins Exposé kommt.
  - **Nur auf eine stimmige Gesamtfläche:** Passt sie nicht zu Hallenfläche + Mezzanine, ist die Mezzanine nicht lesbar oder fehlt die Gesamtfläche, wird abgewiesen. Berichtigen und Angleichen gehen in einem Aufruf (`total_floor_space: <Halle + Mezzanine>` dazu).
  - **Für viele Objekte:** `plan` mit `changes: { align_building_area: true }` – jedes Objekt bekommt seinen eigenen Wert. Unstimmige Objekte bleiben unverändert und stehen unter `problems`. Solche Pläne, die nur Custom-Felder anfassen, schaffen sechs statt vier Objekte je `apply_plan`-Aufruf (6 statt 10 Propstack-Anfragen je Objekt).
  - **Live am 11.11.2026:** Die 42 Hillwood-Einheiten sind angeglichen – eine einzeln, 41 über den Plan `6t426a4d4a3w` in sieben Etappen (je sechs Objekte, keine Lücken, nichts abgewiesen). Stichproben Gifhorn 003 (8.423 statt 8.801 m²) und Düsseldorf Unit 2 (10.352 statt 10.775 m²); ein leeres „Gebäudefläche verfügbar“ blieb leer. Rückgängig bis 18.11.2026 mit `undo_plan` – das gilt für die 41 Einheiten des Plans. Die einzeln angeglichene Einheit 5766192 gehört nicht zum Plan; ihr Stand vorher steht im Write-Log.
- **Gesamtfläche wird immer gerechnet** (Ansage Florian, 10.11.2026; Anlass: im Mileway-Lauf vom 09.11. stand bei elf Einheiten das Büro in der Gesamtfläche):
  - **Anlegen:** `total_floor_space` = `industrial_area` + `mezzanine_area`. Der Parameter soll wegbleiben. Kommt er mit einem anderen Wert, wird abgewiesen und nichts angelegt; der richtige Wert darf mitkommen, weil ältere Tool-Listen ihn noch schicken.
  - **Ändern:** Sobald ein Aufruf Hallenfläche oder Mezzanine anfasst, rechnet das Tool neu – aus dem neuen Wert des Aufrufs und dem gespeicherten der anderen Fläche (Mezzanine aus `mezzanineflache_gesamt`, auch in der Schreibweise „1.050 m²“). Die gespiegelten Felder `gebaudeflache_*` ziehen mit.
  - **Altbestand:** Wird an einem Objekt nur etwas anderes geändert, bleiben die Flächen unberührt. Passt die gespeicherte Gesamtfläche nicht zur Rechnung, steht das als Hinweis im Ergebnis; mit `total_floor_space: <gerechneter Wert>` lässt sie sich sofort berichtigen.
  - **Ohne Hallenfläche** (z. B. reine Bürofläche) gilt die Regel nicht.
  - **Mezzanine nicht lesbar:** Steht im Feld ein Text statt einer Zahl (etwa „ca. 1.000 m²“), rechnet das Tool nicht, sondern weist die Flächenänderung ab und verlangt `mezzanine_area`. Sonst ginge die Mezzanine in der Summe verloren.
  - **Undo einer Massenänderung:** Die Gesamtfläche wird nicht zurückgeschrieben, sondern aus den zurückgesetzten Flächen neu gerechnet. Stand vorher ein Wert, der nicht zur Rechnung passt, meldet das Undo das.
- **„Bezug“ folgt „Verfügbar ab“** (Ansage Florian, 11.11.2026; Anlass: beim Hillwood-Update vom 10.11. war „Verfügbar ab“ neu, „Bezug“ stand noch auf dem alten Wert):
  - Im Bestand hat `free_from` zwei Begleiter in den Custom-Feldern: `bezug` („Bezug“, Text, derselbe Wortlaut) und `bezug_datum` („Bezug (Datum)“, Datum). Muster aus dem Mileway-Lauf: „ab 01.07.2027“ → Bezug „ab 01.07.2027“, Datum 01.07.2027; „sofort“, „auf Anfrage“, „ab 2027“ → Bezug gleich, Datum leer.
  - **Anlegen und Ändern:** Nennt der Aufruf `free_from`, setzt das Tool `bezug` auf denselben Text und `bezug_datum` auf das Datum, wenn der Text **genau ein** Datum nennt (TT.MM.JJJJ, TT.MM.JJ oder JJJJ-MM-TT). Sonst wird ein vorhandenes Datum **geleert** – ein altes Datum neben „Q3 2027“ wäre falsch. Zwei verschiedene Daten oder ein unmögliches (31.02.) zählen als kein Datum.
  - **Altbestand:** Auch ein unverändertes `free_from` zieht nach – so lässt sich ein Objekt mit richtigem „Verfügbar ab“ und leerem „Bezug“ berichtigen. Ein Aufruf ohne `free_from` lässt beide Felder in Ruhe.
  - **Vermietet:** `rented: true` setzt mit `free_from` „vermietet“ auch `bezug` „vermietet“ und leert das Datum. Bei `rented: false` ohne `free_from` meldet das Tool, dass „vermietet“ noch dasteht.
  - **Ausdrücklich gesetzt:** `custom_fields.bezug` bzw. `bezug_datum` haben wie alle ausdrücklichen Custom-Felder Vorrang. Weicht „Bezug“ danach von „Verfügbar ab“ ab, steht das als Hinweis im Ergebnis. So lässt sich „Bezug“ auch nachziehen, ohne `free_from` anzufassen: Stimmt der Wert nicht mit dem gespeicherten „Verfügbar ab“ überein, meldet das Tool es.
  - Live erprobt am 11.11.2026 am Testobjekt 6375202 (unverändertes `free_from` zieht nach und leert ein altes Datum; Datum aus „ab 01.04.2027“; vermietet und wieder verfügbar). Danach an zwölf Hillwood-Einheiten vom 10.11. nachgezogen (Düsseldorf, Westerkappeln, Falkensee) – ohne Abweichungshinweis.
- **Notizen werden nicht doppelt angehängt** (Ansage Florian, 11.11.2026; Anlass: beim Hillwood-Lauf gingen Aufrufe durch einen Neustart verloren und mussten wiederholt werden):
  - **Notizen** (`internal_note` samt `source_link`, `mandate`, `internal_commission`, `developer_project_name` am Objekt; `note_append` an Projekt und Kontakt) halten Sachverhalte fest. Steht derselbe Text schon da – egal von wann und von wem –, wird er nicht noch einmal angehängt. Von mehreren Teilen kommt nur der neue dazu.
  - **Bemerkung** (`bemerkung_append`) ist ein Änderungsprotokoll: Derselbe Vermerk an einem späteren Tag ist ein neuer Eintrag. Doppelt ist er nur unter dem Stempel desselben Tages und Nutzers – genau der Fall „Aufruf wiederholt“.
  - **Ausnahme (v0.9.16):** Vermerke, die der Connector selbst nur bei einer echten Änderung erzeugt (Angleichen der Gebäudefläche, Rückgängigmachen einer Sammeländerung), gelten nie als doppelt. Anlass: angleichen → rückgängig → am selben Tag erneut angleichen hinterließ beim zweiten Mal keinen Vermerk mehr, das Protokoll endete mit „rückgängig gemacht“, obwohl der Wert wieder angeglichen war. Ein wiederholter Aufruf erzeugt diese Vermerke ohnehin nicht, weil sich dann nichts mehr ändert.
  - Verglichen werden **ganze, aufeinanderfolgende Zeilen** (Leerraum egal). Ein kurzer Text, der nur Teil einer längeren Zeile ist, gilt nicht als vorhanden.
  - Das Ergebnis nennt Übersprungenes unter `already_present`. Ist sonst nichts zu ändern, wird nichts geschrieben.
  - Live erprobt am 11.11.2026 am Testobjekt 6375202: Der wiederholte, gleiche Aufruf schrieb nichts mehr (`updated: false`, beide Notizen unter `already_present`).
- **Live-Abnahme „Anlegen“ am 11.11.2026 (v0.9.17).** Anlass: Seit dem 09.11. abends war in Propstack kein Objekt mehr angelegt worden, während `create_object` viermal umgebaut wurde (strenge How-to-Prüfung, Provisionsfelder, gerechnete Gesamtfläche, Bezug). Getestet an der neuen Einheit 6396742 im MCP-TEST-Projekt 603710:
  - Ein Regelverstoß (Ausstattung als Komma-Kette) wurde mit klarer Meldung abgewiesen; es entstand nichts.
  - Die gültige Anlage lief ohne `not_applied` und ohne `write_errors`. Zurückgelesen: Gesamtfläche 3.400 m² = Halle 3.000 + Mezzanine 400 (Büro 250 m² getrennt), „Gebäudefläche gesamt“ 3.400 m², „Bezug“ „ab 01.07.2027“ mit „Bezug (Datum)“ 01.07.2027, Provision vom Projekt samt „Provision extern“, Bemerkung nur mit dem Anlage-Vermerk, interne Notiz im Feld „Notiz“, Merkmal MCP-TEST, Koordinaten vom Projekt.
  - `add_images` (Bild per Link) lief dabei zum ersten Mal live: Bild 56305980 kam mit Titel am Objekt an.
  - Befund: Ohne `status_id` entsteht das Objekt **ohne Status**, und das Ergebnis weist nicht darauf hin. Objekte ohne Status fallen aus Statusfiltern. Entscheidung offen: Standard-Status oder Hinweis im Ergebnis.
  - Einordnung: Über den Connector ist bis zum 11.11.2026 **kein echtes Objekt** angelegt worden, nur Testobjekte. Der letzte echte Lauf (Mileway, 09.11.) lief über den Skill `propstack-expose-workflow`. Nicht live geprüft sind Kaufobjekte und öffentliche Preise.
- **Koordinaten (Entscheidung Florian, 16.10.; korrigiert 09.11.):** Reihenfolge: angegebene Werte > Koordinaten des Projekts (Einheit mit gleicher Adresse) > was Propstack selbst ermittelt > OpenStreetMap (Nominatim) aus der Adresse. Das Tool meldet die Genauigkeit ehrlich: „Hausnummer“ nur, wenn OpenStreetMap die Hausnummer wirklich kennt, sonst „Straße“. Straßengenaue Treffer werden **gesetzt** und in der Prüfaufgabe zum Nachsehen markiert. Geschrieben wird mit dem Trick aus Notion-Korrektur 34: erst `lat`, dann `lng` mit 1, 2, 3, 4 Nachkommastellen und zuletzt exakt. Die Kontrolle läuft per Einzel-GET. An den Kartendienst geht nur die Adresse, mit neutralem Client-Namen.
- **Eigentümer und Ansprechpartner an Einheiten:** `create_object` mit `owner_contact_id` und `contact_person_id`, nachträglich über `set_project_owner` mit `object_id` (und `role`). Die Prüfung erfolgt wie bei Projekten über die Gegenprobe.
- **Feldpaare:** `beleuchtung_halle` und `beleuchtung` werden gegenseitig gespiegelt, weil Exposé und Teamansicht sie getrennt lesen.
- **Prüfaufgaben mit Umlauten:** Die ASCII-Regel aus dem Skill galt für den alten curl-Weg.
- `floor_load` (Bodentragkraft) in **kg/m²**. Propstack hängt die Einheit selbst an, 5 t/m² entsprechen also 5000.
- `unit_id` (Einheitennummer, z. B. „Unit 1“) ist bei Einheiten im Projekt Pflicht. Bei Einzelobjekten ohne Projekt weglassen.
- Nicht enthalten: Firmenkontakte (brauchen Propstack-V2), Deals anlegen/ändern, Löschen.
- **Weitere Schreibwege neben dem Connector** (Stand 10.11.2026, Entscheidung Florian):
  - Der Skill `propstack-expose-workflow` schreibt mit eigenen API-Schlüsseln direkt nach Propstack, ohne die Regeln dieses Connectors. Über ihn lief der Mileway-Lauf vom 09.11.2026. Er wird deaktiviert, sobald der Connector im Team läuft.
  - Die Skills `email-kontakt-scan` (legt Kontakte an) und `propstack-pipeline-report` (liest Deals) nutzen ebenfalls eigene Schlüssel. Sie sollen in einer weiteren Version über den Connector laufen. Der Kontakt-Scan sucht vor dem Anlegen selbst nach dem Kontakt; die Dublettenregeln des Connectors (Mobilnummer, Name + Firma) und das Write-Log gelten für ihn bis dahin nicht.
  - Solange diese Skills bestehen, bleiben ihre Schlüssel gültig; getauscht werden können sie erst nach der Umstellung.

## Phase 3b: Projekte, Eigentümer, Bilder, Prüfaufgabe (Entscheidung Florian, 15.10.2026)

| Tool | Zweck |
|---|---|
| `create_project` | Projekt (Standort mit mindestens zwei Einheiten) anlegen, mit Eigentümer, Ansprechpartner, interner Notiz, Provision. Dublettenprüfung über die Adresse |
| `update_project` | Projekt ändern: Name, Überschrift, Unterzeile, Adresse, Provision, Exposé-Texte, Adresse ausblenden, Koordinaten |
| `set_project_owner` | Kontakt (eigener Shop) mit einem Projekt oder einer Einheit verknüpfen – als Eigentümer oder mit `role: contact_person` als Ansprechpartner |
| `add_images` | Bilder per öffentlicher https-URL an Objekt oder Projekt hängen, mit Titeln |
| `image_upload_url` | Einmal-Adresse für den Upload von Bilddateien, mit Titeln |
| `create_task` | Aufgabe an einen Propstack-Nutzer anlegen, z. B. eine Entscheidungsvorlage – mit verknüpften Objekten, Projekten und Kontakten |

- **Projekt:** Wrapper `project`, `country` DEU, Betreuer = Nutzer. Was Propstack im Sammel-Request still verwirft, wird erkannt und **einzeln nachgesetzt**. Offene Punkte gehen über `review_notes` in die Prüfaufgabe. Testprojekte erkennt man am Namenspräfix `MCP-TEST`, weil Projekte keine Merkmale haben.
- **Interne Notiz am Projekt (`note`):** Propstack speichert das Feld – in der Oberfläche unter „Interne Notizen“ bestätigt (Projekt 613378, 10.11.) –, liefert es im GET aber **nicht zurück**, auch nicht mit `new=1`. Die Notion-Seite hielt es deshalb für nicht schreibbar. Folge: Beim Anlegen wird die Notiz geschrieben, ohne dass das Tool sie gegenlesen kann; das gilt als bekannt und erscheint nicht als Befund. **Nachträglich anhängen geht nicht** – ohne den alten Text würde „anhängen“ ihn ersetzen. `update_project` lehnt `note_append` deshalb ab, solange der GET die Notiz nicht liefert.
- **Write-Log bei Koordinaten:** `update_object` und `update_project` sichern auch die bisherigen Koordinaten im Snapshot.
- **Eigentümer und Ansprechpartner:** `PUT /projects/{id}` bzw. `PUT /units/{id}` mit `relationships_attributes` (`related_client_id`, nicht `client_id`): Eigentümer mit `internal_name: owner`, Ansprechpartner als verknüpfter Kontakt mit `internal_name: partner` – **ohne Bezeichnung**, so wie von Hand hinterlegte Kontakte (live 09.11. an Herford 6324578). Nur wenn Propstack eine Bezeichnung verlangt, wird mit `name: Ansprechpartner` wiederholt.
  - **Prüfung:** Der Einzel-GET von Einheit und Projekt liefert `relationships` (`internal_name`, `client_id`). Das Tool liest dort gegen. Ist der Kontakt in dieser Rolle schon verknüpft, schreibt es nichts.
  - **Ersatzweg**, falls die Liste die neue Verknüpfung nicht zeigt: die Gegenprobe. Das Tool sendet denselben Aufruf ein zweites Mal; Propstack lehnt Doppelte mit „bereits mit dem Kontakt verbunden“ ab, und genau das bestätigt die Verknüpfung. Ist die Antwort nicht eindeutig, meldet das Tool „nicht prüfbar“ und vermerkt es im Write-Log.
  - „Existiert bereits“ zählt als Erfolg. Bei einem fremden Shop kommt eine klare Meldung.
- **Bilder per URL (`add_images`):** Nur öffentliche https-URLs (`remote_photo_url`). Jede URL wird vorher geprüft (erreichbar, `Content-Type: image/*`, mit neutralem User-Agent), sonst entstehen leere Bildobjekte, die man nur in der UI löschen kann. Das erste Bild eines Objekts wird Titelbild. `titles` benennt die Bilder (How-to: „müssen in Propstack benannt werden“).
- **Prüfaufgabe automatisch** nach `create_project` und `create_object`:
  - an Lena (254958), bei `test: true` an den Nutzer selbst;
  - `is_reminder: true`, fällig am nächsten Werktag 9:00;
  - Inhalt: Link, Ersteller, Eigentümer und Ansprechpartner, Koordinaten mit Genauigkeit, Lücken (`not_applied`/`not_verifiable`), Fehler, was laut How-to fehlt, Texthinweise, offene Punkte, die interne Notiz des Projekts zur Kontrolle und die Schritte, die nur in Propstack selbst gehen;
  - Einheiten im Projekt bekommen eine eigene Aufgabe nur bei Problemen – sonst deckt die Aufgabe des Projekts sie ab.
  - Schlägt sie fehl, bleibt der Datensatz angelegt; im Ergebnis steht `review_task.error`.
- **Bilder als Datei** (`image_upload_url`, für Claude Code und Cowork):
  - Das Tool liefert eine Einmal-Adresse `…/upload/images/<token>`: 15 Minuten gültig, an Nutzer und genau ein Objekt/Projekt gebunden, Token mit 256 Bit, liegt in KV.
  - Die Sitzung lädt per `curl -F "image[photo]=@bild.jpg" -F "title=Außenansicht" <adresse>` hoch – je Bild ein `title` in derselben Reihenfolge. Der Worker reicht Datei und Titel per Multipart (`image[photo]`, `image[title]`) an Propstack weiter, mit Write-Log (`tool = image_upload`) und Audit.
  - Aus dem Dateinamen wird bewusst **kein** Titel gemacht: Dateien aus Exposés heißen oft nach dem Eigentümer, und der Titel steht im Exposé.
  - Erlaubt sind JPEG, PNG und WebP, erkannt an den Datei-Bytes. Max. 15 MB je Bild, max. 20 Bilder je Adresse.
  - Ist eine Datei ungültig, wird nichts hochgeladen. Der Propstack-Key verlässt den Server nicht.
- **Aufgabe von Hand (`create_task`, Ansage Florian 10.11.2026):** für Entscheidungsvorlagen und Prüfbitten zu vorhandenen Datensätzen. Es ist ein fest definiertes Tool mit acht Parametern – kein freier API-Aufruf.
  - **Nur Anlegen.** Ändern und Löschen bietet der Connector nicht (harte Regel). Deshalb wird alles **vor** dem Schreiben geprüft: Der Empfänger muss ein Propstack-Nutzer mit aktivem Zugang sein, die Fälligkeit darf nicht in der Vergangenheit liegen, und jedes verknüpfte Objekt, Projekt und jeder Kontakt muss existieren. Fehlt etwas, entsteht keine Aufgabe.
  - **Empfänger und Fälligkeit:** ohne `assignee_id` an den Nutzer selbst, ohne `due_date` am nächsten Werktag 9:00. Die Uhrzeit geht mit deutschem Zeitzonen-Versatz an Propstack (`…T09:00:00+01:00`), damit dort nichts geraten wird.
  - **Text:** reiner Text, kein HTML. Je Absatz ein `<p>`, Zeilenumbrüche als `<br>`; Aufzählungen bleiben Zeilen mit „- “. Mehr Formatierung ist in Propstack nicht erprobt. Am Ende steht automatisch „Angelegt über Claude (Propstack MCP) von <Name> am <Datum>.“ – in Propstack erscheint als Ersteller sonst nur der Nutzer des API-Keys.
  - **Gegenlesen:** Nach dem Anlegen liest das Tool die Aufgabe über `GET /v1/tasks/:id` zurück und vergleicht Titel, Empfänger, Fälligkeit, Text und Verknüpfungen. Abweichungen stehen in `not_applied`, Unprüfbares in `not_verifiable` (dann mit den Feldnamen der Antwort, ohne Werte).
  - **Test:** `test: true` setzt `[MCP-TEST]` vor den Titel und schickt die Aufgabe an den Nutzer selbst.
  - Write-Log (`tool = create_task`, fail-closed) und Audit wie bei allen Schreib-Tools.
  - **Live erprobt am 10.11.2026:** Probeaufgabe 159643420 und die erste echte Aufgabe 159643494 (Entscheidungsvorlage an Lena, drei Objekte und drei Projekte verknüpft). Das Gegenlesen hat Titel, Empfänger, Fälligkeit, Text und Verknüpfungen bestätigt, ohne `not_applied` und ohne `not_verifiable`.
- **API-Key:** Der Key „MCP-Server“ braucht in Propstack zusätzlich Schreibrechte für Projekte, Relationships, Bilder und Aufgaben – und zum Gegenlesen das Leserecht für Aufgaben.
- **`update_project`** (Entscheidung Florian, 16.10.) arbeitet wie `update_object`: Es schreibt nur echte Änderungen, legt vorher einen Snapshot ins Write-Log und liest danach zurück. Was Propstack still verwirft, wird einzeln nachgesetzt. Koordinaten nur zusammen (lat+lng) und mit dem Stufen-Trick, bei Adressänderung mit Dublettenprüfung.
- **Nicht enthalten:** Dokumente (PDF), Post in #objekte, Löschen. Im reinen claude.ai-Chat ohne Code-Ausführung gibt es keinen Datei-Upload, dort nur `add_images` per URL.

## Team-How-to im Server (v0.9.0, 09.11.2026)

Quelle: „Objekte in Propstack anlegen“ und „Projekte in Propstack anlegen“ (Drive: K & P → Allgemein → Knowledge Sharing → Propstack), die Notion-Wissensdatenbank und die Rückmeldung von Oguzhan (24.10.). Abgeglichen mit von Hand angelegten Datensätzen (Herford 6324578, Hillscheid 6282819). Die Regeln stehen im Code (`src/propstack/howto.ts`), damit jede Claude-Sitzung nach demselben Muster schreibt – unabhängig vom Skill.

| How-to | Im Connector |
|---|---|
| Überschrift „Logistikhalle in (2-stellige PLZ) Ort“ | Fehlendes oder falsches „(XX)“ → abgewiesen (Objekt-Überschrift, Projektname und Projekt-Überschrift). Projekt: `title` = `name`; weicht die Überschrift ab → Hinweis. Eine vom Projekt übernommene Alt-Überschrift wird nur gemeldet |
| Aktiv, „wenn wir das Objekt anbieten können“ | `active`. Ohne Angabe: Aktiv nur bei Status Vermarktung/Reserviert und nicht vermietet |
| Interne Notizen: Link, Alleinmandat, Mietpreise, Provisionsregelung, Projektname des Entwicklers | `source_link`, `mandate`, `internal_commission`, `developer_project_name`; Mietpreise am Objekt in `internal_rent_hall` / `_office` / `_mezzanine` (interne Felder), am Projekt in `internal_rents`; Freitext in `internal_note`. Ziel: an Projekt und Objekt das Feld `note` („Notiz“) |
| Ansprechpartner: Eigentümer ausfüllen, Kontakt hinterlegen | `owner_contact_id` und `contact_person_id` beim Anlegen, nachträglich `set_project_owner` (mit `role`) |
| Adresse aus dem Dropdown → Koordinaten | Koordinaten werden ermittelt, geschrieben und gegengelesen (siehe oben). Einheiten übernehmen Adresse und Koordinaten des Projekts |
| Provision ja/nein mit Standardtexten | `commission`: `provisionsfrei` oder `staffel` (die vier Sätze der Staffel). Feste Regeln je Eigentümer stehen in der Tool-Beschreibung |
| Wichtige Flächenfelder | Eigene Parameter, auf die Felder gelegt, die das Team in Propstack sieht: `hall_divisible_from` → `lagerflache_teilbar_ab`, `office_divisible_from` → `buroflache_teilbar_ab`, `mezzanine_area` → `mezzanineflache_gesamt`/`_verfugbar`, `mezzanine_divisible_from`, `car_parking` → `stellplatze_verfugbar`, `truck_parking` → `lkw_stellplatze_gesamt`, `dock_doors` → `ramepntore`, `ground_level_doors` → `anzahl_rampentore_2`, `wgk`, `lighting` → `beleuchtung` + `beleuchtung_halle`, `sprinkler` → `sprinkleranlage`. Gesamtfläche = Halle + Mezzanine wird beim Anlegen berechnet |
| Energie: Heizungsart Halle, Zertifizierung, Baujahr | `heating`, `certification`, `construction_year`. **Wesentlicher Energieträger** ist noch nicht möglich (API-Feld unbekannt) → steht als Handgriff in der Prüfaufgabe |
| Objektbeschreibung als Fließtext, **ohne Eigentümernamen** | Text wird geprüft: voller Eigentümername, Preis oder die Straße des Objekts im Text → abgewiesen. Namensteil → Hinweis. Straße in der Überschrift → Hinweis |
| Lage: Entfernungen in km, stichpunktartig | Ohne km → abgewiesen. Mehrere Entfernungen als Fließtext-Kette → abgewiesen. Die Meldung sagt ausdrücklich: nichts schätzen, sonst Lage weglassen und als offenen Punkt melden |
| Ausstattung: alles, was in kein Feld passt | Muss eine Aufzählung sein (eine Zeile je Punkt). Komma-Kette → abgewiesen |
| Einheiten: Beschreibung, Lage, Ausstattung, Provision vom Projekt | Werden beim Anlegen der Einheit vom Projekt übernommen, ebenso Überschrift, Adresse und Koordinaten |
| „Daten auf Einheiten übertragen“ nach Projektänderung | `update_project` nennt den Weg (`units_hint`): `plan` mit `object_filter {project_id}` und Texten/Provision – mit Vorschau und Undo |
| Bilder benennen, keine Schriftzüge, Grundrisse kennzeichnen | Titel je Bild ist Pflicht (`title` beim Upload bzw. `titles`); ohne Titel oder mit Dateinamen als Titel wird nichts hochgeladen. `get_object`/`get_project` zeigen die Titel. Grundriss-Kennzeichen und Schriftzüge bleiben Handarbeit |
| „Mietprojekt“ | `marketing_type: RENT` setzt `for_rent` beim Anlegen; nachträglich `update_project` mit `for_rent` (ältere Läufe haben den Schalter nicht gesetzt, Befund 10.11. an Projekt 613122) |
| „Einheitenliste im Exposé anzeigen“ | API-Feld `show_units_on_landing_page` (aus der Diagnose, nicht in der Doku). Abgleich mit der Oberfläche am 10.11.2026 in beide Richtungen: Projekt 613378 (Feld `true`) – dieser Schalter war an, der andere aus; Projekt 613122 (Feld nicht gesetzt) – dieser Schalter war aus. `create_project` setzt ihn standardmäßig, `update_project` nachträglich |
| „Auf der Landing Page auf die jeweiligen Einheiten verlinken“ | Per API nicht erreichbar – der Projekt-GET liefert dafür kein Feld. Steht als Schritt in `ui_steps` und in der Prüfaufgabe |

- **Streng nach How-to (Vorgabe Oguzhan/Florian, 10.11.2026):** Wo das How-to ein Format oder ein Verbot nennt, weist der Connector ab statt zu warnen: Überschrift, Eigentümername, Adresse und Preise im Text, Lage als km-Liste, Ausstattung als Liste, Bildtitel. Wo Daten schlicht fehlen können (Eigentümer, Flächen, Baujahr …), meldet er die Lücke.
- **Provisionsfelder nach Feld-Mapping, Korrektur 29** (Entscheidung Florian, 10.11.2026: „Hier ist die Notion-Regel richtig“). Die Provision gehört vollständig auf jede Einheit: `provision_extern` setzt der Connector selbst aus der Provisionsaussage („Provisionsfrei“ bzw. „provisionspflichtig für den Mieter“; auch wenn die Provision vom Projekt übernommen ist; nicht bei Kauf). `provision_interne_notiz` kommt aus `internal_commission` – Herkunft der Aussage und Sonderregeln, kurz; dieselbe Zeile steht laut How-to auch in der internen Notiz. `provision` und `provision_intern` bleiben gesperrt (im Bestand ungenutzt – nicht anfangen), `provisionspflichtig` sowieso. v0.9.6 hatte `provision_interne_notiz` gesperrt; das war eine Fehldeutung von „streng nach How-to“. Wechsel auf die Staffel, während die Außenprovision noch „Provisionsfrei“ lautet, wird abgewiesen, bis `courtage` mit angegeben ist – das How-to nennt für provisionspflichtige Objekte keinen Text dafür.
- **Was fehlt, wird gemeldet:** Jedes Anlegen liefert `howto_not_provided` (laut How-to wichtig, aber nicht angegeben) und `text_warnings`. Beides steht auch in der Prüfaufgabe.
- **Projekt oder Einzelobjekt:** Projekt nur bei mindestens zwei getrennt vermietbaren Einheiten, im Zweifel Einzelobjekt (Wissensdatenbank, Abschnitt 3).
- **`contact_person_id` schreibt nicht mehr ins Custom-Feld `ansprechpartner_vermietung`** (v0.8.0 tat das mit der Kontakt-ID). Von Hand angelegte Objekte nutzen das Feld nicht; der Ansprechpartner ist jetzt eine echte Verknüpfung.
- **Diagnose:** `get_object` und `get_project` mit `diagnose: "field_names"` listen die Feldnamen mit Bezeichnung und Typ, die Propstack liefert – ohne Werte. Mit `diagnose_key` (z. B. `"energie"`) nur die passenden Felder, dafür tiefer aufgeschlüsselt. Damit lassen sich Felder aus der Oberfläche finden, die die Doku nicht nennt. Befund 09.11.: Einheiten liefern `note` („Notiz“), `relationships` (verknüpfte Kontakte) und `firing_types` („Wesentlicher Energieträger“). Seit 11.11. auch am Kontakt: `get_contact` mit `diagnose: "field_names"` liest den Kontakt samt Verknüpfungen (`include=owned_properties,relationships`) und zeigt unter `links` die Feldnamen aller Einträge und die Ausprägungen der Art-Felder (`internal_name`, `*_type`) – keine Namen, keine IDs. `get_project` mit `diagnose: "list_channel"` zeigt, was die Projektliste liefert (einfach und mit `expand=1`: Anzahl, Dauer, Größe, Feldnamen, Verknüpfungen). Anlass: die Suche nach Eigentümer – bei 36 von 46 Hillwood-Einheiten hängt der Eigentümer nur am Projekt, nicht an der Einheit.
- **`get_object`** zeigt deshalb auch `internal_note`, `contacts` (Eigentümer/Ansprechpartner) und `energy_source`.
- **Koordinaten mit zweitem Durchgang:** Haftet der Wert nach dem Stufen-Trick nicht, liest das Tool nach einer Sekunde neu und wiederholt einmal (live am Projekt beobachtet).
- **Gegenlesen hinkt beim Längengrad:** Der exakte Wert kommt bei Propstack teils verzögert an. Live 10.11., Projekt 613378: direkt nach dem Schreiben und 35 Sekunden später stand im Einzel-GET noch die vierstellige Stufe (`7.6886`), Stunden später – ohne weiteren Schreibzugriff – der exakte Wert (`7.688554`). Vier Stellen sind rund 7 m. Alles innerhalb von 0,0001° gilt deshalb als gesetzt; das Ergebnis nennt die gelesenen Werte und sagt, dass noch der Zwischenwert zu lesen war. Größere Abweichungen bleiben ein Befund (`not_applied: lat/lng`). Die Erklärung aus v0.9.5 („Propstack speichert nur vier Stellen“) war falsch.
- **Nachsichtige IDs:** Ziffernfolgen als Text (`"123"`) werden bei IDs und Anzahlen angenommen. Clients mit veralteter Tool-Liste schicken neue Parameter als Text.
- **Notion-Seite „Feld-Mapping“ (10.11.2026):** Die überholten Stellen der Seite tragen Kurzhinweise (`note` ist schreibbar, `relationships` ist mit `?new=1` lesbar, `unit_id` ist nicht global eindeutig, Provisionsregelungen gehören in die Internen Notizen, Landing-Page-Schalter per API, Bildtitel, Gegenlesen der Koordinaten). Der ausführliche Abschnitt „Korrekturen 10.11.2026“ liegt fertig in [`docs/notion-feldmapping-korrekturen-2026-11-10.md`](docs/notion-feldmapping-korrekturen-2026-11-10.md). Er ist noch nicht eingetragen, weil der Notion-Workspace sein Kontingent an freien Blöcken verbraucht hat.
- **Mileway-Lauf vom 09.11.2026:** Korrekturliste, Stand der Umsetzung und die Vorschläge für Lage, Ausstattung und Beschreibung liegen in [`docs/mileway-korrektur-2026-11/`](docs/mileway-korrektur-2026-11/). Paket A ist umgesetzt, Paket B wartet auf Freigabe.

## Phase 4: Massenänderungen (plan → apply_plan → undo_plan)

| Tool | Zweck |
|---|---|
| `plan` | Auswahl (ID-Liste oder Filter wie bei den Such-Tools) und Änderung festlegen. **Ändert nichts in Propstack.** Liefert `plan_id`, Anzahl und Vorschau |
| `apply_plan` | Bestätigten Plan ausführen, in Etappen |
| `undo_plan` | Ausgeführten Plan rückgängig machen |

- **Änderungen:** Kontakte: Merkmale hinzufügen/entfernen, Betreuer, Quelle, Kontaktstatus, Custom-Felder. Objekte: Status, vermietet, Provision (`commission`, `courtage`, `courtage_note`), Exposé-Texte (Beschreibung, Lage, Ausstattung), Custom-Felder. Texte werden schon beim Planen gegen die Team-Regeln geprüft. **Keine Merkmale an Objekten** (Entscheidung Florian, 16.10.). Live geprüft: Propstack ignoriert Merkmal-Updates an Objekten still (`sub_group_ids` und leere `group_ids`). Das Test-Merkmal MCP-TEST wird nur beim Anlegen gesetzt, das funktioniert.
- **Regeln:**
  - Höchstens 500 Datensätze je Plan.
  - Die Plan-ID verfällt 10 Minuten nach dem Planen (Spezifikation). Danach muss neu geplant werden, weil sich der Bestand geändert haben kann.
  - Nur wer geplant hat, darf ausführen. Claude muss die Vorschau zeigen und eine ausdrückliche Bestätigung einholen.
- **Gleiche Regeln wie Einzeländerungen:** `apply_plan` schreibt jeden Datensatz über `update_contact` bzw. `update_object`. Es gelten dieselben Prüfungen (Einzel-PUTs, Spiegelung, Preissperre, aktiv/inaktiv, Gegenlesen). Jeder Datensatz bekommt einen eigenen Write-Log-Eintrag (`tool = apply_plan:<id>`).
- **Etappen:** Pro Tool-Aufruf höchstens ~40 Propstack-Requests. Das reicht für etwa 13 Kontakte oder 4–8 Objekte. Claude ruft `apply_plan` erneut auf, bis `remaining = 0`. Bei unklarem Propstack-Status (5xx/Timeout/429) hält der Lauf an. Mit Workers Paid lässt sich das Budget erhöhen (`BULK_REQUEST_BUDGET`).
- **Rückgängig:** 7 Tage lang (Entscheidung Florian), jeder Nutzer darf es auslösen.
  - Je Datensatz wird der gesicherte Stand vorher hergestellt, als Rohwert und nicht als Anzeigewert.
  - Felder, die seitdem jemand anders geändert hat, werden **übersprungen** und gemeldet. Trägt ein Feld den alten Wert schon wieder (z. B. wenn ein unterbrochener Lauf wiederholt wird), zählt der Datensatz als rückgängig gemacht.
  - Merkmale werden nur zurückgenommen, wenn der Plan sie wirklich gesetzt bzw. entfernt hat.
  - Bemerkungen werden nie zurückgesetzt. Hat die Sammeländerung dort einen Vermerk hinterlassen (Angleichen der Gebäudefläche), hängt `undo_plan` einen eigenen an, z. B. „Sammeländerung vom 2026-11-11 (Plan 4g6k0b5j301o) rückgängig gemacht: Gebäudefläche gesamt wieder 3.000 m².“ So stimmt das Änderungsprotokoll wieder; die Plan-ID führt zum Eintrag im Write-Log.
  - **Live-Befund 11.11.2026 (v0.9.15):** Das Rückgängigmachen der Angleich-Funktion war bis dahin nur in den automatischen Tests bewiesen. Der erste Live-Test (Testobjekt 6375202) stellte die Werte richtig her, meldete aber „0 rückgängig, 1 teilweise“ samt „Problem“, weil die stehen gebliebene Bemerkung als übersprungenes Feld zählte, und schloss mit dem Satz, jemand anders habe das Feld geändert. In der Bemerkung stand weiter „angeglichen“, obwohl der Wert zurück war. Seit v0.9.15 zählt ein solcher Datensatz als rückgängig gemacht, der Abschlusssatz nennt nur noch, was zutrifft, und die Bemerkung bekommt den Vermerk über das Rückgängigmachen.
  - **Nachtest live am 11.11.2026 mit v0.9.16** (Testobjekt 6375202, Plan `253d2e6y5t6j`): angleichen und rückgängig machen am selben Tag wie der erste Lauf, mit wortgleichem Angleich-Vermerk. Ergebnis: `undone: 1`, kein `partial`, keine `problems`, Abschlusssatz zutreffend; beide Flächenfelder wieder 3.000 m². Der Vermerk über das Rückgängigmachen steht in der Bemerkung – geprüft über einen wortgleichen `bemerkung_append`, den der Connector als `already_present` meldete. Dass er überhaupt geschrieben wurde, belegt zugleich die Korrektur aus v0.9.16: Der zweite, wortgleiche Angleich-Vermerk wurde angehängt, sonst hätte es beim Rückgängigmachen nichts zu vermerken gegeben. Danach wieder auf 2.500 m² angeglichen.
  - **Befund aus dem Nachtest, behoben in v0.9.17:** `get_object` zeigte von langen Texten nur den Anfang (Bemerkung und andere Custom-Felder 300 Zeichen, interne Notiz 1.500) – das Neueste am Ende war über den Connector nicht lesbar. Seitdem kommen die Texte in der Einzelansicht vollständig (siehe „Texte in der Einzelansicht vollständig“ bei den Lese-Tools).
- **Speicher:** D1-Tabellen `bulk_plan` und `bulk_item` (`migrations/0003_bulk_plans.sql`), Löschfrist 12 Monate per Cron.

Write-Log auswerten:

```sql
SELECT ts, user_email, tool, entity, entity_id, status, not_applied, override_reason FROM write_log ORDER BY id DESC LIMIT 20;
```

## Dashboard-Daten: `dashboard_daten` (v0.10.0, 12.11.2026; Abruf „alles“ seit v0.10.1)

**Anlass:** Das Dashboard „Objektanlage & Prüfaufgaben“ (claude.ai-Artifact, Quelltext `weekly_report/dashboard/dashboard.html`) darf Propstack nicht selbst abfragen. Bisher holte eine tägliche Routine die Daten mit `python -m weekly_report.dashboard_export` – dafür lagen Propstack-Keys in der Claude-Umgebung. Jetzt holt der Connector die Daten; der Key bleibt im Worker. Routine und Dashboard stellt die Sitzung um, die das Dashboard betreut.

**Eingabe:**
- `dokument`: `meta/stand`, `meta/projekte`, `wochen/<JJJJ-KWnn>` oder `pruefung/teil-<nn>` – oder `alles` für alle Dokumente eines Stands in einer Antwort (seit v0.10.1)
- `tage` (Standard 91, höchstens 91) und `broker_ids` (Standard `[254958]`, der Sitz, auf dem die Prüfaufgaben gepflegt werden)
- `stand` (Zusatz zur Vorgabe, optional): der Wert `aktualisiert` aus `meta/stand` bzw. `stand` aus der Antwort auf `alles`. Dann kommt die Antwort genau aus diesem Stand oder ein Fehler – nie aus einem anderen.

**Ausgabe:** genau das Dokument, das `baue_dokumente()` im bisherigen Export erzeugt – gleiche Feldnamen in gleicher Reihenfolge, Wochenschlüssel = ISO-Woche in Berliner Zeit, 400 Aufgaben je Teil, gleiche Regel für die Art („Pruefung“ → „Prüfung“). Kompaktes JSON ohne Hülle und ohne Zusatzfelder. Solange der Stand nicht fertig ist, kommt stattdessen `{"fortsetzen": true, "phase": …, "fortschritt": …}`.

**Aufbau in Etappen.** Ein Stand braucht rund 114 Propstack-Abfragen, ein Tool-Aufruf darf höchstens 45 (Cloudflare Free: 50 Subrequests):

| Schritt | Abfrage | Anzahl am 12.11.2026 |
|---|---|---|
| Einheiten im Fenster | `GET /units?expand=1&created_at_from=…&created_at_to=…`, 100 je Seite | 4 |
| Projektliste | `GET /projects`, 200 je Seite | 3 |
| Anlagedatum je Projekt | `GET /units?project_id=…&expand=1&sort_by=created_at&order=asc&per=1` | 104 |
| Aufgaben der Prüfer | `GET /activities?item_type=reminder&broker_id=…&sort_by=updated_at&order=desc`, 200 je Seite | 3 |

- Je Aufruf höchstens 40 Abfragen und 20 Sekunden; danach wird der Fortschritt gespeichert und `fortsetzen: true` gemeldet.
  - Live über den Connector (12.11.2026): **drei Aufrufe** mit 40, 40 und 34 Abfragen; der erste dauerte unter fünf Sekunden. Vom Worker aus antwortet Propstack schnell, dort greift die Abfragegrenze.
  - Aus der Entwicklungsumgebung (langsamerer Netzweg, rund eine halbe Sekunde je Abfrage) waren es vier Aufrufe mit 22, 36, 39 und 17 Abfragen, zusammen 72 Sekunden – dort greift die Zeitgrenze.
- Einheiten werden zu je 100 gelesen statt wie im Export zu 200: Mit `expand=1` wiegt eine Einheit rund 33 KB, 200 wären 6,8 MB je Antwort. Die Reihenfolge ist bei beiden Seitengrößen dieselbe (live geprüft).
- Der Zeitpunkt des Stands (`aktualisiert`) ist der Beginn des Aufbaus. Einheiten, die während des Aufbaus entstehen, gehören zum nächsten Stand.
- Meldet Propstack mittendrin einen Fehler, ist der Fortschritt gespeichert; der nächste Aufruf macht dort weiter. Bei einem Serverfehler (5xx) oder Netzproblem versucht es der Connector vorher einmal selbst erneut, bei 429 wartet der Client wie überall.

**Zwischenspeicher (D1, `migrations/0004_dashboard_cache.sql`):** `dashboard_stand` (Fortschritt und Zustand je Stand), `dashboard_teil` (Rohdaten während des Aufbaus, auf die nötigen Felder gekürzt), `dashboard_dokument` (fertige Dokumente).
- Ein fertiger Stand gilt **30 Minuten**: In dieser Zeit kommen alle Dokumente aus dem Speicher, ohne eine Propstack-Abfrage. Danach baut der nächste Aufruf neu.
- Mit `stand` bleibt ein Stand **bis zu 24 Stunden** lesbar; ältere Stände löscht der nächste Aufbau und der tägliche Cron. Ein unfertiger Stand, der älter als 30 Minuten ist, wird verworfen.
- Gleichzeitige Aufrufe: Je Parametersatz gibt es höchstens einen Stand im Aufbau (eindeutiger Index). Eine Sperre (zwei Minuten) lässt nur einen Aufruf bauen, die anderen bekommen „erneut aufrufen“. Bleibt ein Aufruf hängen und ein zweiter übernimmt, überschreibt der Nachzügler nichts: Fertigstellen wirkt nur, solange der Stand im Aufbau ist.

**Abruf „alles“ (v0.10.1, Auftrag Florian vom 12.11.2026).** Die Routine muss jedes Dokument unverändert in die Datenbank des Artifacts schreiben. Verlässlich geht das nur per Datei – und eine Tool-Antwort liegt in einer Claude-Sitzung nur dann als Datei vor, wenn sie zu groß fürs Gespräch ist. Bei den Einzelabrufen galt das nur für `pruefung/teil-01`; die übrigen Dokumente hätte das Modell abschreiben müssen.
- `dokument: "alles"` liefert, sobald der Stand fertig ist, **eine** Antwort in einer Zeile: `{"stand": "<aktualisiert>", "dokumente": {"meta/stand": {…}, "meta/projekte": {…}, "wochen/2026-KW33": {…}, …, "pruefung/teil-01": {…}, …}}`.
- Schlüssel = Name des Dokuments (Sammlung/Dokument) wie bei den Einzelabrufen. Reihenfolge: `meta/stand`, `meta/projekte`, dann die Wochen und Teile so, wie `meta/stand` sie nennt.
- Die Werte sind Zeichen für Zeichen dieselben wie bei den Einzelabrufen – es sind dieselben gespeicherten Dokumente. Passt der Speicher nicht zu dem, was `meta/stand` nennt, kommt ein Fehler statt eines unvollständigen Stands.
- Solange der Stand aufgebaut wird, kommt wie sonst die kleine Antwort mit `fortsetzen: true`. `stand`, `tage` und `broker_ids` wirken wie bei den Einzelabrufen. Die Einzelabrufe bleiben unverändert.
- Grenzen: Der Weg durch Cloudflare trägt bis 32 MiB je Antwort (WebSocket-Nachricht zwischen Worker und Durable Object). Was Claude selbst annimmt, ist nicht dokumentiert – live geprüft mit der heutigen Größe (siehe Abnahme unten). Wächst der Bestand stark, ist die Größe neu zu prüfen; die Einzelabrufe bleiben der Rückweg.
- Der Weg hängt daran, dass die Sitzung zu große Tool-Antworten als Datei ablegt. Käme die Antwort eines Tages doch ins Gespräch, darf die Routine sie nicht abschreiben, sondern muss abbrechen und melden.

**Live-Abnahme „alles“ (12.11.2026, 11:29 Uhr, v0.10.1):**
- Die Antwort kam als Datei an. Meldung der Sitzung, wörtlich: „Error: result (220,566 characters across 1 line) exceeds maximum allowed tokens. Output has been saved to …/tool-results/mcp-Propstack-dashboard_daten-….txt“.
- Die Datei ist reines, kompaktes JSON ohne Hülle: 222.358 Bytes, eine Zeile, `{"stand": …, "dokumente": {…}}` mit **17 Dokumenten**. Die Schlüssel sind genau die, die `meta/stand` nennt, in derselben Reihenfolge.
- Alle 17 Dokumente aus der Datei wurden mit dem bisherigen Export verglichen, auf denselben Zeitpunkt gestellt: **identisch, einschließlich der Feldreihenfolge** (363 Einheiten, 104 Projekte, 522 Prüfaufgaben, davon 495 offen).
- Aufbau in Etappen mit „alles“ (eigener Stand mit `tage: 90`): zweimal `fortsetzen: true` (nach 40 und 80 Abfragen), beim dritten Aufruf die Datei mit 17 Dokumenten. Die drei Aufrufe dauerten 22, 11 und 15 Sekunden.
- `stand`: Derselbe Stand noch einmal abgerufen ergab eine bytegleiche Datei; ein unbekannter Stand ergab die Fehlermeldung; der Einzelabruf `meta/stand` mit `stand` ergab dasselbe Dokument wie in der Datei.
- Aus dem Zwischenspeicher kam die ganze Antwort in 1,5 Sekunden. Kein Aufruf wartete auf eine Genehmigung. Aufgerufen wurde aus einer laufenden Sitzung, die noch die alte Tool-Definition kannte – der neue Wert „alles“ wurde trotzdem angenommen.

**Empfohlener Ablauf für die Routine (seit v0.10.1):**
1. `dashboard_daten` mit `dokument: "alles"` aufrufen und wiederholen, solange `fortsetzen: true` kommt (nacheinander, nicht parallel).
2. Die Antwort kommt nicht ins Gespräch, sondern liegt als Datei in der Sitzung (Meldung „exceeds maximum allowed tokens … Output has been saved to <Pfad>“). Die Datei ist reines JSON.
3. Ein kurzes Skript liest die Datei und schreibt je Schlüssel aus `dokumente` eine Datei; diese gehen per Dateipfad unverändert in die Datenbank des Artifacts.

Einzelabrufe (weiterhin möglich): `meta/stand` abrufen, bis das Dokument kommt; danach `meta/projekte`, jede Woche aus `wochen` (`wochen/<Woche>`) und jeden Teil aus `pruefung_teile` (`pruefung/<Teil>`) – jeweils mit `stand` = `aktualisiert`.

**Gleichheit mit dem bisherigen Export – wie geprüft:**
- Die 12 Fälle aus `tests/weekly_report/test_dashboard_export.py` und die Parsing-Fälle aus `test_propstack_parsing.py` sind portiert (`test/dashboard-dokumente.test.ts`, `test/dashboard-zeit.test.ts`).
- **Abgleich mit dem echten Export** (`test/dashboard-golden.test.ts`): `test/dashboard-golden.erzeugen.py` lässt `weekly_report.dashboard_export.main()` selbst gegen eine nachgestellte Propstack-API laufen und zeichnet Anfragen, Antworten und Dokumente auf. Der Connector bekommt dieselben Antworten vorgespielt. Bestanden ist der Test nur, wenn jedes Dokument exakt gleich ist **und** der Connector keine Anfrage stellt, die der Export nicht gestellt hat. Vier Szenarien: Ende der Sommerzeit im Fenster, Jahreswechsel mit KW53 und zwei Prüfern, Fensterbeginn in der Stunde, die es am Beginn der Sommerzeit nicht gibt, Fensterbeginn in der doppelten Stunde am Ende der Sommerzeit.
- Die Zeitrechnung (Fenster, Wochen, Schreibweise der Zeitstempel) ist gegen Werte geprüft, die Python selbst berechnet hat.
- Der Zwischenspeicher läuft im Test gegen echtes SQLite mit der Migration (`test/dashboard-store.test.ts`) – D1 ist SQLite.
- **Live-Abgleich am 12.11.2026, 10:29 Uhr:** neuer Code und alter Export nacheinander gegen das echte Propstack, beide auf denselben Zeitpunkt gestellt. Ergebnis: **17 von 17 Dokumenten inhaltlich identisch, einschließlich der Reihenfolge der Felder** (363 Einheiten, 104 Projekte, 13 Wochen, 522 Prüfaufgaben, davon 495 offen, 2 Teile). Zwei Unterschiede in der Schreibweise, beide ohne Wirkung auf das Dashboard: kompakt statt mit Leerzeichen (222 statt 236 KB) und ganze Zahlen ohne „.0“ (`10197` statt `10197.0`, 318 Stellen).

**Live-Abnahme über den Connector (12.11.2026, 10:39 Uhr, v0.10.0)** – in einer frischen Sitzung, weil eine laufende Sitzung neue Tools nicht nachlädt:
- Das Tool war sofort nach dem Deployment sichtbar (geführt unter der Server-ID, nicht unter „Propstack“) und lief ohne Genehmigungsnachfrage.
- `meta/stand` ist **identisch** mit dem bisherigen Export, auf denselben Zeitpunkt gestellt: 363 Einheiten, 104 Projekte, 522 Prüfaufgaben, davon 495 offen, 13 Wochen, 2 Teile – gleiche Felder in gleicher Reihenfolge.
- `pruefung/teil-01` (400 Aufgaben, 373 offen, 105.441 Bytes) wurde vollständig verglichen: Prüfwert (SHA-256 über den Inhalt) gleich dem des Exports.
- Alle 17 Dokumente kamen an. Der API-Key des Workers darf `/v1/activities` lesen.
- Ein Aufruf ohne `stand` lieferte danach denselben Stand aus dem Zwischenspeicher. Zwei versehentlich gleichzeitig abgesetzte Aufrufe kamen beide richtig an.

**Befund aus der Abnahme: So kommen die Dokumente in einer Claude-Sitzung an.**
- 16 der 17 Dokumente (bis rund 30 KB) kamen direkt als Tool-Antwort ins Gespräch.
- `pruefung/teil-01` war dafür zu groß. Die Sitzung meldete: „Error: result (104,921 characters across 1 line) exceeds maximum allowed tokens. Output has been saved to …/tool-results/….txt“. Die Datei enthält das Dokument unverändert als JSON, ohne Hülle. Das ist kein Fehler des Tools, sondern die Grenze der Sitzung für Tool-Antworten.
- Folge für die Routine: Das große Dokument liegt als Datei vor und lässt sich ohne Abschreiben in die Datenbank des Artifacts übernehmen. Die 16 kleineren stehen nur im Gespräch – das Modell muss sie Zeichen für Zeichen wiedergeben, um sie zu speichern (zusammen rund 117 KB, jeden Tag). Das kostet Zeit und Geld und kann unbemerkt Fehler einschleusen.

**Bewusste Abweichungen vom Export** (jeweils nur in Fällen, in denen der Export ein falsches oder unvollständiges Ergebnis geliefert hätte):
- Verschiebt sich eine Liste während des Blätterns, zählt der Export einen Datensatz doppelt. Der Connector zählt jede Einheit und jede Aufgabe einmal.
- Gibt es im Fenster keine Projekte, fragt der Connector die Projektliste nicht ab.
- Liefert Propstack mehr Seiten als die Reißleine erlaubt (8.000 Datensätze), speichert der Export still ein unvollständiges Ergebnis. Der Connector bricht mit Fehlermeldung ab.

**Entschieden (Florian, 12.11.2026): ein Abruf für alles.** Zur Wahl standen drei Wege, die Dokumente ohne Abschreiben in die Datenbank des Artifacts zu bringen:
1. So lassen – die Routine holt 17 Dokumente einzeln, 16 gibt das Modell wieder. Teuer und fehleranfällig.
2. **Ein Abruf für alles – umgesetzt in v0.10.1** (siehe oben). Kein neuer Zugang, nichts läuft durch das Modell.
3. Download-Link (15 Minuten gültig, wie beim Bild-Upload) – unabhängig vom Verhalten der Sitzung, aber ein neuer Zugang ohne Anmeldung. Nicht gebaut; bleibt der Ausweg, falls Weg 2 an einer Grenze von Claude scheitert.

## Audit-Log (D1)

Jeder Tool-Aufruf wird in `propstack-mcp-audit` (Tabelle `audit_log`, Schema in `migrations/`) protokolliert: Zeitpunkt, Mail, Propstack-ID, Tool, Parameter (max. 2000 Zeichen), Trefferzahl, Erfolg/Fehler, Dauer. Ergebnisdaten werden **nicht** gespeichert. Ein täglicher Cron (03:17 UTC) löscht Einträge, die älter als **12 Monate** sind. Bei Lese-Tools gilt „best effort“: Fällt das Log aus, läuft die Abfrage trotzdem und der Fehler wird geloggt. Ab Phase 3 (Schreiben) muss das Log vor jedem Write erfolgreich sein.

Auswerten (Cloudflare-Dashboard → D1 → `propstack-mcp-audit` → Console, oder `npx wrangler d1 execute AUDIT_DB --remote --command "…"`):

```sql
SELECT ts, user_email, tool, params, result_count, ok FROM audit_log ORDER BY ts DESC LIMIT 50;
```

## So funktioniert der Login

1. Claude registriert sich per Dynamic Client Registration (`/register`) und startet OAuth (`/authorize`).
2. Der Worker leitet zum Google-Login weiter (Scope `openid email profile`, Hinweis `hd=kromeichpartner.de`).
3. In `/callback` prüft der Worker serverseitig:
   - **3a** (`src/auth/google-id-token.ts`): Die Signatur des ID-Tokens wird gegen Googles JWKS geprüft (RS256). Außerdem `iss`, `aud`, `exp` und `iat`. `hd` muss `kromeichpartner.de` sein, `email_verified` muss `true` sein.
   - **3b** (`src/auth/broker-lookup.ts`): Zur Mail muss es in `GET /v1/brokers` genau einen Propstack-Nutzer geben. Der Abgleich ignoriert Groß- und Kleinschreibung. Treffer landen 1 h im KV-Cache (`propstack-broker:<mail>`). Abgelehnte Mails werden nie gecacht.
   - Schlägt eine Prüfung fehl, gibt es eine Seite „Zugriff verweigert“ (403) und kein Token. Ist Propstack nicht erreichbar, gibt es 503 (fail closed).
4. Das Token enthält nur `email`, `name` und `brokerId`. Das Google-Access-Token wird verworfen.
5. Access-Token-Laufzeit: 1 h. Bei jedem Refresh wird 3b erneut geprüft (`tokenExchangeCallback` in `src/index.ts`), Cache inklusive. Ohne Propstack-Nutzer bekommt der Client `invalid_grant` und muss sich neu anmelden.

## Einrichtung

Voraussetzungen: Node ≥ 20, Zugriff auf den Cloudflare-Account **kromeichpartner**, Admin in Google Workspace und in Propstack.

```bash
cd propstack-mcp
npm install
npm test            # Unit-Tests (Auth, Client, Filter, Mapper, Tools, Audit)
npm run type-check
```

### 1. Google-OAuth-Client (GCP)

1. Google Cloud Console → Projekt der Kromeich GmbH → **APIs & Dienste → OAuth-Zustimmungsbildschirm**.
   - Nutzertyp: **Intern**. Damit können sich nur Konten aus dem Workspace anmelden.
   - Scopes: `openid`, `email`, `profile`. Mehr nicht.
2. **Anmeldedaten → Anmeldedaten erstellen → OAuth-Client-ID**, Typ **Webanwendung**.
   - Autorisierte Weiterleitungs-URIs:
     - `https://propstack-mcp.kromeichpartner.workers.dev/callback` (Produktion)
     - `http://localhost:8788/callback` (lokale Tests; besser ein eigener Dev-Client)
3. Client-ID und Client-Secret notieren. Nur für die Secrets unten, nie ins Repo.

### 2. Propstack-API-Key

Propstack → **Verwaltung → API-Schlüssel**. Ein V1-Key, laut Spezifikation **ohne Löschrechte**. Ab Phase 2 braucht er **Leserechte** auf: Nutzer, Kontakte (inkl. Quellen), Objekte (inkl. Status), Projekte, Deals, Deal-Pipelines, Merkmale und Custom-Felder. Ab Phase 3 zusätzlich **Anlegen und Bearbeiten** von Kontakten und Objekten sowie **Anlegen** von Merkmalen (nur für `MCP-TEST`). **Keine Löschrechte.** Fehlt ein Recht, meldet das Tool „Zugriff verweigert (401/403)“.

**Zweiter Schlüssel (ab v0.11.0, optional):** `PROPSTACK_API_KEY_V2` für die V2-Schnittstelle – nur für `create_company` und `link_contact_company`. Er braucht Lesen und Schreiben auf Kontakte und Verknüpfungen, **keine Löschrechte**. Ohne ihn sind nur diese zwei Tools gesperrt.

### 3. Cloudflare: Login und KV

```bash
npx wrangler login                                 # mit dem Firmen-Account kromeichpartner
```

Der KV-Namespace `propstack-mcp-OAUTH_KV` (ID `759b347676ea454c98f8dbd171d4070f`) ist bereits angelegt und in `wrangler.jsonc` eingetragen. Die ID ist kein Secret.

### 4. Lokal testen (vor jedem Deployment)

```bash
cp .dev.vars.example .dev.vars    # .dev.vars ist gitignored
# Werte eintragen. COOKIE_ENCRYPTION_KEY: openssl rand -hex 32
npm run dev                       # http://localhost:8788
npx @modelcontextprotocol/inspector@latest
```

Im Inspector `http://localhost:8788/mcp` eintragen, verbinden, anmelden und `whoami` aufrufen. Dann die Abnahmefälle unten durchspielen.

### 5. Secrets und Deployment

Erst deployen, wenn alle Abnahmefälle lokal grün sind. Es gibt kein Deployment ohne Auth.
`wrangler secret put` für einen noch nicht existierenden Worker legt einen leeren Platzhalter-Worker an. Deshalb beim **ersten** Deployment die Secrets direkt mitschicken:

```bash
# Einmalig: Datei außerhalb des Repos anlegen, z. B. ~/propstack-mcp.secrets (Format wie .dev.vars):
#   GOOGLE_CLIENT_ID=...  GOOGLE_CLIENT_SECRET=...  COOKIE_ENCRYPTION_KEY=...  PROPSTACK_API_KEY=...  PROPSTACK_API_KEY_V2=...
npx wrangler deploy --secrets-file ~/propstack-mcp.secrets
rm ~/propstack-mcp.secrets
```

Danach werden einzelne Secrets nur noch so geändert:

```bash
npx wrangler secret put PROPSTACK_API_KEY
npx wrangler secret put PROPSTACK_API_KEY_V2   # optional, für Firmen und Verknüpfungen
npx wrangler secret put GOOGLE_CLIENT_ID
npx wrangler secret put GOOGLE_CLIENT_SECRET
npx wrangler secret put COOKIE_ENCRYPTION_KEY
npx wrangler deploy
```

Prüfen: `curl -i -X POST https://propstack-mcp.kromeichpartner.workers.dev/mcp` muss `401` liefern.

### 5b. Automatisches Deployment (ab Phase 2)

`.github/workflows/propstack-mcp-deploy.yml` veröffentlicht nach jedem Merge auf `main` (bei Änderungen in `propstack-mcp/`): Tests → D1-Migrationen → `wrangler deploy` → Smoke-Test (401 ohne Token). Einmalig einrichten:

1. Cloudflare-Dashboard → **Mein Profil → API-Tokens → Token erstellen** → Vorlage **„Cloudflare Workers bearbeiten“**. Zusätzlich die Berechtigung **Konto → D1 → Bearbeiten** hinzufügen und das Konto auf kromeichpartner beschränken.
2. GitHub → Repo → **Settings → Secrets and variables → Actions** → zwei Secrets anlegen:
   - `CLOUDFLARE_API_TOKEN` (Token aus Schritt 1)
   - `CLOUDFLARE_ACCOUNT_ID` (Cloudflare-Dashboard → Workers & Pages → rechts „Konto-ID“)

Ohne diese Secrets wird das Deployment mit einer Warnung übersprungen. Die Worker-Secrets (Google, Propstack, Cookie-Key) bleiben in Cloudflare, ein Deployment löscht sie nicht.

### 5c. Nach einem Deployment mit neuen oder geänderten Tools

Claude speichert die Tool-Liste zwischen. Nach jedem Deployment, das Tools hinzufügt oder ändert:
1. **Organisationseinstellungen → Konnektoren → Propstack → Tools → neu laden** (Org-Owner).
2. Jede Person: **Anpassen → Konnektoren → Propstack** → Tools neu laden bzw. trennen und neu verbinden. Danach einen **neuen** Chat öffnen.

Befund vom 10.11.2026 (Einführung von `create_task`):
- Eine **laufende** Sitzung bekommt neue Tools nicht, auch nicht nach dem Neuladen im Konnektor. Konnektoren werden beim Start einer Sitzung gelesen. Geänderte Parameter vorhandener Tools kommen dagegen an, weil der Server sie prüft.
- In einer **neuen** Sitzung ist das Tool da. Der Server kann dort unter seiner Server-ID statt unter „Propstack“ geführt sein (`mcp__<Server-ID>__create_task` statt `mcp__Propstack__create_task`). Tools deshalb per Stichwort suchen und keinen festen Namen voraussetzen.

Befund vom 11.11.2026 (Nachfragen in Cloud-Sitzungen von Claude Code) – am selben Tag berichtigt, nachdem die Wartezeiten aller Aufrufe der Sitzung ausgewertet waren:
- **Nachgefragt wird je Tool, nicht je Art der Änderung.** Jeder einzelne `update_object`-Aufruf wartete auf eine Freigabe, und die Nachfrage bietet nur „einmal erlauben“ – trotz „Immer erlauben“ am Konnektor und trotz Modus „Auto“. `apply_plan` (9 Aufrufe) und `undo_plan` (2) liefen am 11.11. dagegen ohne Freigabe durch, ebenso `plan` und alle Lese-Tools. Dabei kennzeichnet der Server `apply_plan` und `undo_plan` genauso als „überschreibt Bestehendes“ wie `update_object`. Die frühere Aussage an dieser Stelle („eine Freigabe je Etappe“) war eine Annahme und falsch.
- **Ursache laut Dokumentation von Claude Code** (Seite „Permissions“, Abschnitt MCP): Steht ein Tool eines claude.ai-Konnektors auf „Nachfragen“ und erreicht diese Einstellung die Sitzung, wirken Erlaubnisregeln für dieses Tool nicht – es wird bei jedem Aufruf gefragt, auch im Modus „Auto“. Deshalb konnte die Erlaubnisregel im Repository (`.claude/settings.json`, von Florian am 11.11. angelegt: `mcp__Propstack__*` und dieselbe Regel für die Server-ID) nichts ändern. Die Datei kann bleiben; sie schadet nicht.
- **Stellschraube ist die Berechtigung je Tool am Konnektor selbst:** claude.ai → Anpassen → Konnektoren → Propstack → Tool-Berechtigungen, bei Bedarf zusätzlich in den Organisationseinstellungen.
- **Bestätigt am 11.11.2026 (Florian):** `update_object` stand dort „gerade wieder“ auf „Genehmigung erforderlich“, obwohl es vorher auf „Immer erlauben“ gestellt war.
- **Warum es zurückspringt:** Die gespeicherte Erlaubnis hängt am Wortlaut des Tools (Beschreibung und Beschreibungen der Parameter). Ändert ein Deployment diesen Wortlaut, gilt das Tool als neu und steht wieder auf „Genehmigung erforderlich“. Belege:
  - Eigene Auswertung: Die Definition jedes Tools wurde für sieben Stände vom 09. bis 11.11. verglichen. `update_object` änderte sich in diesen drei Tagen dreimal, `update_project` und `create_object` je zweimal, `update_contact`, `plan` und `undo_plan` je einmal. `apply_plan`, `set_project_owner`, `create_contact` und `create_task` blieben unverändert. Ohne Nachfrage lief am 11.11. genau das nie geänderte `apply_plan`; jeder Aufruf des dreimal geänderten `update_object` wartete auf eine Freigabe.
  - Nutzeranalyse im öffentlichen Fehlerverzeichnis von Anthropic (`anthropics/claude-ai-mcp`, Meldungen 1087 und 1032): Die Erlaubnis sei an eine Prüfsumme aus Beschreibung und Parameter-Beschreibungen gebunden. Das ist keine offizielle Aussage.
  - Vorbehalt: In derselben Meldung berichten viele Nutzer, auch aus Cloud-Sitzungen und Team-Tarifen, dass „Immer erlauben“ selbst ohne Änderung nicht hält. Ob ein erneutes Erlauben trägt, ist deshalb zu testen und nicht vorauszusetzen.
- **Behoben und getestet am 11.11.2026:** Florian hat die Tools in den Admin-Einstellungen (Organisation) neu geladen und auf „Immer erlauben“ gestellt. Direkt danach liefen in der laufenden Cloud-Sitzung ohne Nachfrage durch: `update_object` (echte Änderung am Testobjekt 6375202, 4,2 s – vorher 38 s bis 13 min Wartezeit je Aufruf), `update_project` (2,1 s), `update_contact` (2,8 s) und `undo_plan` (1,3 s). Die Einstellung wirkt also sofort, ohne neue Sitzung, und sie gilt für die ganze Organisation.
- **Nach jeder Änderung an einer Tool-Definition** müssen die betroffenen Tools dort neu geladen und wieder auf „Immer erlauben“ gestellt werden. Ob das Zurückspringen wirklich an der Änderung hängt, zeigt sich bei der nächsten gewollten Änderung – dann gezielt nachsehen.
- **Regel für die Entwicklung (ab 11.11.2026): Der Wortlaut vorhandener Tools bleibt stabil.** Beschreibung, Parameter und Parameter-Beschreibungen eines vorhandenen Tools werden nicht mehr nebenbei geändert – jede solche Änderung kostet jede Person im Team die gespeicherte Erlaubnis für dieses Tool. Ist eine Änderung nötig: bündeln und im Bericht an Florian die betroffenen Tools nennen („bitte neu erlauben: …“). Ein Test wacht darüber (`test/tool-definitions.test.ts`): Er schlägt fehl, sobald sich die Definition eines Tools ändert, eines dazukommt oder wegfällt, und nennt die betroffenen Tools. Eine gewollte Änderung muss dort ausdrücklich übernommen werden (`test/tool-definitions.snapshot.ts`).
- Offener Vorschlag: Regeln und Befunde stehen bisher in den Tool-Beschreibungen und waren der häufigste Grund für Änderungen. Sie ließen sich in die allgemeinen Hinweise des Servers verlagern; durchgesetzt werden sie ohnehin im Code. Das wäre ein einmaliger Umbau, der alle Erlaubnisse noch einmal zurücksetzt. Entscheidung steht aus.

### 6. Connector in Claude eintragen

- **Team/Enterprise (empfohlen, einmal für alle):** Ein Org-Owner geht zu claude.ai → **Admin-Einstellungen → Connectors → Add custom connector**. Name: `Propstack`, URL: `https://propstack-mcp.kromeichpartner.workers.dev/mcp`. Client-ID und Secret leer lassen (Dynamic Client Registration).
- **Einzelner Nutzer:** claude.ai → **Einstellungen → Connectors → Add custom connector** mit derselben URL.
- Danach im Chat den Connector aktivieren und **Connect** wählen. Google-Login mit dem @kromeichpartner.de-Konto. Test: „Wer bin ich in Propstack?“ ruft `whoami` auf.

## Abnahme Phase 1

| Kriterium | So prüfen |
|---|---|
| Domain-Konto mit Propstack-Nutzer → richtige ID | Anmelden, `whoami` aufrufen, `propstack_user_id` mit Propstack → Verwaltung → Nutzer vergleichen |
| Privates Gmail → abgelehnt | Mit Gmail-Konto anmelden: Google blockt schon beim internen Client. Sonst zeigt der Worker 403 |
| Domain-Konto ohne Propstack-Nutzer → abgelehnt | Mit einem Funktionspostfach anmelden → 403 „kein aktiver Propstack-Nutzer“ |
| Kein Secret im Repo | `git grep -nE '(PROPSTACK_API_KEY(_V2)?|GOOGLE_CLIENT_SECRET|COOKIE_ENCRYPTION_KEY)\s*[=:]\s*\S{8,}|GOCSPX[-]|[0-9]+-[a-z0-9]{32}\.apps\.googleusercontent\.com'` liefert nichts |
| Unit-Tests 3a/3b | `npm test` (die CI läuft bei Änderungen in `propstack-mcp/`) |

## Abnahme Phase 2 (live in Claude prüfen)

Die Logik ist per Unit-Tests abgedeckt. Die echten Propstack-Antworten lassen sich aber nur mit dem Live-Key prüfen. Nach dem Deployment:

| Prüfung | Frage an Claude |
|---|---|
| Kontaktsuche + Detail | „Suche den Kontakt <Name> und zeig mir die Details.“ |
| Objektsuche mit Filtern | „Welche verfügbaren Mietobjekte über 1.000 m² haben wir in <Ort>?“ |
| Deals eines Objekts | „Welche Interessenten gibt es für Objekt <ID>?“ |
| Pipeline-Status | „Wie steht die Pipeline <Name>? Mit Summen je Phase.“ (Summen stichprobenartig mit Propstack vergleichen) |
| Merkmale / Felder / Stammdaten | „Welche Kontakt-Merkmale gibt es?“, „Welche Custom-Felder haben Objekte?“ |
| Auswertung | „Wie viele Kontakte haben wir je Quelle?“ (Gesamtzahl mit Propstack vergleichen) |
| Filter mit Listen | Suche mit zwei Merkmalen gleichzeitig. Prüft, ob Propstack `group[]=` versteht |
| Audit-Log | Danach in D1: `SELECT * FROM audit_log ORDER BY ts DESC LIMIT 10;` |

Ergebnis des ersten Live-Tests (09.10.2026) und Korrekturen: Merkmale wurden per ODER verknüpft (78 + 85 → 135 statt 28), jetzt gibt es `tag_match`. Die Ortssuche war unscharf (Mannheim bei „Leverkusen“), jetzt gibt es `city`/`zip_prefix`. Objekte ohne Status fielen stillschweigend weg, jetzt werden sie gemeldet. Betreuer kamen nur als ID, jetzt mit `broker_name`. Pipeline-Summen zeigten 0 € ohne Hinweis, jetzt `values_available`/`outside_stages`. Datenbefunde (kein Code): Keine Kontakte haben eine Quelle gesetzt, Deals haben keine Preise, „Absage“ ist in Propstack mit 5 % gewichtet, und `last_contact_at` liegt teils in der Zukunft.

## Bekannte Grenzen (bewusste Entscheidungen Phase 1)

- **Aktiv-Status:** `GET /v1/brokers` hat laut Doku kein Aktiv-Flag. Jeder Nutzer, den V1 liefert, gilt als aktiv. **Einmal mit echtem Key prüfen:** Taucht ein deaktivierter Propstack-Nutzer noch in `/v1/brokers` auf? Wenn ja, greift das Offboarding nicht. Dann auf `GET /v2/brokers?email=…` umstellen, das hat `active`, `archived` und `blocked`.
- **Rollen:** Alle Propstack-Rollen dürfen sich anmelden. Ein Funktionspostfach, das in Propstack als (technischer) Nutzer existiert, kommt durch.
- **Offboarding-Verzögerung:** Access-Token 1 h plus Cache 1 h beim Refresh. Nach dem Deaktivieren in Propstack bleibt der Zugriff also noch bis zu ~2 h bestehen. Refresh-Tokens laufen 30 Tage (Standard der Library), werden aber stündlich gegen 3b geprüft.
- **Google-Konto sperren reicht nicht:** Der Refresh fragt Google nicht erneut. Offboarding heißt: den Propstack-Nutzer deaktivieren bzw. entfernen.
