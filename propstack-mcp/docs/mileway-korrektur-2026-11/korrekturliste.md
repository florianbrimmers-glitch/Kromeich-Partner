# Korrekturliste: Mileway-Lauf vom 09.11.2026

> **Stand 10.11.2026, abends: Paket A ist umgesetzt** (Freigabe Florian Brimmers: „so machen“).
> 15 Projekte, 26 Einheiten und die Einheit in Ratingen wurden über den Connector korrigiert, 26 Eigentümer verknüpft.
> Ein Kontroll-Lesen aller 42 Datensätze ergab keine Abweichung vom Plan; Halle, Büro, Status, Beschreibung und Lage sind unverändert.
>
> Abweichungen von der Liste unten:
> - **Ratingen (6373992):** Überschrift nicht geändert. Die beiden älteren Einheiten desselben Projekts (5766717, 5766719) tragen dasselbe Muster „– Aircom Parc, A5 (995 m²)“; nur eine von dreien umzustellen hätte sie uneinheitlich gemacht. Provisionshinweis, Gesamtfläche und interne Notiz sind gesetzt.
> - **Rampentore:** Die Wörter bleiben im Feld (Entscheidung Florian: „deshalb gibt es doch das Feld“).
> - **Barbing (613124):** Der Längengrad saß erst im zweiten Anlauf.
>
> Beim Prüfen der Namen gefunden:
> - Fünf neue Projektnamen gibt es im Bestand schon an anderer Adresse (Wesseling, Castrop-Rauxel, Dormagen, Leipzig, Köln) – von Hand so benannt, also das Muster des How-to.
> - Alte Datensätze ohne Titel und Fläche an derselben oder benachbarter Adresse: Köln 2777862 (Hansestraße 61-63), Neuss 2778565 (Fuggerstraße 2-6), Castrop-Rauxel 2778015 (Merklinder Straße 12). Mögliche Dubletten – nicht angefasst.
>
> Paket B (Lage, Ausstattung, Beschreibung) liegt als Vorschlag in `vorschlaege-paket-b.md`; die exakten Texte stehen in `plan-b.json`. Davon ist nichts geschrieben.

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
