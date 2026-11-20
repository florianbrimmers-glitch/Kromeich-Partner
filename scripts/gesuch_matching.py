"""Welche unserer Flächen passen auf ein Gesuch? Liest nur.

Prototyp vom 19.11.2026. Anlass: Die ganze Automatisierung pflegt den Bestand – die
Frage, mit der das Geld verdient wird, beantwortet keine davon. Am 19.11.2026 fanden sich
für die sechs Gesuche der Website 64 Kandidaten unter 1.116 Einheiten in Vermarktung und
weitere 65 unter 204 aktiven Einheiten des Altbestands ohne Propstack-Status.

Gesucht wird im Umkreis eines Ortes nach Hallenfläche, optional Hallenhöhe und Rampen:

  python scripts/gesuch_matching.py --ort Wermelskirchen --umkreis 30 --flaeche 8000-12000 --hoehe 9 --rampen 4
  python scripts/gesuch_matching.py --lat 52.575 --lng 13.33 --umkreis 30 --flaeche 1500-3000 --hoehe 7.5

Regeln:
- In Frage kommt, was nicht vermietet, nicht archiviert und in „Status Logistik“ nicht
  inaktiv ist – und entweder in Propstack in Vermarktung steht (Status 163674) oder gar
  keinen Propstack-Status hat, in „Status Logistik“ aber „Aktiv“ ist. Die zweite Gruppe
  ist Altbestand aus dem Import 01/2025 (19.11.2026: 204 Einheiten); sie wird als
  „ohne Propstack-Status“ gekennzeichnet und gehört vor einem Angebot geprüft.
- Fläche = Lagerfläche (Custom-Feld `lagerflache`, sonst `lagerflache_verfugbar`), sonst
  die Fläche der Einheit. Eine größere Einheit passt, wenn sie laut
  `lagerflache_teilbar_ab` teilbar ist.
- Ist Hallenhöhe oder Rampenzahl an der Einheit nicht gepflegt, bleibt sie Kandidat und
  die Lücke wird genannt – ein fehlender Wert ist kein Ausschluss. Ist der Wert
  gepflegt und zu klein, fällt die Einheit raus.
- `--ort` ohne Koordinaten nimmt die Mitte der eigenen Einheiten in diesem Ort. Kennt
  der Bestand den Ort nicht, --lat/--lng angeben.

Grenzen (Datenstand 19.11.2026, 1.320 Einheiten kommen in Frage):
- 270 Einheiten (20 %) haben keine Koordinaten – eine Umkreissuche sieht sie nicht.
  Das Skript nennt ihre Zahl bei jedem Lauf.
- Rampen sind bei 42 % gepflegt, Hallenhöhe bei 71 %.
- „Bezug“ ist Freitext („sofort“, „Q2 2027“, „laut Flächenupdate …“), als Datum nur bei
  26 %. Nach Verfügbarkeit lässt sich deshalb nicht filtern; der Text wird angezeigt.
- Kühlung ist an 3 Einheiten gepflegt: Ein Kühlgesuch lässt sich nicht aus Feldern beantworten.

Umgebung: PROPSTACK_API_KEY oder PROPSTACK_API_V1 (wird nie ausgegeben).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field

import httpx

BASE = "https://api.propstack.de/v1"
STATUS_VERMARKTUNG = 163674


def _scalar(value):
    return value["value"] if isinstance(value, dict) and "value" in value else value


def _custom(unit: dict, key: str):
    fields = unit.get("custom_fields")
    return _scalar(fields.get(key)) if isinstance(fields, dict) else None


def zahl(value) -> float | None:
    """Zahl aus einem Feldwert: 7575.0, "7.575 m²", "12", "9,5"."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    m = re.search(r"\d[\d.,]*", value)
    if not m:
        return None
    raw = m.group().rstrip(".,")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", raw):
        return float(re.sub(r"[.,]", "", raw))
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def entfernung_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def koordinaten(unit: dict) -> tuple[float, float] | None:
    lat, lng = zahl(_scalar(unit.get("lat"))), zahl(_scalar(unit.get("lng")))
    return (lat, lng) if lat and lng else None


VERMARKTUNG = "Vermarktung"
ALTBESTAND = "ohne Propstack-Status"


def verfuegbar_als(unit: dict) -> str | None:
    """Kommt die Einheit für ein Angebot in Frage – und in welcher Gruppe? None = nein.

    Propstack führt zwei Angaben nebeneinander: den Objekt-Status und das Custom-Feld
    „Status Logistik“. Am 19.11.2026 waren 204 Einheiten dort „Aktiv“ und frei, hatten
    aber keinen Propstack-Status – wer nur nach Status filtert, sieht sie nicht."""
    if _scalar(unit.get("rented")) is True or _scalar(unit.get("archived")) is True:
        return None
    logistik = _custom(unit, "status_logistik")
    if logistik == "Inaktiv":
        return None
    status = unit.get("property_status")
    if isinstance(status, dict):
        return VERMARKTUNG if status.get("id") == STATUS_VERMARKTUNG else None
    return ALTBESTAND if logistik == "Aktiv" else None


def in_vermarktung(unit: dict) -> bool:
    return verfuegbar_als(unit) is not None


def ortsmitte(units: list[dict], ort: str) -> tuple[float, float] | None:
    """Mitte der eigenen Einheiten in diesem Ort (auch „Köln-Ossendorf“ für „Köln“)."""
    gesucht = ort.strip().casefold()
    punkte = [
        k for u in units
        if (k := koordinaten(u)) and str(_scalar(u.get("city")) or "").strip().casefold().split("-")[0].strip() == gesucht
    ]
    if not punkte:
        return None
    return sum(p[0] for p in punkte) / len(punkte), sum(p[1] for p in punkte) / len(punkte)


@dataclass
class Gesuch:
    lat: float
    lng: float
    umkreis_km: float
    flaeche_von: float
    flaeche_bis: float
    hoehe_min: float | None = None
    rampen_min: float | None = None


@dataclass
class Kandidat:
    unit_id: int
    name: str
    ort: str
    entfernung_km: int
    flaeche: int
    teilbar_ab: int | None
    hoehe: float | None
    rampen: float | None
    bezug: str | None
    projekt_id: int | None
    gruppe: str = VERMARKTUNG
    luecken: list[str] = field(default_factory=list)


def _bezeichnung(unit: dict) -> str:
    """Überschrift und Name: Einheiten heißen oft nur „Unit 1“ – erst die Überschrift sagt, wo."""
    titel = str(_scalar(unit.get("title")) or "").strip()
    name = str(_scalar(unit.get("name")) or "").strip()
    if titel and name and name.casefold() not in titel.casefold():
        return f"{titel} – {name}"
    return titel or name or f"Einheit {unit['id']}"


def pruefe(unit: dict, gesuch: Gesuch) -> Kandidat | None:
    """Passt die Einheit? None = nein (oder ohne Koordinaten/Fläche nicht beurteilbar)."""
    punkt = koordinaten(unit)
    if not punkt:
        return None
    abstand = entfernung_km(gesuch.lat, gesuch.lng, *punkt)
    if abstand > gesuch.umkreis_km:
        return None

    flaeche = (
        zahl(_custom(unit, "lagerflache"))
        or zahl(_custom(unit, "lagerflache_verfugbar"))   # Altbestand: nur als Text „20.170 m²“
        or zahl(_scalar(unit.get("property_space_value")))
    )
    if not flaeche:
        return None
    teilbar_ab = zahl(_custom(unit, "lagerflache_teilbar_ab"))
    passt = gesuch.flaeche_von <= flaeche <= gesuch.flaeche_bis or (
        teilbar_ab is not None and teilbar_ab <= gesuch.flaeche_bis and flaeche >= gesuch.flaeche_von
    )
    if not passt:
        return None

    luecken: list[str] = []
    hoehe = zahl(_custom(unit, "hallenhohe"))
    if gesuch.hoehe_min is not None:
        if hoehe is None:
            luecken.append("Hallenhöhe")
        elif hoehe < gesuch.hoehe_min:
            return None
    rampen = zahl(_custom(unit, "ramepntore"))  # so heißt das Feld in Propstack
    if gesuch.rampen_min is not None:
        if rampen is None:
            luecken.append("Rampen")
        elif rampen < gesuch.rampen_min:
            return None

    bezug = _custom(unit, "bezug")
    return Kandidat(
        unit_id=unit["id"],
        name=_bezeichnung(unit),
        ort=str(_scalar(unit.get("city")) or ""),
        entfernung_km=round(abstand),
        flaeche=round(flaeche),
        teilbar_ab=round(teilbar_ab) if teilbar_ab else None,
        hoehe=hoehe,
        rampen=rampen,
        bezug=str(bezug) if bezug else None,
        projekt_id=_scalar(unit.get("project_id")),
        gruppe=verfuegbar_als(unit) or VERMARKTUNG,
        luecken=luecken,
    )


def finde(units: list[dict], gesuch: Gesuch) -> tuple[list[Kandidat], int, int]:
    """(Kandidaten, in Frage kommende Einheiten, davon ohne Koordinaten).
    Sortiert: erst Vermarktung, dann Altbestand; darin erst ohne Datenlücke, dann nach Entfernung."""
    verfuegbar = [u for u in units if in_vermarktung(u)]
    ohne_koordinaten = sum(1 for u in verfuegbar if not koordinaten(u))
    kandidaten = [k for u in verfuegbar if (k := pruefe(u, gesuch))]
    kandidaten.sort(key=lambda k: (k.gruppe != VERMARKTUNG, len(k.luecken), k.entfernung_km, -k.flaeche))
    return kandidaten, len(verfuegbar), ohne_koordinaten


def lade_einheiten(key: str) -> list[dict]:
    """GET /v1/units?expand=1 – alle Seiten (rund 2.600 Einheiten = 26 Seiten)."""
    # Feste Reihenfolge und je ID nur einmal: Ohne Sortierung verschieben sich Einheiten
    # zwischen den Seiten – zwei Läufe hintereinander zählten 1.115 und 1.118.
    units: dict[int, dict] = {}
    page = 1
    with httpx.Client(timeout=60.0, headers={"X-API-KEY": key, "Accept": "application/json"}) as client:
        while True:
            response = client.get(f"{BASE}/units", params={
                "expand": 1, "per": 100, "page": page, "sort_by": "created_at", "order": "asc",
            })
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(3)
                continue
            response.raise_for_status()
            data = response.json()
            rows = data if isinstance(data, list) else (data or {}).get("data", [])
            for row in rows:
                if isinstance(row, dict) and row.get("id"):
                    units[row["id"]] = row
            if len(rows) < 100:
                return list(units.values())
            page += 1
            time.sleep(0.3)


def _bereich(text: str) -> tuple[float, float]:
    teile = [zahl(t) for t in re.split(r"\s*[-–]\s*", text.strip())]
    if len(teile) == 1 and teile[0]:
        return teile[0] * 0.85, teile[0] * 1.15  # eine Zahl: ±15 %
    if len(teile) == 2 and teile[0] and teile[1] and teile[0] <= teile[1]:
        return teile[0], teile[1]
    raise argparse.ArgumentTypeError(f"Fläche als „8000-12000“ oder „10000“ angeben, nicht „{text}“")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ort", help="Ort, in dem wir Einheiten führen (Mitte dieser Einheiten)")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lng", type=float)
    ap.add_argument("--umkreis", type=float, default=25, help="Kilometer (Standard 25)")
    ap.add_argument("--flaeche", type=_bereich, required=True, help="Hallenfläche in m²: 8000-12000 oder 10000 (±15 %%)")
    ap.add_argument("--hoehe", type=float, help="Mindest-Hallenhöhe in m")
    ap.add_argument("--rampen", type=float, help="Mindestzahl Rampen/Tore")
    ap.add_argument("--json", action="store_true", help="Ergebnis als JSON")
    args = ap.parse_args()

    key = os.environ.get("PROPSTACK_API_KEY") or os.environ.get("PROPSTACK_API_V1")
    if not key:
        print("PROPSTACK_API_KEY bzw. PROPSTACK_API_V1 fehlt.", file=sys.stderr)
        return 2
    if (args.lat is None) != (args.lng is None) or (args.lat is None and not args.ort):
        print("Entweder --ort oder --lat und --lng angeben.", file=sys.stderr)
        return 2

    units = lade_einheiten(key)
    if args.lat is not None:
        mitte = (args.lat, args.lng)
    else:
        mitte = ortsmitte(units, args.ort)
        if not mitte:
            print(f"Im Bestand liegt keine Einheit mit Koordinaten in „{args.ort}“ – bitte --lat und --lng angeben.", file=sys.stderr)
            return 2

    gesuch = Gesuch(mitte[0], mitte[1], args.umkreis, args.flaeche[0], args.flaeche[1], args.hoehe, args.rampen)
    kandidaten, verfuegbar, ohne_koordinaten = finde(units, gesuch)

    if args.json:
        print(json.dumps({"gesuch": asdict(gesuch), "in_vermarktung": verfuegbar,
                          "ohne_koordinaten": ohne_koordinaten, "kandidaten": [asdict(k) for k in kandidaten]},
                         ensure_ascii=False, indent=1))
        return 0

    vollstaendig = sum(1 for k in kandidaten if not k.luecken)
    altbestand = sum(1 for k in kandidaten if k.gruppe == ALTBESTAND)
    von, bis = (f"{wert:,.0f}".replace(",", ".") for wert in (gesuch.flaeche_von, gesuch.flaeche_bis))
    print(f"{len(kandidaten)} Kandidaten im Umkreis von {args.umkreis:g} km ({von}–{bis} m²), "
          f"davon {vollstaendig} mit allen Angaben"
          + (f", {altbestand} aus dem Altbestand ohne Propstack-Status (vor einem Angebot prüfen)." if altbestand else "."))
    for k in kandidaten:
        teile = [f"Einheit {k.unit_id}", f"{k.ort} ({k.entfernung_km} km)", f"{k.flaeche:,} m²".replace(",", ".")]
        if k.teilbar_ab:
            teile.append(f"teilbar ab {k.teilbar_ab:,} m²".replace(",", "."))
        teile.append(f"Höhe {k.hoehe:g} m" if k.hoehe else "Höhe –")
        teile.append(f"{k.rampen:g} Rampen" if k.rampen else "Rampen –")
        teile.append(f"Bezug: {k.bezug}" if k.bezug else "Bezug –")
        if k.projekt_id:
            teile.append(f"https://crm.propstack.de/app/projects/{k.projekt_id}")
        if k.gruppe == ALTBESTAND:
            teile.append("OHNE PROPSTACK-STATUS")
        if k.luecken:
            teile.append(f"NICHT GEPFLEGT: {', '.join(k.luecken)}")
        print("  " + " · ".join(teile))
        print(f"      {k.name}")
    print(f"\nGeprüft: {verfuegbar} Einheiten, die in Frage kommen. {ohne_koordinaten} davon haben keine Koordinaten "
          "und konnten nicht berücksichtigt werden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
