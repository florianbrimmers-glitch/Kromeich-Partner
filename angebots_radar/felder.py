"""Kleine Helfer: Feldwerte aus Propstack lesen, Entfernungen, Gebiete, Quartale.

Bewusst ohne Abhängigkeit zu den anderen Paketen (gespiegelt statt gekoppelt); `zahl` und
`entfernung_km` entsprechen scripts/gesuch_matching.py.
"""
from __future__ import annotations

import math
import re
from datetime import date


def skalar(value):
    """Viele Felder kommen als {label, value} – der Wert darin, sonst der Wert selbst."""
    return value["value"] if isinstance(value, dict) and "value" in value else value


def custom(row: dict, key: str):
    fields = row.get("custom_fields")
    return skalar(fields.get(key)) if isinstance(fields, dict) else None


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


def im_polygon(lat: float, lng: float, polygon: list) -> bool:
    """Punkt im Vieleck. Propstack liefert die Ecken als [lng, lat] (live 26.11.2026)."""
    innen = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i][0], polygon[i][1]
        x2, y2 = polygon[(i + 1) % n][0], polygon[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat) and lng < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            innen = not innen
    return innen


def polygon_mitte(polygon: list) -> tuple[float, float]:
    """(lat, lng) – Mittel der Ecken; reicht, um Treffer nach Nähe zu ordnen."""
    return (sum(p[1] for p in polygon) / len(polygon), sum(p[0] for p in polygon) / len(polygon))


# Bundesland über die ersten zwei Ziffern der PLZ. An Landesgrenzen ungenau (49477 Ibbenbüren
# liegt in NRW, „49“ zählt hier zu Niedersachsen) – deshalb gilt zuerst das Feld „region“ der
# Einheit, die Tabelle ist nur der Ersatz. Für ein Gesuch „NRW“ reicht das.
_PLZ_LAND = {
    "Nordrhein-Westfalen": "32 33 40 41 42 44 45 46 47 48 50 51 52 53 57 58 59",
    "Niedersachsen": "21 26 27 29 30 31 37 38 49",
    "Hessen": "34 35 36 60 61 63 64 65",
    "Rheinland-Pfalz": "54 55 56 67 76",
    "Baden-Württemberg": "68 69 70 71 72 73 74 75 77 78 79 88 89",
    "Bayern": "80 81 82 83 84 85 86 87 90 91 92 93 94 95 96 97",
    "Saarland": "66",
    "Berlin": "10 12 13",
    "Brandenburg": "14 15 16 03",
    "Hamburg": "20 22",
    "Schleswig-Holstein": "23 24 25",
    "Bremen": "28",
    "Mecklenburg-Vorpommern": "17 18 19",
    "Sachsen": "01 02 04 08 09",
    "Sachsen-Anhalt": "06 39",
    "Thüringen": "07 98 99",
}
PLZ_ZU_LAND = {plz: land for land, liste in _PLZ_LAND.items() for plz in liste.split()}


def bundesland(region: str | None, plz: str | None) -> str | None:
    if region and region.strip() in _PLZ_LAND:
        return region.strip()
    plz = re.sub(r"\D", "", plz or "")
    return PLZ_ZU_LAND.get(plz[:2]) if len(plz) == 5 else None


def ort_schluessel(ort: str | None) -> str:
    """„Köln-Ossendorf“ und „Köln“ sollen zusammenfinden, „Mülheim an der Ruhr“ und „Mülheim“ auch."""
    text = (ort or "").strip().casefold()
    text = re.split(r"\s*[-/(,]\s*|\s+(?:an der|am|a\.d\.|bei|ob der|in der|im)\s+", text)[0]
    return text.strip()


# --- Zeitpunkte: „ab wann“ im Gesuch, „Bezug“ an der Einheit -------------------------------

SOFORT = (0, 0)   # kleiner als jedes Quartal
_MONATE = {"januar": 1, "jan": 1, "februar": 2, "feb": 2, "märz": 3, "maerz": 3, "mrz": 3, "april": 4, "apr": 4,
           "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9,
           "sept": 9, "oktober": 10, "okt": 10, "november": 11, "nov": 11, "dezember": 12, "dez": 12}
_JAHRESTEIL = {"anfang": 1, "frühjahr": 2, "fruehjahr": 2, "mitte": 3, "sommer": 3, "herbst": 4, "ende": 4, "winter": 4}
_SOFORT = re.compile(r"\b(sofort|asap|kurzfristig|zeitnah|ab jetzt)\b", re.IGNORECASE)
_VERFUEGBAR = re.compile(r"verf(?:ü|ue)gbar", re.IGNORECASE)


def _jahr(text: str) -> int:
    return int(text) + 2000 if len(text) == 2 else int(text)


def _alle_quartale(t: str, heute: date | None) -> list[tuple[int, int]]:
    funde: list[tuple[int, int]] = []
    for m in re.finditer(r"\bQ\s?([1-4])\s*[/ .-]?\s*(20\d\d|\d\d)\b", t, re.IGNORECASE):
        funde.append((_jahr(m.group(2)), int(m.group(1))))
    for m in re.finditer(r"\b(20\d\d)-(\d\d)-\d\d\b", t):
        funde.append((int(m.group(1)), (int(m.group(2)) + 2) // 3))
    for m in re.finditer(r"\b\d{1,2}\.(\d{1,2})\.(20\d\d|\d\d)\b", t):
        if 1 <= int(m.group(1)) <= 12:
            funde.append((_jahr(m.group(2)), (int(m.group(1)) + 2) // 3))
    for m in re.finditer(r"(?<![\dQq.])(0?[1-9]|1[0-2])\s?/\s?(20\d\d)\b", t):   # nicht die 3 aus „Q3/2027“
        funde.append((int(m.group(2)), (int(m.group(1)) + 2) // 3))
    for m in re.finditer(r"\b([A-Za-zäÄü]{3,9})\.?\s+(20\d\d)\b", t):
        wort = m.group(1).casefold()
        if wort in _MONATE:
            funde.append((int(m.group(2)), (_MONATE[wort] + 2) // 3))
        elif wort in _JAHRESTEIL:
            funde.append((int(m.group(2)), _JAHRESTEIL[wort]))
    if heute and (m := re.search(r"\b(\d{1,2})(?:\s*-\s*(\d{1,2}))?\s*Monate\b", t)):
        monate = int(m.group(2) or m.group(1))        # „12-14 Monate ab Mietvertrag“: der spätere Wert
        ziel = heute.year * 12 + (heute.month - 1) + monate
        funde.append((ziel // 12, (ziel % 12) // 3 + 1))
    if not funde and (m := re.search(r"(?<![\d.,/])(20[2-4]\d)(?![\d.,/])", t)):
        funde.append((int(m.group(1)), 1))
    return funde


def quartal(text: str | None, heute: date | None = None, spaetestes: bool = False) -> tuple[int, int] | None:
    """(Jahr, Quartal) aus „Q3 2026“, „Q2/2027“, „Sommer 2027“, „Ende 2028“, „07/2026“, „01.12.2026“,
    „März 2027“, „2026-04-01“, mit `heute` auch „ca. 15 Monate nach Mietvertragsabschluss“.
    SOFORT für „ab sofort“, „kurzfristig“, „zeitnah“ – das gilt auch, wenn daneben ein Datum steht
    („Ab sofort, spätestens Sommer 2026“). Sonst das früheste genannte Quartal, mit `spaetestes`
    das späteste (Bezug einer Einheit: „Bauzeit Feb 2027 bis Jan 2028“). „… verfügbar“ ohne
    Datum zählt als sofort („laut Flächenupdate August 2026 verfügbar“ nennt aber ein Datum).
    None = nicht lesbar („auf Anfrage“, „Quartal“, „nach Absprache“)."""
    if not text:
        return None
    t = text.strip()
    if _SOFORT.search(t):
        return SOFORT
    funde = _alle_quartale(t, heute)
    if funde:
        return max(funde) if spaetestes else min(funde)
    return SOFORT if _VERFUEGBAR.search(t) else None


def quartal_von(tag: date) -> tuple[int, int]:
    return tag.year, (tag.month + 2) // 3


def quartale_zwischen(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Wie viele Quartale liegt b nach a (negativ: davor)."""
    return (b[0] - a[0]) * 4 + (b[1] - a[1])


def quartal_text(q: tuple[int, int] | None) -> str:
    if q is None:
        return "offen"
    return "sofort" if q == SOFORT else f"Q{q[1]} {q[0]}"
