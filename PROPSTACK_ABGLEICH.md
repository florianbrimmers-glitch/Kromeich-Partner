# Propstack-Abgleich der OSM-Logistikhallen (Glandorf, 40 km)

**Letzter Lauf:** GitHub Actions „Propstack Abgleich", Run #2 am 09.06.2026 — **Status: success (grün)**
**Propstack-Bestand:** 1.567 Objekte (GET /v1/units, 8 Seiten)
**Match-Logik (gelockert):** Geo < 1 km **ODER** gleiche Stadt/PLZ + Straße **ODER** Betreibername-Token.
Zusätzlich wird für jede Halle ohne Treffer das **nächstgelegene** Propstack-Objekt ausgewiesen.

## Kernergebnis
Auch mit der gelockerten Logik ist **keine** der 45 Hallen mit identischer Adresse in Propstack.
Die formal gezählten Treffer (4/25 Einzelhallen, 2/20 Komplexe) sind fast ausschließlich
**Namens-Fehltreffer** über weite Distanzen. Real räumlich nah sind nur 3 Kandidaten – alle mit
*abweichender* Adresse (Nachbarobjekte, nicht dieselbe Halle).

## Detailprüfung der 3 Kandidaten (Propstack-Objekt im Detail vs. OSM-Halle)
Alle drei wurden über die Propstack-Einzel-API (GET /v1/units/{id}) verifiziert. **Ergebnis: keiner ist dieselbe Immobilie.**

| OSM-Halle | Propstack-Objekt (#ID) | Befund |
|-----------|------------------------|--------|
| Dometic Waeco, Gutenbergstr. 1, Emsdetten (Lager, 31.056 m²) | #2778398 „Gutenbergstr. 20" | **Wohnung** (rs_type=APARTMENT, object_type=LIVING) — nur Straßenname-Zufall. **Kein Treffer.** |
| Dieter-Fuchs-Str. 10, Dissen (Lager, 36.856 m²; 52.1054, 8.1901) | #5032898 „Westring, Dissen / A33" (INDUSTRY, 19.748 m², Makler O. Sahin; 52.1102, 8.1926) | **andere Halle** im selben Gewerbegebiet, ~560 m entfernt, andere Straße, halbe Fläche. **Kein Treffer**, aber: KP hat dort bereits ein Lagerhallen-Mandat. |
| Mielestr. 2, Bielefeld (Industrie-Komplex) | #2777954 „Stadtheider Str. 55" (INDUSTRY; 52.0403, 8.5466) | anderes Gewerbeobjekt ~470 m entfernt, andere Straße/PLZ. **Kein Treffer.** |

**Fazit der Detailprüfung:** 0 echte Treffer. Bemerkenswert ist nur, dass KP im Gewerbegebiet Dissen/A33
bereits eine (andere) Lagerhalle betreut (#5032898, Makler Oguzhan Sahin) — nützlicher Kontext für die Akquise dort.

## Namens-Fehltreffer (KEINE echten Treffer)
- „Thomas Philipps …" → matchte ~20 Objekte mit Token *thomas* (Schifferstadt, Grammetal, Düsseldorf …) in **150–333 km** Entfernung.
- „Coppenrath & Wiese" → matchte Objekte mit Token *wiese* (Wiesenstraße/-weg) in **140–240 km** Entfernung.
Diese sind durch die ausgewiesene Distanz klar als Zufallstreffer erkennbar.

## Nächstgelegene Objekte (Auszug) — Beleg, dass real nichts in der Nähe liegt
- Im Westerfeld, Lotte: nächstes Objekt **4,9 km**
- Gestamp, Bielefeld: **6,0 km**
- Werk 2, Rödinghausen: **8,0 km**
- Brockhagener Str., Bielefeld: **9,5 km**
- die meisten übrigen Hallen: **10–31 km**

## Fazit
Der erste (rote) Lauf war inhaltlich korrekt — rot war nur der Artifact-Upload (GitHub-Speicherquota).
Der grüne Wiederholungslauf mit gelockerten Kriterien **bestätigt**: Keine der recherchierten
Logistik-/Lagerhallen ist als Objekt in Propstack erfasst. Drei Standorte (Emsdetten, Dissen, Bielefeld)
haben ein Propstack-Objekt in unmittelbarer Nähe mit abweichender Adresse und sollten manuell geprüft werden.
Alle anderen sind klar nicht im Bestand → durchweg **potenzielle Akquise-Zielobjekte**.
