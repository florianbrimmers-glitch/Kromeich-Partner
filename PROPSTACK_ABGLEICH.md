# Propstack-Abgleich der OSM-Logistikhallen (Glandorf, 40 km)

**Lauf:** GitHub Actions „Propstack Abgleich" am 09.06.2026 · Propstack-Bestand: **1.567 Objekte** (GET /v1/units)
**Match-Logik:** geografisch (Propstack-Objekt < 400 m am OSM-Footprint) ODER PLZ + Straßenname.

## Ergebnis

| Liste | Treffer |
|-------|---------|
| Einzelhallen (25) | **0 von 25** in Propstack |
| Komplexe (20) | **1 von 20** – und dieser ist unsicher (s.u.) |

### Einziger (schwacher) Treffer
- **OSM:** Mielestraße 2, 33611 Bielefeld (Komplex, 36.252 m²)
- **Propstack:** #2777954 „Stadtheider Straße 55 – Bielefeld", 33609 Bielefeld, *zur Miete*
- **Bewertung:** 399 m Abstand, **andere Straße und andere PLZ** → höchstwahrscheinlich ein benachbartes Objekt, **nicht** dieselbe Immobilie. Manuell prüfen.

## Interpretation
Keiner der recherchierten Logistik-/Lager-Standorte ist aktuell als Objekt in Propstack erfasst.
Für die Akquise heißt das: Es handelt sich durchweg um **potenzielle Neukontakte/Zielobjekte**, die noch nicht im CRM liegen.

## Einschränkungen
- Geo-Match nur möglich, wenn das Propstack-Objekt Koordinaten (`lat`/`lng`) hat; Adress-Match braucht passende PLZ + Straße. Anders erfasste Objekte könnten theoretisch übersehen werden.
- Propstack führt für Gewerbe relevante Felder (u.a. `hall_height`, `ramp`, `crane_runway`, `total_floor_space`, `industrial_area`, `plot_area`) – für eine spätere Anreicherung nutzbar.
