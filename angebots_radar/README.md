# Angebots-Radar (Vorauswahl je Gesuch)

Nennt je aktivem Mietgesuch die freien Flächen aus dem Bestand, die passen und dem Kontakt **noch nicht
angeboten** wurden – mit dem Grund, warum sie passen, und mit dem, was vor einem Angebot zu prüfen ist.
**Liest nur:** kein Schreiben in Propstack, kein Slack, keine KI (also auch keine Kosten am Anthropic-Limit).

Anlass (26.11.2026, Florian: „etwas Neues, was uns hilft“): Sechs Automatisierungen pflegen den Bestand. Die
Frage, mit der das Geld verdient wird – *welche unserer Flächen passen auf dieses Gesuch?* –, beantwortete
bisher nur `scripts/gesuch_matching.py`, von Hand, für ein Gesuch nach dem anderen. In Propstack stehen aber
die Gesuche des Teams als Suchprofile, und in einer Notiz vom 19.11. heißt es wörtlich „gerne Vorauswahl
treffen“. Diese Vorauswahl macht das Paket für alle Gesuche auf einmal.

## Aufruf

```bash
python -m angebots_radar.main                       # alle aktiven Hallengesuche (Einheiten laden: rund 4 Minuten)
python -m angebots_radar.main --betreuer Marek      # nur die Gesuche eines Betreuers
python -m angebots_radar.main --gesuch 13969555     # ein Suchprofil
python -m angebots_radar.main --nur-neu --tage 7    # nur, was seit 7 Tagen neu ist (Fläche oder Gesuch)
python -m angebots_radar.main --merken angebots_radar/laeufe/JJJJ-MM-TT.json    # Vorschläge ohne Namen ablegen
python -m angebots_radar.main --vergleich angebots_radar/laeufe/2026-11-26.json # was wurde daraus?
python -m angebots_radar.main --daten ORDNER        # gespeicherte Antworten lesen/ablegen (Entwickeln, zweite Auswertung)
```

Umgebung: `PROPSTACK_API_KEY` oder `PROPSTACK_API_V1`. Tests: `pytest tests/angebots_radar -q` (240, ohne Netz).
Der Lauf endet mit Fehler, wenn sich Kontakte nicht lesen lassen – ohne Namen ist nicht geprüft, ob ein Profil ein Testprofil ist.

## Ablauf

1. **Gesuche** (`gesuch.py`): `GET /v1/saved_queries`. Gebiet aus `lat`/`lng`/`radius`, `polygon`, `cities` oder
   `regions`. Fläche aus dem Text der Team-Vorlage („▪️ ~8.000 - 12.000 m² Hallenfläche“), sonst aus den
   Feldern, sonst aus dem Custom-Feld `lagerflache` – das ist die **Untergrenze** für Propstacks eigenes
   Matching (meist 50–95 % des Wunsches), dann gilt bis zum Doppelten als passend. Dazu Höhe, Rampen, Bezug,
   Besonderheiten (Bedingung oder Wunsch), „laut Notiz erledigt“, „noch nicht senden“. Gelesen wird je
   Teilaussage: „Büro 300 m², Halle 5.000 m²“ sind zwei, „Kühlung ja, Gefahrgut nein“ auch. Was sich nicht
   sicher lesen lässt, bleibt leer.
2. **Bestand** (`bestand.py`): `GET /v1/units?expand=1`. Angebotsfähig ist, was nicht vermietet und nicht
   inaktiv ist und in Vermarktung steht – oder Altbestand ohne Propstack-Status mit „Status Logistik“ = Aktiv
   (dieselbe Regel wie im Stresstest vom 19.11.). Es zählt die **Hallenfläche**, nicht die Objektart – und
   wenn „Lagerfläche verfügbar“ deutlich darunter liegt, der freie Teil. Bezug: Der Text gilt („frei ab“,
   dann „Bezug“), das Datumsfeld nur ohne Text. Rampen stehen nur in `ramepntore`; `anzahl_rampentore_2` ist
   „Ebenerdige Tore“. Dieselbe Halle unter zwei IDs (gleiche Adresse, Fläche und Bezeichnung, anderes
   Projekt) zählt einmal.
3. **Abgleich** (`abgleich.py`), je Gesuch:
   - Gebiet; bis 25 % über dem Umkreis (mindestens 5, höchstens 10 km) gilt als „knapp außerhalb“ – Vorschlag mit Hinweis.
   - Fläche: **passt** (±10 %), **teilbar**, **Kombination** (bis zu vier Einheiten eines Projekts, deren
     Summe passt), **größer** (bis zum Doppelten – Teilfläche erfragen).
   - Hallenhöhe: gepflegt und mehr als 0,5 m zu niedrig → raus; nicht gepflegt → „prüfen“.
   - Bezug: wird die Einheit mehr als zwei Quartale nach dem Bedarf frei → kein Vorschlag (gezählt).
   - Rampen: nur Hinweis (gepflegt bei gut der Hälfte, uneinheitlich gezählt).
   - Kühlung, Kran, Gleisanschluss als Bedingung: nur mit Nachweis am Objekt – und „nachrüstbar“, „möglich“
     oder „deaktiviert“ ist keiner. Sonst sagt der Bericht „von Hand suchen“, statt ungekühlte Hallen zu nennen.
   - **Schon angeboten:** Deal des Kontakts zur Einheit oder zu ihrem Projekt (jede Pipeline, jede Stufe,
     auch Absage), Einheit mit ID in der Notiz, oder hinter „Angeboten:“ in der Notiz: Straße (als ganzes
     Wort, mit passender Hausnummer und Stadt), „Ort Eigentümer“ oder „Ort Unit 2.1“. Ein Angebot zum
     zweiten Datensatz derselben Halle gilt mit.
   - Je Projekt ein Vorschlag (weitere passende Einheiten werden gezählt; ist eine davon neu, steht das da).
   - Rang: Art, Nähe zum Flächenwunsch, Entfernung, belegte Höhe/Rampen/Besonderheiten; Abzug für Altbestand,
     geschätzte Lage, Widersprüche am Objekt, alte Datensätze.
4. **Bericht** (`bericht.py`): je Betreuer, zuletzt bearbeitete Gesuche zuerst, höchstens fünf Vorschläge je
   Gesuch. Gesuche, die seit über 180 Tagen niemand bearbeitet hat, stehen getrennt („erst nachfragen“).
   Am Ende: was in Propstack aufzuräumen ist.

Kein Vorschlag entsteht für: Ankaufsprofile, andere Objektarten, Freiflächen-Gesuche, Testprofile, Profile
ohne lesbare Fläche – und für Profile **ohne Gebiet** (dort wird nur gezählt: fünf aus Hunderten wären Zufall;
als „ohne Gebiet“ gilt auch ein Vieleck um ganz Deutschland). Wen der *Text* als Ankauf, Grundstück oder
Freifläche ausschließt, der steht einzeln im Bericht – ein falsch gelesenes Mietgesuch soll auffallen.

## Befund vom 26.11.2026 (live, nur gelesen)

Zahlen nach dem Prüflauf (siehe unten); in Klammern der Stand davor, wo er sich geändert hat.

| | Zahl |
|---|---|
| Suchprofile in Propstack | 271, davon 243 aktiv |
| … davon Ankaufsprofile von Investoren (BUY) | 142 aktiv – laufen nicht durch den Abgleich |
| Aktive Hallengesuche zur Miete, geprüft | **69** (70) – ohne 7 Testprofile, 4 Profile an einem Kollegen, 3 an nicht mehr abrufbaren Kontakten |
| … mit Vorschlägen | 56 (57) – 31 „frisch“, 25 seit über 180 Tagen nicht bearbeitet |
| Vorschläge gezeigt (höchstens 5 je Gesuch) | 270 (274), über 200 verschiedene Einheiten |
| Passende Objekte insgesamt | 2.345 (2.563) – ohne Deckel wäre das eine weitere Liste, die niemand liest |
| Passende Flächen, die der Kontakt schon kennt | 81 (herausgenommen) |
| Gesuche, deren Kontakt keinen einzigen Deal hat | 45 von 69; unter den frischen 16 von 33 |
| „Nur neu“, 7 Tage (so sähe eine Wochenmeldung aus) | 8 Gesuche, 20 Vorschläge (14 / 41 – der Unterschied waren doppelt angelegte Hallen) |
| Angebotsfähige Flächen | 1.299 Hallen aus 1.310 Datensätzen (1.103 Vermarktung, 196 Altbestand) |

Der vierte Wert von unten ist kein Beweis, dass nichts angeboten wurde – Angebote stehen nur teilweise als
Deal in Propstack (seit Oktober in „300 Mieter“, davor oft nur in der Notiz oder gar nicht).

**Gegenprobe an den echten Angeboten.** Pipeline „300 Mieter“, 86 Deals: 21 hängen an Kontakten ohne
Hallengesuch, bei 11 ist die Einheit heute nicht mehr frei. Von den übrigen 54 hätte der Abgleich **32**
gefunden. Die 22 anderen liegen alle **außerhalb des im Suchprofil gezeichneten Gebiets** (bis 489 km:
München für ein Gesuch um Düsseldorf, Wedel für eines im Sauerland) – Fläche, Höhe und Bezug haben kein
einziges echtes Angebot ausgeschlossen. Die Regeln treffen also, was das Team anbietet; wo das Profil den
Bedarf nicht abbildet, kann kein Abgleich helfen. Nach dem Prüflauf neu gerechnet: unverändert 32 von 54.

**Stichprobe von Hand** (12 zufällige frische Gesuche, 34 Vorschläge gegen die Objektdaten gelesen): 30
plausibel, 4 falsch. Die Ursachen sind seitdem abgestellt: eine als frei geführte Halle mit „Vermietungsstand
100 %“ (jetzt Hinweis und Abzug) und drei Vorschläge für ein Gesuch ohne Gebiet (jetzt nur gezählt).
„Plausibel“ heißt: Lage, Fläche, Höhe und Termin stimmen laut Daten. Ob die Fläche wirklich noch frei ist,
weiß nur der Eigentümer.

**Unabhängiger Prüflauf (26./27.11.2026, nur gelesen).** Ein zweiter Durchgang ohne Kenntnis der Bauweise hat
die Lesefunktionen mit rund 600 Eingaben beschossen und den Lauf gegen die Rohdaten gelesen: 14 belegte Fehler,
12 Schwächen. Alle sind behoben und als Testfall mit dem falschen Ergebnis von vorher festgehalten
(`tests/angebots_radar`, „Befunde des Prüflaufs“). Was im Lauf sichtbar falsch war:

- **Doppelt angelegte Hallen galten als „neu“** und standen deshalb oben; ein Angebot zum einen Datensatz
  wurde beim anderen nicht erkannt. Elf Hallen in Kirchlengern, Bünde, Porta Westfalica und Rheine.
- **„Frei ab sofort“ bei 14 Einheiten, deren Bezug „auf Anfrage“ lautet** – gelesen aus einem alten Datum im
  dritten Bezugsfeld. Jetzt: „Bezug: auf Anfrage“ unter „prüfen“.
- **Ebenerdige Tore als Rampen gezählt** bei 170 Einheiten (Feld `anzahl_rampentore_2`, im Prüflauf nur
  gestreift, beim Nachzählen gefunden).
- **Ganze statt freier Fläche** bei 31 Datensätzen (14.086 m² angeboten, 3.919 m² frei).
- **Kran, Kühlung, Gleis ohne Beleg:** „Kranbahnanlagen nachrüstbar“, „Fußbodenheizung/-kühlung“, „Am
  Gleisdreieck“. Kühlung ist jetzt an 9 Hallen belegt, Kran an 25, Gleisanschluss an 16.
- **Im Gesuch:** die erste Zahl der Zeile als Hallenfläche („Büro 300 m², Halle 5.000 m²“ → 300), Jahreszahl,
  PLZ und „30k Budget“ als Fläche, „12,20 m“ als 20 m, „noch nichts angemietet“ als erledigt, „Kühlung ja,
  Gefahrgut nein“ als nichts von beidem.

Zehn der 69 Gesuche werden seitdem anders gelesen (alle am Originaltext geprüft: richtig). Von den 274
Vorschlägen davor stehen 238 unverändert; 36 fielen heraus (20 nur aus den ersten fünf, 8 Zwillinge oder
schon angeboten, 6 wegen der freien Fläche, 2 zeitlich), 32 rückten nach.

**Was dabei am Bestand aufgefallen ist** (alles nur gelesen, nichts geändert):

- **267 angebotsfähige Einheiten ohne Koordinaten** (245 in Vermarktung). Jede Umkreissuche übersieht sie –
  auch Propstacks eigenes Suchprofil-Matching. Hier bekommen 192 eine geschätzte Lage (Projekt, PLZ, Ort);
  75 bleiben ohne.
- **11 Hallen stehen zweimal in Propstack** – einmal ohne Projekt (2025 bzw. 08/2026 angelegt), einmal im
  Projekt (09/2026 bzw. 24.11.2026). Welcher Datensatz bleibt, entscheidet ein Mensch.
- **Bei 31 Datensätzen liegt „Lagerfläche verfügbar“ unter 90 % der „Lagerfläche“;** bei 12 liegt sie darüber
  – welche Zahl stimmt, ist aus den Feldern nicht zu entscheiden (Hinweis am Vorschlag).
- **Bezug an drei Stellen:** „frei ab“, „Bezug“ (teils nur die Art: „Quartal“, „Datum“) und „Bezug (Datum)“.
  Bei 254 Hallen ist kein Termin lesbar (190 mit Text wie „auf Anfrage“, 63 ganz leer).
- **„Lagerfläche teilbar ab“ steht bei 152 Einheiten um den Faktor 1.000 zu klein** im Feld (10.385 m² als
  10.385). Für Propstacks Matching ist die Einheit damit „teilbar ab 10 m²“.
- **174 Einheiten des Altbestands tragen die Objektart „APARTMENT“** (Import 01/2025), sind aber Hallen.
- **10 Einheiten gelten als frei und tragen „Vermietungsstand 100 %“.**
- **Suchprofile:** 5 aktive ohne lesbare Fläche, 4 ohne Gebiet, 7 Testprofile, 4 an Kollegen statt am Kunden,
  3 an Kontakten, die die Schnittstelle nicht mehr liefert (404); 36 der 69 seit über einem halben Jahr nicht
  bearbeitet. Nur zwei Suchprofile führen eine „Angeboten:“-Liste in der Notiz.

## Seite und Rückmeldung

`seite/angebots-radar.html` zeigt den Lauf als Arbeitsliste: Filter nach Betreuer, „nur Neues“, Suche, je
Vorschlag „passt“/„prüfen“ und der Link nach Propstack. Die Daten liegen als `radar.json` daneben
(`--seite radar.json`; mit Kundennamen, deshalb nicht im Repo). Veröffentlicht am 26.11.2026 als private
Claude-Seite, nach dem Prüflauf am 27.11.2026 neu. Dort lässt sich je Vorschlag **„Angeboten“** oder **„Passt nicht“ mit Grund** anklicken; das
wird in der Datenbank der Seite gespeichert (Sammlung `urteile`, Schlüssel `<Suchprofil>_<Einheit>`). Diese
Urteile sind die zweite Messung neben `--vergleich`: Sie sagen nicht nur, ob angeboten wurde, sondern warum
ein Vorschlag nichts taugte – daran werden die Regeln nachgezogen.

## Grenzen

- Ein Vorschlag ist eine Vorauswahl, kein Angebot. Was unter „prüfen“ steht, ist nicht erledigt.
- „Schon angeboten“ sieht nur, was in Propstack steht (Deals, Notiz). Ein Angebot per Mail ohne Deal wird
  noch einmal vorgeschlagen. Kontakte derselben Firma werden nicht zusammengezogen.
- Dubletten erkennt das Paket nur bei gleicher Adresse, Fläche und Bezeichnung. Eine Halle, die beim zweiten
  Anlegen anders vermessen oder benannt wurde, zählt zweimal.
- Bekannte Lesefehler, bewusst offen: „2.000 m² Kühlfläche in Halle mit 10.000 m²“ ergibt 2.000; „Kunde hat
  2.000 m² und braucht 5.000 m²“ ergibt 2.000; „kein Gefahrgut und Kühlung nötig“ liest keins von beiden.
- Hat ein Kontakt mehrere Bedarfe und nur ein Profil, sieht der Abgleich nur das Profil.
- Text wird nach festen Mustern gelesen, nicht verstanden. Ein Gesuch mit zwei Phasen („bis Q3 2.000–3.000 m²,
  danach 5.000–7.000 m²“) wird mit der ersten gelesen.
- Das Bundesland kommt, wo das Feld fehlt, aus den ersten zwei Ziffern der PLZ – an Landesgrenzen ungenau.
- Ankaufsprofile (142) und Kaufobjekte sind nicht Teil des Abgleichs. Das wäre eine zweite Spur.

## Betrieb – noch zu entscheiden

Das Paket läuft bisher nur von Hand. Der Lauf vom 26.11.2026 liegt ohne Namen in `laeufe/2026-11-26.json`;
`--vergleich` zählt später, für wie viele der 270 Vorschläge inzwischen ein Deal angelegt wurde – getrennt
nach „genau diese Einheit“ und „nur dasselbe Projekt“, gezählt ab dem Zeitpunkt, zu dem die Deals gelesen
wurden (26.11.2026, 23:26 Uhr). **Erst diese Zahl sagt, ob das Radar wirkt** – der Stresstest vom 19.11. hat gezeigt, was passiert, wenn man
Aktivität statt Wirkung misst.

1. **Wohin?** Vorschlag: einmal pro Woche `--nur-neu` als Slack-Nachricht an den jeweiligen Betreuer (am
   26.11. wären das 8 Gesuche und 20 Vorschläge über alle; ohne KI, läuft als GitHub-Workflow wie die Handler). Den Text dazu
   liefert `--nur-neu --nachricht NAME` schon heute – gesendet wird nichts. Nicht als
   Propstack-Aufgaben – die liest niemand (Stresstest, Befund 1).
2. **Vorauswahl als Deal?** Die Pipeline „300 Mieter“ hat die Stufe „Vorauswahl“. Vorschläge dort anzulegen
   brächte sie an den Ort, an dem Marek arbeitet – ist aber Schreiben an Live-Daten und braucht ein
   Connector-Tool für Deals, das es noch nicht gibt.
3. **Die Datenlücken oben** (Koordinaten, „teilbar ab“, doppelte Hallen, Testprofile) – jede einzeln als
   Sammeländerung mit Probe und Protokoll, nach Freigabe.
