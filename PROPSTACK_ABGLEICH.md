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

## Räumlich plausible Kandidaten (manuell prüfen)
| OSM-Halle | Propstack-Objekt | Distanz | Bewertung |
|-----------|------------------|---------|-----------|
| Dometic Waeco, Gutenbergstraße 1, Emsdetten | #2778398 „Gutenbergstraße 20, Emsdetten" | gleiche Straße | **gleiche Straße**, andere Hausnr. → wahrscheinlich Nachbargebäude |
| Dieter-Fuchs-Straße 10, Dissen | #5032898 „Westring, Dissen" (Fläche 19.748 m²) | 490 m | gleiche Stadt, andere Straße → eher Nachbarobjekt |
| Mielestraße 2, Bielefeld | #2777954 „Stadtheider Straße 55, Bielefeld" | 399 m | andere Straße + andere PLZ → eher Nachbarobjekt |

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
