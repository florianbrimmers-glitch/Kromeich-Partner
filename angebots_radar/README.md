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

Umgebung: `PROPSTACK_API_KEY` oder `PROPSTACK_API_V1`. Tests: `pytest tests/angebots_radar -q` (99, ohne Netz).

## Ablauf

1. **Gesuche** (`gesuch.py`): `GET /v1/saved_queries`. Gebiet aus `lat`/`lng`/`radius`, `polygon`, `cities` oder
   `regions`. Fläche aus dem Text der Team-Vorlage („▪️ ~8.000 - 12.000 m² Hallenfläche“), sonst aus den
   Feldern, sonst aus dem Custom-Feld `lagerflache` – das ist die **Untergrenze** für Propstacks eigenes
   Matching (meist 50–95 % des Wunsches), dann gilt bis zum Doppelten als passend. Dazu Höhe, Rampen, Bezug,
   Besonderheiten (Bedingung oder Wunsch), „laut Notiz erledigt“, „noch nicht senden“. Was sich nicht sicher
   lesen lässt, bleibt leer.
2. **Bestand** (`bestand.py`): `GET /v1/units?expand=1`. Angebotsfähig ist, was nicht vermietet und nicht
   inaktiv ist und in Vermarktung steht – oder Altbestand ohne Propstack-Status mit „Status Logistik“ = Aktiv
   (dieselbe Regel wie im Stresstest vom 19.11.). Es zählt die **Hallenfläche**, nicht die Objektart.
3. **Abgleich** (`abgleich.py`), je Gesuch:
   - Gebiet; bis 25 % (mindestens 5 km) über dem Umkreis gilt als „knapp außerhalb“ – Vorschlag mit Hinweis.
   - Fläche: **passt** (±10 %), **teilbar**, **Kombination** (bis zu vier Einheiten eines Projekts, deren
     Summe passt), **größer** (bis zum Doppelten – Teilfläche erfragen).
   - Hallenhöhe: gepflegt und mehr als 0,5 m zu niedrig → raus; nicht gepflegt → „prüfen“.
   - Bezug: wird die Einheit mehr als zwei Quartale nach dem Bedarf frei → kein Vorschlag (gezählt).
   - Rampen: nur Hinweis (gepflegt bei gut der Hälfte, uneinheitlich gezählt).
   - Kühlung, Kran, Gleisanschluss als Bedingung: nur mit Nachweis am Objekt. Sonst sagt der Bericht „von
     Hand suchen“, statt ungekühlte Hallen zu nennen.
   - **Schon angeboten:** Deal des Kontakts zur Einheit oder zu ihrem Projekt (jede Pipeline, jede Stufe,
     auch Absage), Einheit mit ID in der Notiz, oder ihre Straße hinter „Angeboten:“ in der Notiz.
   - Je Projekt ein Vorschlag (weitere passende Einheiten werden gezählt); dieselbe Halle zweimal in Propstack
     zählt einmal, die Dublette wird genannt.
   - Rang: Art, Nähe zum Flächenwunsch, Entfernung, belegte Höhe/Rampen/Besonderheiten; Abzug für Altbestand,
     geschätzte Lage, Widersprüche am Objekt, alte Datensätze.
4. **Bericht** (`bericht.py`): je Betreuer, zuletzt bearbeitete Gesuche zuerst, höchstens fünf Vorschläge je
   Gesuch. Gesuche, die seit über 180 Tagen niemand bearbeitet hat, stehen getrennt („erst nachfragen“).
   Am Ende: was in Propstack aufzuräumen ist.

Kein Vorschlag entsteht für: Ankaufsprofile, andere Objektarten, Freiflächen-Gesuche, Testprofile, Profile
ohne lesbare Fläche – und für Profile **ohne Gebiet** (dort wird nur gezählt: fünf aus Hunderten wären Zufall).

## Befund vom 26.11.2026 (live, nur gelesen)

| | Zahl |
|---|---|
| Suchprofile in Propstack | 271, davon 243 aktiv |
| … davon Ankaufsprofile von Investoren (BUY) | 142 aktiv – laufen nicht durch den Abgleich |
| Aktive Hallengesuche zur Miete, geprüft | **70** (ohne 7 Testprofile und 4 Profile, die an einem Kollegen hängen) |
| … mit Vorschlägen | 58 – 31 „frisch“, 27 seit über 180 Tagen nicht bearbeitet |
| Vorschläge gezeigt (höchstens 5 je Gesuch) | 279, über 210 verschiedene Einheiten |
| Passende Objekte insgesamt | 2.859 – ohne Deckel wäre das eine weitere Liste, die niemand liest |
| Passende Flächen, die der Kontakt schon kennt | 82 (herausgenommen) |
| Gesuche, deren Kontakt keinen einzigen Deal hat | 46 von 70; unter den frischen 16 von 33 |
| „Nur neu“, 7 Tage (so sähe eine Wochenmeldung aus) | 15 Gesuche, 44 Vorschläge |
| Angebotsfähige Flächen | 1.310 (1.110 Vermarktung, 200 Altbestand) |

Der dritte Wert von unten ist kein Beweis, dass nichts angeboten wurde – Angebote stehen nur teilweise als
Deal in Propstack (seit Oktober in „300 Mieter“, davor oft nur in der Notiz oder gar nicht).

**Gegenprobe an den echten Angeboten.** Pipeline „300 Mieter“, 86 Deals: 21 hängen an Kontakten ohne
Hallengesuch, bei 11 ist die Einheit heute nicht mehr frei. Von den übrigen 54 hätte der Abgleich **32**
gefunden. Die 22 anderen liegen alle **außerhalb des im Suchprofil gezeichneten Gebiets** (bis 489 km:
München für ein Gesuch um Düsseldorf, Wedel für eines im Sauerland) – Fläche, Höhe und Bezug haben kein
einziges echtes Angebot ausgeschlossen. Die Regeln treffen also, was das Team anbietet; wo das Profil den
Bedarf nicht abbildet, kann kein Abgleich helfen.

**Stichprobe von Hand** (12 zufällige frische Gesuche, 34 Vorschläge gegen die Objektdaten gelesen): 30
plausibel, 4 falsch. Die Ursachen sind seitdem abgestellt: eine als frei geführte Halle mit „Vermietungsstand
100 %“ (jetzt Hinweis und Abzug) und drei Vorschläge für ein Gesuch ohne Gebiet (jetzt nur gezählt).
„Plausibel“ heißt: Lage, Fläche, Höhe und Termin stimmen laut Daten. Ob die Fläche wirklich noch frei ist,
weiß nur der Eigentümer.

**Was dabei am Bestand aufgefallen ist** (alles nur gelesen, nichts geändert):

- **267 angebotsfähige Einheiten ohne Koordinaten** (245 in Vermarktung). Jede Umkreissuche übersieht sie –
  auch Propstacks eigenes Suchprofil-Matching. Hier bekommen 188 eine geschätzte Lage (Projekt, PLZ, Ort);
  79 bleiben ohne.
- **„Lagerfläche teilbar ab“ steht bei 152 Einheiten um den Faktor 1.000 zu klein** im Feld (10.385 m² als
  10.385). Für Propstacks Matching ist die Einheit damit „teilbar ab 10 m²“.
- **174 Einheiten des Altbestands tragen die Objektart „APARTMENT“** (Import 01/2025), sind aber Hallen.
- **10 Einheiten gelten als frei und tragen „Vermietungsstand 100 %“.**
- **Suchprofile:** 6 aktive ohne lesbare Fläche, 2 ohne Gebiet, 7 Testprofile, 4 an Kollegen statt am Kunden;
  37 der 70 seit über einem halben Jahr nicht bearbeitet.

## Grenzen

- Ein Vorschlag ist eine Vorauswahl, kein Angebot. Was unter „prüfen“ steht, ist nicht erledigt.
- „Schon angeboten“ sieht nur, was in Propstack steht (Deals, Notiz). Ein Angebot per Mail ohne Deal wird
  noch einmal vorgeschlagen. Kontakte derselben Firma werden nicht zusammengezogen.
- Hat ein Kontakt mehrere Bedarfe und nur ein Profil, sieht der Abgleich nur das Profil.
- Text wird nach festen Mustern gelesen, nicht verstanden. Ein Gesuch mit zwei Phasen („bis Q3 2.000–3.000 m²,
  danach 5.000–7.000 m²“) wird mit der ersten gelesen.
- Das Bundesland kommt, wo das Feld fehlt, aus den ersten zwei Ziffern der PLZ – an Landesgrenzen ungenau.
- Ankaufsprofile (142) und Kaufobjekte sind nicht Teil des Abgleichs. Das wäre eine zweite Spur.

## Betrieb – noch zu entscheiden

Das Paket läuft bisher nur von Hand. Der Lauf vom 26.11.2026 liegt ohne Namen in `laeufe/2026-11-26.json`;
`--vergleich` zählt später, für wie viele der 279 Vorschläge inzwischen ein Deal angelegt wurde. **Erst
diese Zahl sagt, ob das Radar wirkt** – der Stresstest vom 19.11. hat gezeigt, was passiert, wenn man
Aktivität statt Wirkung misst.

1. **Wohin?** Vorschlag: einmal pro Woche `--nur-neu` als Slack-Nachricht an den jeweiligen Betreuer (rund
   15 Gesuche, 44 Vorschläge über alle; ohne KI, läuft als GitHub-Workflow wie die Handler). Nicht als
   Propstack-Aufgaben – die liest niemand (Stresstest, Befund 1).
2. **Vorauswahl als Deal?** Die Pipeline „300 Mieter“ hat die Stufe „Vorauswahl“. Vorschläge dort anzulegen
   brächte sie an den Ort, an dem Marek arbeitet – ist aber Schreiben an Live-Daten und braucht ein
   Connector-Tool für Deals, das es noch nicht gibt.
3. **Die Datenlücken oben** (Koordinaten, „teilbar ab“, Testprofile) – jede einzeln als Sammeländerung mit
   Probe und Protokoll, nach Freigabe.
