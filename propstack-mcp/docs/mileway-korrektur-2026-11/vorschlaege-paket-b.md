# Paket B – Vorschläge für die 15 Mileway-Standorte

Stand 10.11.2026: **umgesetzt.** Dieses Dokument zeigt den Vorschlag, wie er zur Freigabe vorlag. Die tatsächlich geschriebenen Texte stehen in `plan-b.json`, die Abweichungen vom Vorschlag im Kopf von `korrekturliste.md`.

Entscheidungen von Florian Brimmers am 10.11.2026: 1 ja · 2 „Gesamtfläche ist bei uns Halle plus Mezzanine“ (Hallenfläche deshalb 4.115 m²) · 3 ja · 4 ja · 5 nein, die Namen bleiben · 6 (Köln, Rampentore) offen.

## So sind die Zahlen entstanden

- Jede Entfernung ist eine berechnete Fahrstrecke vom Standort (seine Koordinaten in Propstack) zum Ziel, keine Luftlinie und keine Schätzung.
- Ziele aus OpenStreetMap: Autobahn-Anschlussstellen (gemessen bis zur Auffahrt), Bundesstraßen, nächste Haltestelle, nächster Bahnhof.
- Flughäfen: gemessen bis zum Terminal. Häfen: gemessen bis zu einem Punkt im Hafengebiet – auf einen Kilometer genau ist das nicht.
- Weitere Autobahnen stehen nur dabei, wenn sie höchstens 10 km entfernt sind, Bundesstraßen ebenso.
- Nennt eine Haltestelle die Straße des Objekts, steht nur „Nächste Bushaltestelle“.
- Die Einleitung ist der bisherige Text des Eigentümers, gekürzt, ohne Adresse und ohne den Eigennamen des Gewerbeparks.

## Was du entscheiden musst

1. **Lage, Ausstattung, Beschreibung so schreiben?** Für alle 15 Standorte oder mit Änderungen je Standort.
2. **Wesseling (6373761):** Mileway nennt 6.585 m² „inkl. 1.420 m² Büro und ca. 1.050 m² Mezzanine“, im Text aber 2.730 + 2.435 = 5.165 m² Lager. Die Gesamtfläche steht jetzt auf 5.165 m² (Halle plus Mezzanine). Offen ist, ob die Hallenfläche dann 4.115 m² statt 5.165 m² heißen muss.
3. **Aachen, Halle 1 (6373958):** Laut Text besteht die Halle aus zwei Zonen zu je rund 1.200 m² und einer Mezzanine mit etwa 1.375 m². Im Feld Hallenfläche stehen die vollen 3.774 m², das Feld Mezzanine ist leer. Soll ich aufteilen (Halle 2.399 m², Mezzanine 1.375 m², Gesamt bleibt 3.774 m²)? Dazu aus dem Text: Rampentore 6, ebenerdige Tore 1.
4. **Kriftel:** Die Beschreibung nennt „rund 3.050 m² Lagerfläche sowie ca. 500 m² Bürofläche“. Laut Mileway-Tabelle sind die 3.050 m² inklusive Büro, die Felder sagen 2.550 m² Halle. Text auf 2.550 m² ändern?
5. **Eigennamen der Gewerbeparks** („Forum Radefeld“, „Hansepark“): aus den Beschreibungen nehmen? Sie verraten den Standort, obwohl „Adresse ausblenden“ an ist. Im Vorschlag als „optional“ markiert.
6. **Köln, Rampentore:** Die Seite sagt „Rampentore (vorderseitig)“ ohne Zahl und ohne Zuordnung zu einer Einheit. In welches Feld welcher Einheit das gehört, kann ich nicht belegen.

## Was nur von Hand geht

- „Wesentlicher Energieträger“ lässt sich über die Schnittstelle nicht setzen. Belegt ist er an vier Standorten:
  - Reinbek: Erdgas (Verbrauchsausweis: Strom 1 kWh/(m²a), Wärme 126 kWh/(m²a))
  - Gottmadingen: Erdgas (Verbrauchsausweis: Strom 4 kWh/(m²a), Wärme 104 kWh/(m²a))
  - Pleidelsheim: Erdgas (zwei Verbrauchsausweise: Strom 120 / 39 kWh/(m²a), Wärme 166 / 111 kWh/(m²a))
  - Köln: Erdgas (Verbrauchsausweis: Strom 31 kWh/(m²a), Wärme 116 kWh/(m²a))
- Für die übrigen elf Standorte schreibt Mileway „Ein Energieausweis ist noch in Bearbeitung“.

## Was die Mileway-Seiten nicht hergeben

Bodentragkraft, Grundstücksfläche, Zahl der Stellplätze und LKW-Stellplätze, WGK, Beleuchtung, Sprinkler, Zertifizierung und „teilbar ab“ stehen auf keiner der 15 Seiten. Diese Felder bleiben leer, bis jemand die Angaben beim Eigentümer erfragt.
Die fünf Einheiten mit einem Wort im Feld „Rampentore“ bleiben wie sie sind; eine Zahl nennt Mileway nur für Aachen (siehe Entscheidung 3).

## Wesseling – Projekt 613115

### Lage (neu)

```
Die Immobilie befindet sich in Wesseling, einem etablierten Wirtschaftsstandort zwischen den Metropolregionen Köln und Bonn. Die zentrale Lage im Rheinland bietet eine ausgezeichnete Anbindung an die regionalen und überregionalen Verkehrswege.

Autobahnen:
- A 555 (Anschlussstelle Wesseling): ca. 0,7 km
- A 553 (Anschlussstelle Brühl-Ost): ca. 6,4 km

ÖPNV:
- Bushaltestelle Akademie Eichholz: ca. 0,2 km
- Bahnhof Sechtem: ca. 4,3 km

Häfen:
- Hafen Köln-Godorf: ca. 7,9 km

Flughäfen:
- Flughafen Köln/Bonn: ca. 25 km
```

### Ausstattung (neu)

- Hochregallager mit ca. 2.730 m², lichte Höhe 12,0 m
- Kommissionierungsfläche mit ca. 2.435 m², lichte Höhe 6,0 m
- Mezzanine mit einer Traglast von 0,5 kN
- Showroom im vorderen Bereich
- Separater Bürotrakt
- Großzügige Zufahrt und Rangierflächen
- Zahlreiche Stellplätze auf dem Grundstück
- Vermietung ausschließlich als Single-Tenant-Objekt

### Einheiten

- 6373761 (Gesamtfläche): abgeschnittene Beschreibung vervollständigt

## Castrop-Rauxel – Projekt 613116

### Lage (neu)

```
Die Immobilie liegt im Stadtteil Merklinde an der nordöstlichen Stadtgrenze von Castrop-Rauxel, in direkter Nachbarschaft zu Dortmund. Die Lage im nördlichen Ruhrgebiet sichert eine sehr gute Erreichbarkeit.

Autobahnen:
- A 40 (Anschlussstelle Dortmund-Lütgendortmund): ca. 3,5 km
- A 45 (Anschlussstelle Dortmund-Hafen): ca. 4,4 km
- A 42 (Anschlussstelle Castrop-Rauxel): ca. 4,6 km

Bundesstraßen:
- B 235: ca. 0,9 km
- B 226: ca. 8,3 km

ÖPNV:
- Bushaltestelle Johannesstraße: ca. 0,7 km
- Haltepunkt Castrop-Rauxel Merklinde: ca. 0,5 km

Häfen:
- Hafen Dortmund: ca. 10 km

Flughäfen:
- Flughafen Dortmund: ca. 25 km
- Flughafen Düsseldorf: ca. 55 km
```

### Ausstattung (neu)

- Stellplätze vor Ort
- Freifläche zusätzlich anmietbar

## Melle – Projekt 613117

### Lage (neu)

```
Die Immobilie befindet sich in Melle. Über die A 30 ist der Standort an die überregionale Verkehrsachse zwischen den Niederlanden, Osnabrück und Bad Oeynhausen angebunden; von dort besteht Anschluss an die A 1, A 33 und A 2.

Autobahnen:
- A 30 (Anschlussstelle Melle-West): ca. 4,2 km

ÖPNV:
- Nächste Bushaltestelle: ca. 0,2 km
- Bahnhof Melle: ca. 4,2 km

Häfen:
- Hafen Osnabrück: ca. 30 km

Flughäfen:
- Flughafen Münster/Osnabrück: ca. 58 km
- Flughafen Hannover: ca. 123 km
```
Hinweis: Name der Haltestelle („Oldendorf, Betonstraße“) weggelassen – er nennt die Straße des Objekts.

### Ausstattung (neu)

- Parkplätze vor Ort
- Vermietung ausschließlich als Gesamtfläche

### Beschreibung (Änderung)

- Adresse: „Die Immobilie an der Betonstraße 8 in Melle umfasst“ → „Die Immobilie in Melle umfasst“

## Weiden – Projekt 613118

### Lage (neu)

```
Die Immobilie befindet sich in Weiden in der Oberpfalz, einem etablierten Wirtschaftsstandort im Nordosten Bayerns. Die verkehrsgünstige Lage bietet eine hervorragende Anbindung an die wichtigen Verkehrsachsen der Region sowie an die angrenzenden Märkte in Tschechien.

Autobahnen:
- A 93 (Anschlussstelle Weiden-Nord): ca. 1,7 km

Bundesstraßen:
- B 22: ca. 0,5 km
- B 15: ca. 3,2 km

ÖPNV:
- Nächste Bushaltestelle: weniger als 0,1 km
- Haltepunkt Altenstadt (Waldnaab): ca. 3,3 km

Häfen:
- Hafen Regensburg: ca. 87 km

Flughäfen:
- Flughafen Nürnberg: ca. 122 km
```
Hinweis: Name der Haltestelle („Industriegebiet Am Forst“) weggelassen – er nennt die Straße des Objekts.

### Ausstattung (neu)

- Vier Überladebrücken
- Für Sprinter und große Lkw ausgelegt
- Großzügige Rangierfläche

### Einheiten

- 6373953 (Halle): abgeschnittene Beschreibung vervollständigt

## Kriftel – Projekt 613119

### Lage (neu)

```
Die Immobilie befindet sich in Kriftel, einem etablierten Gewerbestandort im wirtschaftsstarken Rhein-Main-Gebiet. Die zentrale Lage zwischen Frankfurt am Main, Wiesbaden und dem Flughafen Frankfurt bietet eine ausgezeichnete regionale und überregionale Erreichbarkeit.

Autobahnen:
- A 66 (Anschlussstelle Hattersheim-Ost): ca. 0,9 km

Bundesstraßen:
- B 40: ca. 3,2 km
- B 519: ca. 3,8 km

ÖPNV:
- Bushaltestelle Hofheimer Straße: ca. 1,3 km
- Haltepunkt Kriftel: ca. 0,5 km

Häfen:
- Osthafen Frankfurt: ca. 24 km

Flughäfen:
- Flughafen Frankfurt am Main: ca. 12 km
```

### Ausstattung (neu)

- Großzügige Rangierfläche
- Bürofläche im 1. Obergeschoss
- Single-Tenant-Objekt

### Beschreibung (Änderung)

- Adresse: „Die Immobilie am Holzweg 24 in Kriftel bietet“ → „Die Immobilie in Kriftel bietet“

## Aachen – Projekt 613120

### Lage (neu)

```
Die Immobilie befindet sich in etablierter Gewerbelage in Aachen, südwestlich des Autobahnkreuzes der A 4 und A 44. Eine namhafte Mieterschaft bildet das unmittelbare Umfeld.

Autobahnen:
- A 544 (Anschlussstelle Rothe Erde): ca. 1,7 km
- A 4 (Anschlussstelle Aachen-Zentrum): ca. 4,4 km
- A 44 (Kreuz Aachen): ca. 5,4 km

Bundesstraßen:
- B 1: ca. 3,4 km
- B 258: ca. 3,6 km

ÖPNV:
- Bushaltestelle Elleter Feld: ca. 0,2 km
- Bahnhof Aachen-Rothe Erde: ca. 3,7 km

Häfen:
- Hafen Lüttich (Trilogiport): ca. 61 km

Flughäfen:
- Flughafen Maastricht Aachen: ca. 37 km
- Flughafen Köln/Bonn: ca. 82 km
```

### Ausstattung (neu)

- Vordere Zone mit rund 1.200 m², Höhe etwa 4,00 m
- Hochregalfähiges Lager mit rund 1.200 m², Höhe ca. 9,95 m
- Mezzanine im Obergeschoss mit etwa 1.375 m², Höhe circa 4,45 m
- Alle Tore elektrisch bedienbar
- Sanitär- und Versorgungsanschlüsse vorhanden
- Stellplätze in der Tiefgarage zusätzlich anmietbar
- Parkplätze vor Ort

### Einheiten

- 6373958: Vorspann „Allee 50: …“ → „Halle 1: …“ (alte Einheitennummer mit Adresse)
- 6373959: Vorspann „Allee 54: …“ → „Halle 2: …“ (alte Einheitennummer mit Adresse)

## Bergkamen – Projekt 613121

### Lage (neu)

```
Die Immobilie liegt in Bergkamen in einem gewerblich geprägten Umfeld. Die Autobahnen A 1 und A 2 sind schnell erreichbar, wodurch regionale und überregionale Verkehre zügig angebunden sind.

Autobahnen:
- A 1 (Anschlussstelle Hamm/Bergkamen): ca. 1,6 km
- A 2 (Kamener Kreuz): ca. 8,1 km

Bundesstraßen:
- B 233: ca. 3,8 km
- B 54: ca. 6,8 km

ÖPNV:
- Bushaltestelle Gewerbepark: ca. 0,3 km
- Bahnhof Werne a d Lippe: ca. 6,3 km

Häfen:
- Hafen Hamm: ca. 11 km

Flughäfen:
- Flughafen Dortmund: ca. 21 km
- Flughafen Düsseldorf: ca. 105 km
```

### Ausstattung (neu)

- Heizung teilweise vorhanden
- Großzügige Rangierflächen
- Stellplätze am Objekt

## Dormagen – Projekt 613122

### Lage (neu)

```
Die Immobilie befindet sich in Dormagen, einem etablierten Gewerbestandort zwischen den Wirtschaftsregionen Köln und Düsseldorf. Im direkten Umfeld befinden sich zahlreiche Unternehmen aus Industrie, Gewerbe und Dienstleistung.

Autobahnen:
- A 57 (Anschlussstelle Dormagen): ca. 1,1 km

Bundesstraßen:
- B 9: ca. 3,6 km

ÖPNV:
- Bushaltestelle Alte Heerstraße: ca. 0,7 km
- Bahnhof Dormagen: ca. 1,8 km

Häfen:
- Hafen Neuss: ca. 17 km

Flughäfen:
- Flughafen Düsseldorf: ca. 27 km
```

### Ausstattung (neu)

- Sozialflächen
- Ausreichend Parkplätze

## Reinbek – Projekt 613123

### Lage (neu)

```
Die Flächen befinden sich in einem Gewerbepark in Reinbek, nur 16 km östlich von Hamburg.

Autobahnen:
- A 24 (Anschlussstelle Reinbek): ca. 4,8 km
- A 25 (Anschlussstelle Hamburg-Bergedorf): ca. 7,4 km
- A 1 (Anschlussstelle Hamburg-Öjendorf): ca. 7,6 km

Bundesstraßen:
- B 207: ca. 4,9 km
- B 5: ca. 7,4 km

ÖPNV:
- Nächste Bushaltestelle: ca. 0,2 km
- Haltepunkt Reinbek: ca. 2,5 km

Häfen:
- Hafen Hamburg (Burchardkai): ca. 33 km

Flughäfen:
- Flughafen Hamburg: ca. 27 km
```
Hinweis: Name der Haltestelle („Reinbek, Borsigstraße“) weggelassen – er nennt die Straße des Objekts.

### Ausstattung (neu)

- Ebenerdige Andienung
- Stellplätze vor Ort

### Beschreibung (Änderung)

- Adresse: „Der Gewerbepark Borsigstraße 4–6 bietet“ → „Der Gewerbepark bietet“

## Barbing – Projekt 613124

### Lage (neu)

```
Der Gewerbepark liegt verkehrsgünstig an der Autobahn A 3, ca. 12 Kilometer von Regensburg entfernt. Busverbindungen verbinden den Standort mit den umliegenden Gemeinden und der Stadt Regensburg.

Autobahnen:
- A 3 (Anschlussstelle Rosenhof): ca. 0,4 km

Bundesstraßen:
- B 8: ca. 0,4 km
- B 15: ca. 8,0 km

ÖPNV:
- Bushaltestelle Unterheising Benzstraße: ca. 0,2 km
- Haltepunkt Regensburg-Burgweinting: ca. 9,2 km

Häfen:
- Hafen Regensburg: ca. 12 km

Flughäfen:
- Flughafen München: ca. 114 km
```

### Ausstattung (neu)

- Lastenaufzug (2 t)
- Anlieferungsrampe
- Verlade- bzw. Kommissionierbereich
- Ebenerdige Andienung
- Treppenhausverbindung zwischen den Gebäudeteilen

### Beschreibung (Änderung)

- Tippfehler: „durhcgeführt“ → „durchgeführt“

## Gottmadingen – Projekt 613125

### Lage (neu)

```
Der Standort liegt in einer wachsenden Wirtschaftsregion an der Grenze zwischen Deutschland und der Schweiz. Die Schweizer Grenze ist nur zwei Kilometer entfernt, bis Konstanz und zum Bodensee sind es etwas mehr als 30 Minuten Fahrt.

Autobahnen:
- A 81 (Anschlussstelle Gottmadingen): ca. 3,9 km

Bundesstraßen:
- B 34: ca. 0,2 km
- B 314: ca. 5,9 km

ÖPNV:
- Nächste Bushaltestelle: ca. 0,1 km
- Bahnhof Gottmadingen: ca. 1,5 km

Häfen:
- Rheinhafen Basel: ca. 112 km

Flughäfen:
- Flughafen Zürich: ca. 52 km
```
Hinweis: Name der Haltestelle („Gottmadingen, Industriepark West“) weggelassen – er nennt die Straße des Objekts.

### Ausstattung (neu)

- Glasfaseranschluss (Ausbau des Netzes geplant)
- Bürogebäude mit fünf Vollgeschossen, Flächen flexibel teilbar
- Ausreichend Parkplätze

### Beschreibung (Änderung)

- Adresse (die Straße heißt „Industriepark“): „Im Industriepark Gottmadingen finden Sie vielseitige Lösungen“ → „An diesem Standort finden Sie vielseitige Lösungen“

### Einheiten

- 6373972 (Halle 204): abgeschnittene Beschreibung vervollständigt
- 6373973 (Halle 239): abgeschnittene Beschreibung vervollständigt
- 6373973 (Halle 239): Felder aus dem Text – Hallenhöhe 8,2 m; Rampentore 2 („zwei Verladerampen für LKW“)
- 6373974 (Halle 306): abgeschnittene Beschreibung vervollständigt

## Leipzig – Projekt 613126

### Lage (neu)

```
Die Flächen befinden sich im Norden von Leipzig in einem etablierten Gewerbeumfeld. Der Standort ist an das Autobahnkreuz Leipzig-Mitte mit der Autobahn A 14 und der Bundesstraße B 2 angebunden.

Autobahnen:
- A 14 (Anschlussstelle Leipzig-Nord): ca. 1,5 km

Bundesstraßen:
- B 6: ca. 5,2 km
- B 2: ca. 7,2 km

ÖPNV:
- Bushaltestelle GVZ Nord, Porschestraße: ca. 0,3 km
- Bahnhof Leipzig-Wahren: ca. 7,9 km

Häfen:
- Hafen Halle (Saale): ca. 34 km

Flughäfen:
- Flughafen Leipzig/Halle: ca. 5,9 km
```

### Ausstattung (neu)

- Ausreichend Parkplätze

### Beschreibung (Änderung)

- optional – Eigenname des Gewerbeparks: „Das Forum Radefeld bietet“ → „Der Gewerbepark bietet“

## Pleidelsheim – Projekt 613127

### Lage (neu)

```
Die Multitenant-Anlage befindet sich in Pleidelsheim und ist sehr gut angebunden. Die Stadt Ludwigsburg ist nur 20 Fahrminuten entfernt.

Autobahnen:
- A 81 (Anschlussstelle Pleidelsheim): ca. 2,1 km

Bundesstraßen:
- B 27: ca. 6,2 km
- B 328: ca. 8,5 km

ÖPNV:
- Bushaltestelle Robert-Bosch-Straße: ca. 0,3 km
- Bahnhof Freiberg (Neckar): ca. 4,0 km

Häfen:
- Hafen Stuttgart: ca. 34 km
- Hafen Heilbronn: ca. 36 km

Flughäfen:
- Flughafen Stuttgart: ca. 48 km
```

### Ausstattung (neu)

- Tiefgarage
- Ausreichend Stellplätze
- Büroflächen frisch renoviert und bezugsfertig
- Teeküche auf Wunsch durch den Vermieter

### Einheiten

- 6373980 (Gebäude 17 EG): Felder aus dem Text – Baujahr 1991

## Köln – Projekt 613128

### Lage (neu)

```
Die Immobilie befindet sich in Köln-Porz, einem attraktiven Wirtschaftsstandort mit hoher Nachfrage nach Gewerbeflächen. Die Lage zeichnet sich durch eine hervorragende Verkehrsanbindung an das Autobahnnetz und den öffentlichen Nahverkehr aus.

Autobahnen:
- A 59 (Anschlussstelle Rath): ca. 0,6 km
- A 559 (Anschlussstelle Köln-Gremberghoven): ca. 0,7 km
- A 3 (Anschlussstelle Königsforst): ca. 4,4 km

Bundesstraßen:
- B 8: ca. 1,6 km
- B 55a: ca. 7,1 km

ÖPNV:
- Bushaltestelle Maarhäuser Weg: ca. 0,3 km
- Haltepunkt Köln Airport-Businesspark: ca. 2,3 km

Häfen:
- Hafen Köln-Niehl: ca. 15 km

Flughäfen:
- Flughafen Köln/Bonn: ca. 8,1 km
```

### Ausstattung (neu)

- 24-Stunden-Zugang
- Ebenerdige Hallenandienung (rückseitig)
- Rangierflächen
- Ausreichend Stellplätze

### Beschreibung (Änderung)

- optional – Eigenname des Gewerbeparks; „unsere“ ist die Stimme des Eigentümers: „Unsere Flächen im Hansepark sind“ → „Die Flächen im Gewerbepark sind“

## Neuss – Projekt 613129

### Lage (neu)

```
Der Standort in Neuss ist sowohl mit öffentlichen Verkehrsmitteln als auch mit dem Auto bequem erreichbar. Über die A 46 und das Autobahnkreuz Neuss-Süd besteht eine direkte Verbindung zur A 57.

Autobahnen:
- A 46 (Anschlussstelle Neuss-Uedesheim): ca. 1,1 km
- A 57 (Anschlussstelle Neuss-Norf): ca. 3,8 km

Bundesstraßen:
- B 9: ca. 0,6 km
- B 326: ca. 6,5 km

ÖPNV:
- Nächste Bushaltestelle: ca. 0,3 km
- Haltepunkt Neuss Allerheiligen: ca. 2,8 km

Häfen:
- Hafen Düsseldorf: ca. 11 km
- Hafen Neuss: ca. 11 km

Flughäfen:
- Flughafen Düsseldorf: ca. 17 km
```
Hinweis: Name der Haltestelle („Fuggerstraße“) weggelassen – er nennt die Straße des Objekts.

### Ausstattung (neu)

- Parkplatz vor Ort
- Integrierte Bürofläche, direkt an die Halle angebunden

### Beschreibung (Änderung)

- Adresse: „Die angebotene Gewerbefläche in der Fuggerstraße 2 umfasst“ → „Die angebotene Gewerbefläche umfasst“

### Einheiten

- 6373984: Vorspann „Fuggerstraße 2: …“ → „Halle: …“ (alte Einheitennummer mit Adresse)

