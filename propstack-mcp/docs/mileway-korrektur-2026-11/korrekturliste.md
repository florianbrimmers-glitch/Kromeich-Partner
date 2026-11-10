# Korrekturliste: Mileway-Lauf vom 09.11.2026

> **Stand 10.11.2026, später Nachmittag: Paket A und Paket B sind umgesetzt.**
>
> **Paket A** (Freigabe Florian Brimmers: „so machen“): 15 Projekte, 26 Einheiten und die Einheit in Ratingen über den Connector korrigiert, 26 Eigentümer verknüpft.
> Ein Kontroll-Lesen aller 42 Datensätze ergab keine Abweichung vom Plan.
>
> **Paket B** (Freigabe: „1. ja“ mit den Entscheidungen 2 bis 6):
> - 15 Projekte und 26 Einheiten haben Lage und Ausstattung als Liste; die Lage nennt berechnete Fahrstrecken statt Luftlinie.
> - 6 Projekte und 18 Einheiten haben eine bereinigte Beschreibung: Adresse gestrichen, ein Tippfehler behoben, fünf abgeschnittene Texte vervollständigt, Straßenname im Vorspann durch die Einheitennummer ersetzt.
> - Felder: Wesseling (Hallenfläche 4.115 m², Mezzanine 1.050 m²), Aachen Halle 1 (Hallenfläche 2.399 m², Mezzanine 1.375 m², Rampentore 6, ebenerdige Tore 1), Gottmadingen Halle 239 (Hallenhöhe 8,2 m, Rampentore 2), Pleidelsheim (Baujahr 1991).
> - Ratingen: Alle drei Einheiten des Projekts (6373992, 5766717, 5766719) heißen jetzt wie das Projekt „Gewerbepark in (40) Ratingen“.
> - Kontrolle doppelt: Jeder gesendete Text wurde Zeichen für Zeichen mit `plan-b.json` verglichen. Danach wurden alle 44 Datensätze unabhängig neu gelesen und mit dem Plan und dem Stand nach Paket A verglichen. Keine Abweichung; was nicht geändert werden sollte, ist unverändert.
>
> Abweichungen vom Vorschlag in `vorschlaege-paket-b.md`:
> - **Aachen, Halle 2 (6373959):** Der Vorschlag hätte Beschreibung und Ausstattung von Halle 1 (Zonen mit 1.200 m², Mezzanine, sechs Rampen) auch an Halle 2 geschrieben. Das wäre falsch gewesen, der Text gilt nur für Halle 1. Halle 2 hat jetzt den Text ihrer eigenen Mileway-Unterseite. Am Projekt tragen die drei Zonen-Zeilen den Zusatz „Halle 1:“.
> - **Wesseling (6373761):** Die Hallenfläche 4.115 m² ist abgeleitet (6.585 m² minus 1.420 m² Büro minus 1.050 m² Mezzanine). Seite und Broschüre von Mileway nennen dieselben Zahlen; der Fließtext nennt 2.730 + 2.435 = 5.165 m² Lager. Die Ableitung steht in der internen Notiz der Einheit, mit der Bitte, sie bei Mileway bestätigen zu lassen.
> - **Kriftel:** „rund 2.550 m² Lagerfläche“ statt 3.050 m² (Entscheidung 4).
> - **Namen der Gewerbeparks** („Forum Radefeld“, „Hansepark“) bleiben in den Beschreibungen (Entscheidung 5).
> - **Bergkamen:** „Bahnhof Werne an der Lippe“ statt der Kurzform „Werne a d Lippe“.
> - Geschützte Bindestriche aus dem Seitentext (Aachen) sind jetzt normale Bindestriche.
> - **Leipzig:** „Bahnhof Leipzig/Halle Flughafen: ca. 5,9 km“ statt „Bahnhof Leipzig-Wahren: ca. 7,9 km“. Der Vorschlag war hier falsch: Die Rechnung prüfte nur die fünf Bahnhöfe mit der kürzesten Luftlinie, und drei davon waren Haltepunkte der Parkeisenbahn am Auensee. Eine Gegenprobe mit zwölf Kandidaten ohne Park- und Museumsbahnen bestätigt die übrigen 14 Standorte.
>
> Grenzen der Lagetexte:
> - Unter „ÖPNV“ stehen die nächste Bushaltestelle (bis 1,5 km) und der nächste Bahnhof oder Haltepunkt der Eisenbahn. Stadtbahn- und Straßenbahnhaltestellen, die weiter als 1,5 km entfernt sind, fehlen – zum Beispiel die Linie 16 in Wesseling.
> - Weitere Autobahnen stehen nur dabei, wenn ihre Anschlussstelle unter den acht nächstgelegenen liegt und höchstens 10 km Fahrstrecke entfernt ist. Die Liste ist dort nicht zwingend vollständig.
> - Entfernungen zu Häfen sind auf einen Kilometer nicht genau (gemessen bis zu einem Punkt im Hafengebiet).
>
> Aufgefallen und nicht geändert:
> - **Aachen, Halle 2:** Die Hallenhöhe 10 m stammt von der Seite der Gesamtliegenschaft und gehört dort zum Hochregallager von Halle 1. Die Unterseite von Halle 2 nennt keine Höhe. Sie nennt „Rampenandienung“; das Feld „Rampentore“ der Einheit ist leer.
> - **Ratingen, D4 (5766719):** Laut Vermerk vom 09.11. bietet Mileway die Fläche nicht mehr an. Die Einheit steht weiter auf „Vermarktung“ und „Aktiv“.
> - **Köln:** „Rampentore (vorderseitig)“ steht ohne Zahl im Text; das Feld der Einheiten B2 und A7 ist leer.
>
> Abweichungen bei Paket A:
> - **Ratingen (6373992):** Überschrift zunächst nicht geändert, weil die beiden älteren Einheiten dasselbe Muster trugen. Mit Paket B für alle drei erledigt.
> - **Rampentore:** Die Wörter bleiben im Feld (Entscheidung Florian: „deshalb gibt es doch das Feld“).
> - **Barbing (613124):** Der Längengrad saß erst im zweiten Anlauf.
>
> Beim Prüfen der Namen gefunden:
> - Fünf neue Projektnamen gibt es im Bestand schon an anderer Adresse (Wesseling, Castrop-Rauxel, Dormagen, Leipzig, Köln) – von Hand so benannt, also das Muster des How-to.
> - Alte Datensätze vom Import am 13.01.2025 an derselben oder benachbarter Adresse: Köln 2777862 (Hansestraße 61-63), Neuss 2778565 (Fuggerstraße 2-6), Castrop-Rauxel 2778015 (Merklinder Straße 12). An keinem hängt ein Deal. Sie sind nicht angefasst; die Entscheidung geht als Vorlage per Aufgabe an Lena Klinnert (Ansage Florian, 10.11.).
>
> Die geschriebenen Texte stehen in `plan-b.json`. Wie die Kilometer entstanden sind, zeigt der Ordner `berechnung/`: `lage_ergebnis.json` enthält je Standort alle berechneten Fahrstrecken, `lage.py` und `texte.py` die Rechnung und den Textaufbau (Stand der Arbeitskopie; die Koordinaten kamen aus dem Abruf der Projekte).

Die folgende Liste zeigt den Stand vor der Korrektur (gelesen am 10.11.2026).

Umfang: 15 Projekte (613115–613129) mit 26 Einheiten. Dazu eine Einheit desselben Laufs im Bestandsprojekt Ratingen (6373992).
Alle Einheiten stehen auf „Vermarktung“ und „Aktiv“; der automatische Exposéversand ist bei keiner gesperrt.

## 1. Was nicht stimmt

| Befund | Regel | Betroffen |
| --- | --- | --- |
| Straße und Hausnummer in Name und Überschrift | How-to: „Logistikhalle in (2-stellige PLZ) Ort“ | 15 von 15 Projekten, 26 von 26 Einheiten |
| Adresse steht im Lagetext oder in der Beschreibung, obwohl „Adresse ausblenden“ an ist | Widerspruch zur eigenen Einstellung | 10 von 15 Projekten (und ihre Einheiten) |
| Einheitennummer nennt die Adresse oder die Hausnummer | Widerspruch zu „Adresse ausblenden“ | 3 Einheiten: Neuss „Fuggerstraße 2“, Aachen „Allee 50“ und „Allee 54“ |
| „Mietprojekt“ ist aus | How-to Projekte, „Webseite & Landing-Page“ | 15 von 15 Projekten |
| „Einheitenliste im Exposé anzeigen“ ist nicht gesetzt | How-to Projekte, „Webseite & Landing-Page“ | 15 von 15 Projekten |
| Am Projekt fehlt die Provision ganz; an den Einheiten fehlt der Provisionshinweis | How-to: „Provisionsfrei“ + „Die Anmietung erfolgt provisionsfrei für den Mieter.“ | 15 Projekte, 26 Einheiten |
| Lage als ein Fließtext-Absatz mit Luftlinien-Entfernungen | How-to: stichpunktartige Liste der Entfernungen in km ab der Adresse | 15 von 15 Projekten (und ihre Einheiten) |
| Ausstattung leer | How-to: alles Bekannte, das in kein Feld passt | 15 Projekte, 26 Einheiten |
| Gesamtfläche enthält die Bürofläche | How-to: Gesamtfläche = Hallenfläche + Mezzaninefläche | 11 von 26 Einheiten |
| Eigentümer an der Einheit nicht verknüpft (am Projekt schon) | How-to Einheiten, „Ansprechpartner“ | 26 von 26 Einheiten |
| Interne Notizen an der Einheit leer | How-to: Link, Mandat, Mietpreise, Provisionsregelung | 26 von 26 Einheiten |
| Feld „Rampentore“ enthält ein Wort statt einer Zahl | Feld-Mapping, Korrektur 38 | 5 von 26 Einheiten |
| Beschreibung bricht mitten im Wort ab | – (sichtbar im Exposé) | 5 von 26 Einheiten |
| Bildtitel „Ort 1“ bis „Ort 4“, kein Grundriss gekennzeichnet | How-to: benennen (z. B. „Außenansicht“), Grundriss kennzeichnen | 15 Projekte, 60 Bilder |
| Projekt mit nur einer Einheit | Wissensdatenbank, Abschnitt 3: dann Einzelobjekt | 9 von 15 Projekten |
| Projekt ohne Koordinaten | How-to: Adresse im Dropdown wählen | 1 Projekt (613124 Barbing) |

Die im How-to genannten Felder sind fast durchgehend leer. Von 26 Einheiten haben: Hallenhöhe 4, ebenerdige Tore 4, Rampentore als Zahl 2, interner Mietpreis 1. Bodentragkraft, Grundstücksfläche, Stellplätze, LKW-Stellplätze, WGK, Beleuchtung, Sprinkler, Heizungsart, Zertifizierung, Baujahr und „teilbar ab“: keine einzige.

In Ordnung sind: Außenprovision „Provisionsfrei“ und die beiden Provisionsfelder an allen Einheiten, Eigentümer am Projekt verknüpft, kein Eigentümername und kein Preis in den Texten, „Verfügbar ab“ überall gesetzt, Koordinaten an allen Einheiten.

## 2. Paket A – richte ich über den Connector, sobald du Ok sagst

Rund 68 Einzeländerungen. Bei jeder sichert der Connector den Stand vorher.

1. **15 Projekte:** Name und Überschrift ohne Adresse (Vorschläge in Abschnitt 5), „Mietprojekt“ an, „Einheitenliste im Exposé anzeigen“ an, Provision „Provisionsfrei“ mit Standardhinweis. Projekt 613124 bekommt die Koordinaten seiner Einheiten.
2. **27 Einheiten:** Überschrift wie das Projekt, Provisionshinweis ergänzt, Gesamtfläche ohne Büro (11 Einheiten plus Ratingen), interne Notiz mit dem Link zur Mileway-Seite und der Provisionsregelung. Die drei Einheitennummern mit Adresse bekommen neutrale Nummern – Vorschlag: Neuss „Halle“, Aachen „Halle 1“ und „Halle 2“; sag mir, wenn du andere willst.
3. **26 Einheiten:** Eigentümer Mileway Germany GmbH verknüpfen.

Zwei Dinge musst du dazu wissen:

- Die angezeigte Gesamtfläche wird kleiner. Beispiel Wesseling: bisher 6.585 m² inklusive Büro, künftig 5.165 m². Die 1.420 m² Büro stehen weiter im Feld Bürofläche.
- Gibt es in einer Stadt schon ein Projekt mit diesem Namen, heißen danach zwei gleich. Das How-to sieht keinen Zusatz vor. Ich prüfe das vor dem Schreiben und melde dir die Fälle.

## 3. Paket B – braucht Recherche, ich lege dir Vorschläge vor

1. **Lage neu (15 Standorte):** Adresse raus, Entfernungen als Liste mit Straßen-Kilometern statt Luftlinie. Ich ermittle die Kilometer per Routenberechnung und lege dir die Texte je Standort vor. Geschätzt wird nichts.
2. **Beschreibung:** Adresse streichen (5 Projekte: Melle, Kriftel, Reinbek, Gottmadingen, Neuss). Danach die 5 abgeschnittenen Einheiten-Beschreibungen vervollständigen.
3. **Ausstattung und fehlende Felder:** aus den 15 Mileway-Seiten, die an den Einheiten hinterlegt sind. Was dort nicht steht, bleibt leer und wird als offen gemeldet.
4. **Rampentore (5 Einheiten):** Die Zahl ist unbekannt. Vorschlag: Feld leeren und „Rampenandienung“ bzw. „Rampentor“ in die Ausstattung schreiben.

## 4. Paket C – geht nur von Hand in Propstack

1. Schalter „Auf der Landing Page auf die jeweiligen Einheiten verlinken“ an 15 Projekten. Den erreicht die Schnittstelle nicht.
2. 60 Bilder umbenennen, Grundrisse kennzeichnen, auf Firmenschriftzüge prüfen. Ob Schriftzüge drauf sind, sehe ich über die Schnittstelle nicht.
3. Interne Notizen an den 15 Projekten. Der Connector kann sie nicht lesen und schreibt deshalb nichts hinein.
4. Entscheidung zu den 9 Projekten mit nur einer Einheit: so lassen oder in Einzelobjekte umbauen. Umbauen heißt Projekt löschen – das kann und soll der Connector nicht.

## 5. Je Projekt

| Projekt | Ort | Name jetzt | Name neu (Vorschlag) | Einheiten | Adresse steht in | Besonderheit |
| --- | --- | --- | --- | --- | --- | --- |
| 613115 | Wesseling | Logistikhalle in (50) Wesseling – Widdiger Straße 1-9 | Logistikhalle in (50) Wesseling | 1 | Lage | nur 1 Einheit |
| 613116 | Castrop-Rauxel | Logistikhalle in (44) Castrop-Rauxel – Merklinder Straße 10 | Logistikhalle in (44) Castrop-Rauxel | 1 | – | nur 1 Einheit |
| 613117 | Melle | Logistikhalle in (49) Melle – Betonstraße 8 | Logistikhalle in (49) Melle | 1 | Lage, Beschreibung | nur 1 Einheit |
| 613118 | Weiden | Logistikhalle in (92) Weiden – Am Forst 13 & 15 | Logistikhalle in (92) Weiden | 1 | Lage | nur 1 Einheit |
| 613119 | Kriftel | Logistikhalle in (65) Kriftel – Am Holzweg 24 | Logistikhalle in (65) Kriftel | 1 | Beschreibung | nur 1 Einheit |
| 613120 | Aachen | Logistikhalle in (52) Aachen – Charlottenburger Allee 50-60 | Logistikhalle in (52) Aachen | 2 | – | – |
| 613121 | Bergkamen | Logistikhalle in (59) Bergkamen – Emilie-Winkelmann-Straße 6 | Logistikhalle in (59) Bergkamen | 1 | – | nur 1 Einheit |
| 613122 | Dormagen | Logistikhalle in (41) Dormagen – Hamburger Straße 26 | Logistikhalle in (41) Dormagen | 1 | Lage | nur 1 Einheit |
| 613123 | Reinbek | Logistikhalle in (21) Reinbek – Borsigstraße 4-6 | Logistikhalle in (21) Reinbek | 3 | Lage, Beschreibung | – |
| 613124 | Barbing | Logistikhalle in (93) Barbing – Gutenbergstraße 2-16 | Logistikhalle in (93) Barbing | 5 | – | keine Koordinaten |
| 613125 | Gottmadingen | Logistikhalle in (78) Gottmadingen – Industriepark 210 | Logistikhalle in (78) Gottmadingen | 3 | Lage, Beschreibung | – |
| 613126 | Leipzig | Logistikhalle in (04) Leipzig – Poststraße 9-21 | Logistikhalle in (04) Leipzig | 2 | Lage | – |
| 613127 | Pleidelsheim | Logistikhalle in (74) Pleidelsheim – Gottlieb-Daimler-Straße 15-17 | Logistikhalle in (74) Pleidelsheim | 1 | – | nur 1 Einheit |
| 613128 | Köln | Logistikhalle in (51) Köln – Hansestraße 61-63 | Logistikhalle in (51) Köln | 2 | Lage | – |
| 613129 | Neuss | Logistikhalle in (41) Neuss – Fuggerstraße 2 | Logistikhalle in (41) Neuss | 1 | Lage, Beschreibung | nur 1 Einheit |

## 6. Je Einheit

| Einheit | Ort | Einheitennummer | Gesamtfläche m² (alt → neu) | Rampentore-Feld | Beschreibung abgeschnitten |
| --- | --- | --- | --- | --- | --- |
| 6373761 | Wesseling | Gesamtfläche | 6585 → 5165 | – | ja |
| 6373826 | Castrop-Rauxel | Halle 2 | 6437 → 5381 | – | – |
| 6373929 | Melle | Gebäude 2 | 6781 → 5655 | „Rampentor“ | – |
| 6373953 | Weiden | Halle | – | – | ja |
| 6373955 | Kriftel | Lager | 3050 → 2550 | „Rampenandienung“ | – |
| 6373958 | Aachen | Allee 50 | – | „Rampenandienung“ | – |
| 6373959 | Aachen | Allee 54 | 489 → 334 | – | – |
| 6373960 | Bergkamen | Halle | – | – | – |
| 6373961 | Dormagen | Lager | – | „Rampentor“ | – |
| 6373963 | Reinbek | Halle 2a | – | – | – |
| 6373964 | Reinbek | Halle 2b | 345 → 304 | – | – |
| 6373965 | Reinbek | Halle 2c | – | – | – |
| 6373966 | Barbing | 1B 1.OG | 801 → 593 | – | – |
| 6373967 | Barbing | 4A 1.OG | – | – | – |
| 6373969 | Barbing | 4A EG | – | – | – |
| 6373970 | Barbing | 1A 1.OG | – | – | – |
| 6373971 | Barbing | 2B 1.OG | – | – | – |
| 6373972 | Gottmadingen | Halle 204 | – | – | ja |
| 6373973 | Gottmadingen | Halle 239 | – | – | ja |
| 6373974 | Gottmadingen | Halle 306 | – | – | ja |
| 6373975 | Leipzig | Unit F | 476 → 226 | – | – |
| 6373977 | Leipzig | Unit D | – | – | – |
| 6373980 | Pleidelsheim | Gebäude 17 EG | – | – | – |
| 6373982 | Köln | B2 | 1321 → 1056 | – | – |
| 6373983 | Köln | A7 | 1070 → 898 | – | – |
| 6373984 | Neuss | Fuggerstraße 2 | 2683 → 2300 | „Rampenandienung“ | – |
| 6373992 | Ratingen (Bestandsprojekt 567014) | A2 | 1513 → 1193 | – | – |

Bei allen Einheiten der Tabelle gilt zusätzlich: Überschrift mit Adresse, Provisionshinweis fehlt, Eigentümer nicht verknüpft, interne Notiz leer, Ausstattung leer. Ratingen: Überschrift mit Zusatz „– Aircom Parc, A2 (1.513 m²)“ statt Adresse.
