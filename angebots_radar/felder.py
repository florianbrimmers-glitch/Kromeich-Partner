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
    """Zahl aus einem Feldwert: 7575.0, "7.575 m²", "6.858,32 m²", "12", "9,5".
    Ein einzelner Punkt vor genau drei Ziffern ist ein Tausenderpunkt („8.000“ = 8000)."""
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
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", raw):          # 6.858,32
        return float(raw.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", raw):          # 6,858.32
        return float(raw.replace(",", ""))
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
    "Rheinland-Pfalz": "54 55 56 67",
    "Baden-Württemberg": "68 69 70 71 72 73 74 75 76 77 78 79 88 89",   # 76: Karlsruhe; 767/768 liegen in RLP
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


def plz5(text: str | None) -> str:
    """Fünfstellige PLZ aus einem Feld. Vier Ziffern allein sind eine ostdeutsche PLZ ohne führende Null („4451“)."""
    roh = (text or "").strip()
    if re.fullmatch(r"\d{4}", roh):
        return "0" + roh
    m = re.search(r"(?<!\d)(\d{5})(?!\d)", roh)
    return m.group(1) if m else ""


def bundesland(region: str | None, plz: str | None) -> str | None:
    if region and region.strip() in _PLZ_LAND:
        return region.strip()
    plz = plz5(plz)
    return PLZ_ZU_LAND.get(plz[:2]) if plz else None


# Ortsnamen. „Köln-Ossendorf“ und „Köln“ sollen zusammenfinden, „Mülheim an der Ruhr“ und „Mülheim“
# auch – „Frankfurt (Oder)“ und „Frankfurt am Main“ aber nicht, und „Neu-Ulm“ ist nicht „Neu-Isenburg“.
_ORT_VORSILBEN = {"neu", "alt", "groß", "gross", "klein", "bad", "sankt", "st", "st.", "ober", "unter", "nieder", "hohen", "markt"}
_ORT_ZUSATZ = re.compile(r"\(([^)]+)\)|\s+(?:an der|am|a\.\s?d\.|ob der|in der|im|bei|vor der)\s+(\S+)")


def ort_schluessel(ort: str | None) -> str:
    """Grundname plus unterscheidender Zusatz: „köln“ (aus „Köln-Ossendorf“), „mülheim ruhr“,
    „frankfurt oder“, „frankfurt main“, „halle saale“, „neu-ulm“. Ein Ortsteil hinter dem
    Bindestrich fällt weg, außer der Name beginnt mit einer Vorsilbe wie „Neu-“ oder „Bad “."""
    text = (ort or "").strip().casefold()
    if not text:
        return ""
    zusatz = ""
    if m := _ORT_ZUSATZ.search(text):
        zusatz = re.sub(r"[^a-zäöüß]", "", (m.group(1) or m.group(2) or ""))
        text = text[:m.start()]
    text = re.split(r"\s*[/,]\s*", text)[0].strip()
    teile = text.split("-")
    if len(teile) > 1 and teile[0].strip() not in _ORT_VORSILBEN:
        text = teile[0].strip()
    return f"{text} {zusatz}".strip()


def gleiche_ortsschluessel(ka: str, kb: str) -> bool:
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    grund_a, _, zusatz_a = ka.partition(" ")
    grund_b, _, zusatz_b = kb.partition(" ")
    # „bad lippspringe“ hat auch ein Leerzeichen: nur als Zusatz werten, was nicht hinter einer Vorsilbe steht
    if grund_a in _ORT_VORSILBEN or grund_b in _ORT_VORSILBEN:
        return False
    return grund_a == grund_b and (not zusatz_a or not zusatz_b)


def gleicher_ort(a: str | None, b: str | None) -> bool:
    """Gleicher Ort – auch wenn nur einer den Zusatz trägt („Mülheim“ und „Mülheim an der Ruhr“).
    Tragen beide einen und er unterscheidet sich, sind es zwei Orte."""
    return gleiche_ortsschluessel(ort_schluessel(a), ort_schluessel(b))


def ort_grundname(ort: str | None) -> str:
    """Der Name, wie er in einer Notiz steht: „mülheim“, „frankfurt“, „bad oeynhausen“, „neu-ulm“."""
    schluessel = ort_schluessel(ort)
    grund, _, _ = schluessel.partition(" ")
    return schluessel if grund in _ORT_VORSILBEN else grund


# --- Zeitpunkte: „ab wann“ im Gesuch, „Bezug“ an der Einheit -------------------------------

SOFORT = (0, 0)   # kleiner als jedes Quartal
_MONATE = {"januar": 1, "jan": 1, "februar": 2, "feb": 2, "märz": 3, "maerz": 3, "mrz": 3, "april": 4, "apr": 4,
           "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9,
           "sept": 9, "oktober": 10, "okt": 10, "november": 11, "nov": 11, "dezember": 12, "dez": 12}
_JAHRESTEIL = {"anfang": 1, "frühjahr": 2, "fruehjahr": 2, "mitte": 3, "sommer": 3, "herbst": 4, "ende": 4, "winter": 4}
_SOFORT = re.compile(r"(?<!nicht )(?<!kein )\b(sofort|asap|kurzfristig|zeitnah|ab jetzt|schnellstm(?:ö|oe)glich)\b(?!\s+nicht)", re.IGNORECASE)
_VERFUEGBAR = re.compile(r"verf(?:ü|ue)gbar", re.IGNORECASE)
_NICHT_VERFUEGBAR = re.compile(r"\bnicht\b[^,;.]*verf(?:ü|ue)gbar", re.IGNORECASE)     # „nicht sofort verfügbar“
# Eine Jahreszahl allein ist nur dann ein Termin, wenn sie nicht das Baujahr ist
_KEIN_TERMINJAHR = re.compile(r"(?:baujahr|bj\.?|erbaut|gebaut|neubau|saniert|modernisiert|kernsaniert|seit)\s*:?\s*$", re.IGNORECASE)
_KEINE_FRIST = re.compile(r"(?:laufzeit|mietdauer|mietzeit|vertragsdauer|f(?:ü|ue)r|mindestens|mind\.?)\s*(?:von\s*)?(?:ca\.?\s*)?$", re.IGNORECASE)
# Baubeginn ist kein Bezugstermin („Baubeginn ab Q2 2026“) – außer der Text nennt auch das Ende
_NUR_BAUBEGINN = re.compile(r"baubeginn|baustart|spatenstich", re.IGNORECASE)
_BAUENDE = re.compile(r"fertig|bezug|verf(?:ü|ue)gbar|\bbis\b|(?:ü|ue)bergabe", re.IGNORECASE)
_ROEMISCH = {"i": 1, "ii": 2, "iii": 3, "iv": 4}


def _jahr(text: str) -> int:
    return int(text) + 2000 if len(text) == 2 else int(text)


def _alle_quartale(t: str, heute: date | None) -> list[tuple[int, int]]:
    funde: list[tuple[int, int]] = []
    for m in re.finditer(r"\bQ\s?([1-4])\s*[/ .-]?\s*(20\d\d|\d\d)\b", t, re.IGNORECASE):
        funde.append((_jahr(m.group(2)), int(m.group(1))))
    for m in re.finditer(r"\b([1-4]|i{1,3}|iv)\.?\s*Quartal\s+(20\d\d)\b", t, re.IGNORECASE):     # „2. Quartal 2027“
        funde.append((int(m.group(2)), _ROEMISCH.get(m.group(1).casefold()) or int(m.group(1))))
    for m in re.finditer(r"(?<![\d.,/])([1-4])\.?\s?Q\.?\s*(20\d\d|\d\d)\b|\bQuartal\s+([1-4])\s*/\s*(20\d\d)\b", t, re.IGNORECASE):
        funde.append((_jahr(m.group(2) or m.group(4)), int(m.group(1) or m.group(3))))                 # „2.Q 2027“, „2Q27“, „Quartal 2/2027“
    for m in re.finditer(r"\b(?:([12])\.?\s*Halbjahr|H([12]))\s*[/ ]?\s*(20\d\d)\b", t, re.IGNORECASE):  # „2. Halbjahr 2027“, „H2 2027“
        funde.append((int(m.group(3)), 1 if (m.group(1) or m.group(2)) == "1" else 3))
    for m in re.finditer(r"\bJahres(ende|anfang|mitte|beginn)\s+(20\d\d)\b", t, re.IGNORECASE):
        funde.append((int(m.group(2)), {"ende": 4, "anfang": 1, "beginn": 1, "mitte": 3}[m.group(1).casefold()]))
    for m in re.finditer(r"\bKW\s?(\d{1,2})\s*[/ ]\s*(20\d\d)\b", t, re.IGNORECASE):               # „KW 10/2027“
        funde.append((int(m.group(2)), min(4, (int(m.group(1)) - 1) // 13 + 1)))
    for m in re.finditer(r"(?<!\d)(20\d\d)-(\d\d)-\d\d(?!\d)", t):                                # auch „2026-10-01T00:00“
        funde.append((int(m.group(1)), (int(m.group(2)) + 2) // 3))
    for m in re.finditer(r"\b\d{1,2}\.(\d{1,2})\.(20\d\d|\d\d)\b", t):
        if 1 <= int(m.group(1)) <= 12:
            funde.append((_jahr(m.group(2)), (int(m.group(1)) + 2) // 3))
    for m in re.finditer(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(20\d\d)\b", t):                           # „10/1/2026“
        erster, zweiter = int(m.group(1)), int(m.group(2))
        monat = erster if (zweiter == 1 and erster <= 12) or zweiter > 12 else zweiter       # 10/1 = 1. Oktober
        if 1 <= monat <= 12:
            funde.append((int(m.group(3)), (monat + 2) // 3))
    for m in re.finditer(r"(?<![\dQq./-])(0?[1-9]|1[0-2])\s?[/.-]\s?(20\d\d)\b", t):                 # „07/2026“, „07-2026“, „07.2026“; nicht „Q3/2027“, „KW 10/2027“
        if not re.search(r"(?:KW|Quartal)\s?$", t[:m.start()], re.IGNORECASE):
            funde.append((int(m.group(2)), (int(m.group(1)) + 2) // 3))
    for m in re.finditer(r"\b([A-Za-zäÄü]{3,9})\.?\s+(20\d\d)\b", t):
        wort = m.group(1).casefold()
        if wort in _MONATE:
            funde.append((int(m.group(2)), (_MONATE[wort] + 2) // 3))
        elif wort in _JAHRESTEIL:
            funde.append((int(m.group(2)), _JAHRESTEIL[wort]))
    if heute and (m := re.search(r"\b(\d{1,2})(?:\s*-\s*(\d{1,2}))?\s*Monate\b", t)) and not _KEINE_FRIST.search(t[:m.start()]):
        monate = int(m.group(2) or m.group(1))        # „12-14 Monate ab Mietvertrag“: der spätere Wert
        ziel = heute.year * 12 + (heute.month - 1) + monate
        funde.append((ziel // 12, (ziel % 12) // 3 + 1))
    if not funde and (m := re.search(r"(?<![\d.,/-])(20[2-4]\d)(?![\d.,/-])", t)) and not _KEIN_TERMINJAHR.search(t[:m.start()]):
        funde.append((int(m.group(1)), 1))
    return funde


def quartal(text: str | None, heute: date | None = None, spaetestes: bool = False) -> tuple[int, int] | None:
    """(Jahr, Quartal) aus „Q3 2026“, „Q2/2027“, „2. Halbjahr 2027“, „Sommer 2027“, „Ende 2028“,
    „07/2026“, „01.12.2026“, „März 2027“, „2026-04-01“, „KW 10/2027“, mit `heute` auch „ca. 15 Monate
    nach Mietvertragsabschluss“. SOFORT für „ab sofort“, „kurzfristig“, „zeitnah“.

    Zwei Lesarten:
    - Gesuch (Standard): Der früheste Termin zählt, und „sofort“ schlägt jedes Datum
      („Ab sofort, spätestens Sommer 2026“).
    - Einheit (`spaetestes`): Der späteste Termin zählt, und ein genanntes Datum schlägt „sofort“
      („Halle 12 Monate nach Mietvertrag, Büros sofort“; „Bauzeit Feb 2027 bis Jan 2028“).
    „… verfügbar“ ohne Datum zählt als sofort. None = nicht lesbar („auf Anfrage“, „Quartal“,
    „nach Absprache“, „nicht verfügbar“, „Baubeginn ab Q2 2026“)."""
    if not text:
        return None
    t = text.strip()
    if _NUR_BAUBEGINN.search(t) and not _BAUENDE.search(t):
        return None
    sofort = bool(_SOFORT.search(t))
    if sofort and not spaetestes:
        return SOFORT
    funde = _alle_quartale(t, heute)
    if funde:
        return max(funde) if spaetestes else min(funde)
    if sofort:
        return SOFORT
    return SOFORT if _VERFUEGBAR.search(t) and not _NICHT_VERFUEGBAR.search(t) else None


def quartal_von(tag: date) -> tuple[int, int]:
    return tag.year, (tag.month + 2) // 3


def quartale_zwischen(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Wie viele Quartale liegt b nach a (negativ: davor)."""
    return (b[0] - a[0]) * 4 + (b[1] - a[1])


def quartal_text(q: tuple[int, int] | None) -> str:
    if q is None:
        return "offen"
    return "sofort" if q == SOFORT else f"Q{q[1]} {q[0]}"
