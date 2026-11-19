# Stresstest der Automatisierung – 19.11.2026

Auftrag: „Schau dir an, wer wir sind und was wir machen, entscheide selbst, was sinnvoll ist, und mach es.“
Geprüft wurden Code, Produktionslogs und die Live-Daten in Propstack. **In Propstack, Slack und Asana wurde
nichts geschrieben** – nur gelesen. Alle Änderungen liegen auf dem Branch `ccr-9cae85c4-4jlmdv`, nichts
davon ist auf `main`.

## Urteil

Die Technik ist sorgfältig gebaut. Gemessen wurde bisher aber Aktivität, nicht Wirkung: Läufe waren grün,
Aufgaben wurden angelegt – ob jemand sie erledigt und ob der Import wirklich alles liest, hat niemand
gezählt. Die Zahlen sagen: Der größte Teil dessen, was die Handler erzeugen, wird nie bearbeitet, und der
Kontakt-Import war an mehreren Stellen blind, ohne dass ein Lauf rot wurde.

## Befund 1 – Die Automatisierung liefert in eine Warteschlange, die niemand leert

| | Zahl |
|---|---|
| Offene Aufgaben in Propstack, alle Nutzer | **609** (Lena 510 · Florian 53 · Marek 40 · Denise 6) |
| Review-Sitz 254958, letzte 91 Tage: neu / erledigt | **213 / 26** |
| Alter der offenen Aufgaben am Review-Sitz (Median) | 107 Tage |
| „Newsletter-Vermietung prüfen“: je angelegt / erledigt | **157 / 1** |

„Stufe B“ war als Sicherheitsnetz gedacht: Im Zweifel entscheidet ein Mensch. Das Netz hält nur, wenn der
Mensch die Aufgabe auch öffnet. Die Aufgabenliste in Propstack ist kein Ort, an dem das Team arbeitet –
von Hand angelegte Aufgaben gibt es dort kaum (Denise: 9 insgesamt). Was dort landet, ist abgelegt, nicht
zugestellt.

Dazu kam vermeidbares Rauschen. **129 der 609 offenen Aufgaben** hätten nie entstehen müssen:

| Ursache | Zahl | Beleg |
|---|---|---|
| Dieselbe Vermietung an mehreren Tagen gemeldet → jedes Mal neue Aufgabe | 41 (58 inkl. Überschneidung) | Westring 8 in Dissen: 7 Aufgaben in 14 Tagen |
| Einheit war schon vermietet/abgeschlossen | 40 | Dissen war seit 12.10. abgeschlossen, alle 7 Aufgaben entstanden danach |
| Vollzugsmeldung als Auftrag gelesen | 48 | „neues Objekt angelegt – SEGRO Herford“ wurde zu „Objekt fehlt in Propstack: bitte anlegen“ (26 von 30 Aufgaben dieser Art); 27 Berichte aus Claude-Sitzungen wurden zu „Flächenupdate abgleichen“ |

Der dritte Punkt ist der unangenehmste: Die Automatisierung hat ihre eigenen Erfolgsmeldungen als Arbeit
zurückgespielt.

**Geändert:** Newsletter-Handler legt je Einheit höchstens eine offene Aufgabe an und keine für
abgeschlossene Einheiten. #objekte-Handler überspringt Vollzugsmeldungen vor jeder KI.
`scripts/pruefaufgaben_aufraeumen.py` listet die 129 Aufgaben und schließt sie mit `--apply`.

**Deine Entscheidung:** siehe unten, Punkte 2–4.

## Befund 2 – Der Kontakt-Import lief grün und war halb blind

Aus dem Produktionslog des Laufs vom 19.11.2026 („success“, „Fehler: 0“) und der Laufhistorie:

- **Der Freitag wurde nie gelesen.** Der Lauf kam Montag bis Freitag und las 24 Stunden. Der Freitagslauf
  deckt den Donnerstag, der Montagslauf den Sonntag – der ganze Freitag fiel jede Woche weg. Dasselbe beim
  Visitenkarten-Import. Zusätzlich riss jede Verspätung des Starts eine Lücke (zwischen den Läufen vom 16. und 17.11.: 72 Minuten
  am Montagmorgen).
- **Apollo wies jeden Aufruf mit 401 ab** (11 von 11). Der Schlüssel stand im Body; Apollo verlangt ihn im
  Header `x-api-key`. Seit wann, lässt sich nicht mehr sagen – ältere Logs sind gelöscht.
- **Ein Postfach stieß an die 50-Mail-Grenze** (Denise: „Found 50 emails“). Was darüber lag, fiel still weg.
- **18 von 19 erkannten Kontakten waren längst in Propstack.** Jeder lief vorher durch Extraktion, Apollo und
  Kategorisierung mit Websuche – die Dublettenprüfung kam zuletzt.
- **Zwei Antworten der KI waren nicht lesbar** und zählten als „kein Kontakt“.
- Scheitert die Firmensuche, wurde die Firma neu angelegt (Dublette auf Verdacht). Scheiterte die
  Verknüpfung, stand der Kontakt trotzdem als sauber angelegt in Slack.

Alle 100 abrufbaren Läufe seit Juni sind „success“. Grün hieß hier nur: Das Programm ist nicht abgestürzt.

**Geändert:** beide Importe täglich mit 48 Stunden Rückblick; Gmail seitenweise; ist der Absender schon in
Propstack, endet die Mail ohne KI-Aufruf; Apollo mit Header (laut Doku, nicht live erprobt);
Telefonnummern wie im Connector (`+49 (0) 151 …` → `+49 151 …`); was schiefgeht, steht in der
Slack-Zusammenfassung und macht den Lauf rot.

**Erwartung nach dem Merge:** Der erste Lauf kann rot sein – genau das ist jetzt die Absicht. Bleibt Apollo
bei 401, ist der Schlüssel selbst ungültig (in Apollo unter Settings → Integrations → API prüfen).

## Befund 3 – Der scharfe #objekte-Handler tut fast nichts automatisch, hatte aber offene Flanken

Stufe A (selbst „vermietet“ setzen und Deals absagen) lief seit Juli **zweimal**. Der Handler ist praktisch
ein Aufgaben-Erzeuger. Die Wege in Stufe A waren trotzdem weiter als nötig:

- Abgesagt wurde jeder offene Deal der Einheit – auch der des Mieters selbst in der Abschluss-Phase und
  Deals aus Verkaufs-Pipelines (321 Deals an Einheiten liegen in „200 …“ und „Kaltenkirchen“). Der Filter
  auf `category` war wirkungslos: Das Feld gibt es in den Zeilen nicht.
- „Halle 2 ist vermietet“ hätte alle Einheiten der Adresse geschlossen – Einheiten eines Projekts erben
  dessen Adresse.
- Eine Quadratmeterzahl traf immer die „nächstliegende“ Einheit: „3.000 m²“ → 7.666 m². „7666.0“ wurde als
  76.660 gelesen.

Passiert ist davon nach Datenlage nichts. **Geändert**, ohne die fünf festgelegten Regressionsfälle vom
08.07.2026 anzufassen; Einzelheiten im README des Pakets.

Offen: Stufe A setzt nur `rented=true`. Deine Regel vom 11.11.2026 schließt mit `rented: true` **und**
Status 163676. Am 19.11. standen 7 Einheiten als vermietet und zugleich in „Vermarktung“.

## Befund 4 – Zwei Status-Angaben laufen auseinander

Propstack führt für jede Einheit zwei Angaben nebeneinander: den **Objekt-Status** (Akquise … Abgeschlossen)
und euer Custom-Feld **„Status Logistik“** (Aktiv/Inaktiv), dazu das Kennzeichen „vermietet“. Sie
widersprechen sich an vielen Stellen (2.536 aktive Einheiten):

| Was | Zahl | Folge |
|---|---|---|
| Kein Objekt-Status, aber „Aktiv“ und frei | **204** | Fast alle aus dem Import 01/2025. Jede Suche „nach Status“ übersieht sie – der Connector-Filter, das Dashboard, anfangs auch mein Gesuch-Abgleich. |
| Weder Objekt-Status noch „Status Logistik“ | 263 | Überwiegend 2026 neu angelegt – nicht einzuordnen, ob verfügbar. |
| „Abgeschlossen“, aber „Aktiv“ | 18 | Nach euren Feldregeln hängt am Aktiv-Feld, was in Exposéversand und Website bleibt. |
| „Vermarktung“, aber vermietet oder „Inaktiv“ | 14 | Erscheinen in Status-Auswertungen als verfügbar. |
| „Abgeschlossen“, aber nicht als vermietet markiert | 124 | |
| Kein Objekt-Status und „Inaktiv“ | 463 | In Ordnung – bewusst stillgelegter Altbestand. |

Insgesamt haben **933 Einheiten (37 %) keinen Objekt-Status**. Der Bestand, der wirklich angeboten werden
kann, ist damit nicht 1.123 („Vermarktung“ und frei), sondern rund **1.320** – 204 davon sieht nur, wer
nach „Status Logistik“ sucht.

Das wirkt in die Automatisierung hinein: 29 der 156 Newsletter-Aufgaben zeigten auf Einheiten ohne Status.
Außerdem hängen 82 offene Deals an vermieteten oder abgeschlossenen Einheiten (80 davon ohne Pipeline).

Der gepflegte Kern ist ordentlich: Fläche bei 99 % bestimmbar, Hallenhöhe bei 71 %, Preisangabe bei 83 %.

Nichts geändert – das ist eine Entscheidung (Punkt 5). *Berichtigung im Lauf der Prüfung:* Ich hatte die
Datensätze aus dem Import 01/2025 zuerst für leere Karteileichen gehalten (kein Status, keine Fläche im
Standardfeld, kein Betreuer, kein Bild). Das war falsch: Sie tragen eure Custom-Felder und wurden im August
und September überarbeitet. Archivieren wäre die falsche Antwort gewesen.

## Befund 5 – Automatisiert ist die Pflege, nicht das Geschäft

Sechs Automatisierungen halten den Bestand aktuell. Keine beantwortet die Frage, mit der ihr Geld verdient:
*Welche unserer Flächen passen auf dieses Gesuch?* Dabei geben die Daten das schon her:

| Gesuch (Website) | Kandidaten in Vermarktung | zusätzlich im Altbestand ohne Status |
|---|---|---|
| Düsseldorf/Haan, ~10.000 m² + Werkstatt | 10 | 13 |
| Berlin-Reinickendorf, Kühlfläche 2.000 m² | 12 | 3 |
| Östliches Ruhrgebiet, 30.000–40.000 m² | 2 | 7 |
| Wermelskirchen +30 km, 8.000–12.000 m², ≥ 9 m | 13 | 11 |
| Mönchengladbach, Interim 3.000 m² | 6 | 8 |
| Duisburg/Essen/MG, 4.000–5.000 m², ≥ 6 Rampen | 21 | 23 |
| **Summe** | **64** | **65** |

Die rechte Spalte ist der Punkt aus Befund 4: Die Hälfte der möglichen Treffer liegt in Datensätzen, die
eine Suche nach Status nicht zeigt. Sie gehören vor einem Angebot geprüft, aber sie gehören auf die Liste.

`scripts/gesuch_matching.py` macht das für jedes Gesuch in unter einer Minute (nur lesend). Drei Lücken
bremsen: **20 % der Einheiten haben keine Koordinaten** (eine Umkreissuche sieht sie nicht), **Rampen sind
nur bei 42 % gepflegt**, und **„Bezug“ ist Freitext** („sofort“, „Q2 2027“, „Datum“) – nach Verfügbarkeit
lässt sich nicht filtern. Kühlung ist an 3 von 1.320 Einheiten gepflegt.

Wenn du die nächste Stunde Pflegeaufwand vergibst: in diese drei Felder, nicht in einen siebten Handler.

## Was geändert wurde

Branch `ccr-9cae85c4-4jlmdv`, 478 Tests grün (Python 3.12 und 3.13), vorher 250.

| Commit | Inhalt |
|---|---|
| `9a43d55` | Newsletter: keine Aufgabe, wenn schon eine offen ist oder die Einheit abgeschlossen ist; Aufräum-Skript |
| `d18ba21` | Kontakt-Import: Telefonnummern wie im Connector |
| `2b4e4de` | Kontakt-Import: lückenlos lesen, erst prüfen dann KI, Apollo-Header, Fehler sichtbar |
| `7332bf9` | #objekte: Vollzugsmeldungen, Absage-Sicherung, Größen- und Adressprüfung; alle Handler: Fehler machen den Lauf rot |
| `eb8d156` | #events: kein Haken ohne Asana-Aufgabe; Personalkarussell vorsichtiger |
| folgende | Gesuch-Abgleich, `CLAUDE.md`, dieser Bericht |

## Was nicht geprüft ist

- Kein Handler ist nach den Änderungen gegen Slack oder die KI gelaufen (dafür fehlen hier die Schlüssel).
  Geprüft ist mit Tests und – wo es um Propstack-Lesezugriffe geht – gegen die Live-Schnittstelle.
- Der Apollo-Fix folgt der Dokumentation, ein echter Aufruf steht aus.
- Das Schließen von Aufgaben (`done=true`) ist nicht erprobt; das Skript prüft deshalb die erste Aufgabe
  einzeln und bricht sonst ab.
- Der Connector (`propstack-mcp`) wurde nicht geprüft. Aufgefallen ist dort nur: `aggregate` für Deals nach
  Kategorie meldet „-339 ohne Zuordnung“ (die Kategorien überlappen).
- Die Laufhistorie in GitHub hat zwei Lücken (02.–22.10. und 31.10.–12.11.). Die Läufe haben stattgefunden –
  Aufgaben aus diesen Tagen belegen es –, nur die Einträge fehlen.
- Der Git-Verlauf von `main` enthält nach Mustersuche keine Schlüssel; die übrigen 30 Branches wurden nicht
  durchsucht.

## Was du entscheiden musst

1. **Mergen.** Empfehlung: ja, als Pull Request, damit die CI läuft. Danach laufen die Importe täglich
   (auch am Wochenende), und Läufe mit Fehlern sind rot.
2. **Die 129 Aufgaben schließen.** `python scripts/pruefaufgaben_aufraeumen.py` zeigt die Liste, `--apply`
   schließt (erst eine als Probe, mit Protokoll und `--undo`). Empfehlung: ja.
3. **Wohin mit Prüfaufträgen?** Propstack-Aufgaben werden nicht abgearbeitet. Entweder jemand bekommt dafür
   feste Zeit – oder die Handler antworten nur noch im Slack-Thread und legen keine Aufgabe mehr an.
   Empfehlung: das Zweite. Im Kanal wird gearbeitet, in der Aufgabenliste nicht.
4. **Newsletter-Handler behalten?** 157 Aufgaben, eine erledigt. Empfehlung: abschalten oder auf eine
   wöchentliche Sammelnachricht in Slack umstellen. Im heutigen Zuschnitt erzeugt er keinen Nutzen.
5. **Eine Status-Angabe, die gilt.** Entweder der Objekt-Status wird für die 204 aktiven Einheiten ohne
   Status nachgezogen (und für die 263 ohne beides entschieden), oder „Status Logistik“ wird zur einzigen
   Wahrheit und alle Werkzeuge filtern danach. Empfehlung: Objekt-Status nachziehen – das kann eine Sitzung
   über den Connector als Sammeländerung mit Rücknahme vorbereiten. Die 18 „Abgeschlossen, aber Aktiv“
   gleich mit.
6. **Stufe A soll auch den Status setzen?** Empfehlung: ja, wie in deiner Regel vom 11.11.
7. **Apollo-Schlüssel prüfen**, falls der erste Lauf nach dem Merge weiter 401 meldet.
8. **Personalkarussell nicht scharf schalten**, bevor die vier offenen Punkte im README erledigt sind.
9. **Schlüssel in der Cloud-Umgebung.** Dort liegen Propstack-Schlüssel mit Schreibrecht. Jede Sitzung kann
   damit am Connector vorbei schreiben – ohne Write-Log, ohne Dublettenprüfung. Empfehlung: durch einen
   Nur-Lese-Schlüssel ersetzen, falls Propstack das anbietet, sonst entfernen.
10. **Aufräumen im Repo:** PR #2 („Kromeich Heroes“, offen seit April) und rund 30 alte Branches.

## Nachrechnen

```bash
python scripts/pruefaufgaben_aufraeumen.py            # die 129 Aufgaben, nur lesend
python scripts/gesuch_matching.py --lat 51.195 --lng 6.44 --umkreis 20 --flaeche 2000-4500 --hoehe 6 --rampen 2
pytest tests/ -q
```
