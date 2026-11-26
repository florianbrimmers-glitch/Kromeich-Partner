"""Ein Suchprofil aus Propstack (`GET /v1/saved_queries`) als Gesuch lesen.

Stand 26.11.2026 (271 Suchprofile, nur gelesen): 144 sind Ankaufsprofile von Investoren
(`marketing_type` BUY), 127 Miet- und sonstige Gesuche, davon 103 aktiv. Die Anforderungen
stehen an drei Stellen:

- Gebiet: `lat`/`lng`/`radius` (Meter) bei 83, sonst `polygon` (Ecken als [lng, lat]),
  `cities` oder `regions` (Bundesländer); bei manchen nichts („deutschlandweit“).
- Fläche: das Custom-Feld `lagerflache` – eine UNTERGRENZE für Propstacks eigenes Matching,
  vom Team meist auf 50–95 % des Wunsches gesetzt („~10.000 m²“ → 8.000). Der Wunsch selbst
  steht im Text.
- Text (`public_note`, `note`), seit 2026 meist nach der Vorlage des Teams:
  „▪️ ~8.000 - 12.000 m² Hallenfläche ▪️ mind. 9m Deckenhöhe ▪️ mind. 4 Rampen ▪️ ab Sommer 2027“.

Der Text wird hier gelesen, nicht gedeutet: Was sich nicht sicher lesen lässt, bleibt leer und
steht im Bericht unter „nicht auswertbar“ – ein Gesuch ohne lesbare Fläche erzeugt keinen
Vorschlag.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .felder import custom, quartal, zahl

AKTIV_OPTION = 182817          # Custom-Feld „aktiv“ am Suchprofil: 182817 = Aktiv, 182818 = Inaktiv
HALLEN_TYPEN = {"INDUSTRY", "SPECIAL_PURPOSE"}

# Tausender mit Punkt oder Leerzeichen („10.000“, „10 000“) oder nackt („4000“)
_NUM = r"(\d{1,3}(?:[. ]\d{3})+|\d+)"
_M2 = r"(?:m\s?[²2]|qm|quadratmeter)"
_BEREICH = re.compile(rf"{_NUM}\s*{_M2}?\s*(?:-|–|—|bis)\s*{_NUM}\s*(?:{_M2}\s*)+", re.IGNORECASE)
_EINZEL = re.compile(rf"{_NUM}\s*{_M2}", re.IGNORECASE)
_TAUSEND_K = re.compile(r"\b(\d{1,3})\s?k\b", re.IGNORECASE)
_ZAHL_HALLE = re.compile(rf"{_NUM}\s+(?:halle|hallenfl\w*|lager|lagerfl\w*)\b", re.IGNORECASE)     # „suchen 5.000 Halle“
_KURZ_BEREICH = re.compile(r"(?<![\d.,])(\d{1,2})\s?(?:-|–|bis)\s?(\d{1,3}\.\d{3})(?![\d.,])")      # „10-15.000“
_HALLE = re.compile(r"hallenfl|lagerfl|logistikfl|logistikhalle|hallenflaeche|\bhalle\b|\blager\b|geb(?:ä|ae)ude\b|mietfl", re.IGNORECASE)
# Zeilen, deren Quadratmeter nicht die gesuchte Hallenfläche sind
_NICHT_HALLE = re.compile(
    r"b(?:ü|ue)ro|grundst|au(?:ß|ss)enfl|freifl|befestigt|park|stellpl|verkaufsfl|nebenfl|sozial|einwohner|haushalte|"
    r"rampe|docks?\b|\btore?\b|andienung|je 1\.?000|pro 1\.?000|deckenh|\bukb\b|palettenstell|mezzanin|miete\b|eur|€",
    re.IGNORECASE,
)
_MINDEST = re.compile(r"\b(mind\.?|mindestens|min\.|ab|mindestfl\w*)\s*(?:ca\.?\s*)?~?\s*$", re.IGNORECASE)
_HOECHST = re.compile(r"\b(bis zu|max\.?|maximal|h(?:ö|oe)chstens)\s*(?:ca\.?\s*)?~?\s*$", re.IGNORECASE)

_HOEHE_ZEILE = re.compile(r"h(?:ö|oe)he|\bukb\b|\bhoch\b|lichte", re.IGNORECASE)
_HOEHE_WERT = re.compile(r"(\d{1,2}(?:[.,]\d)?)\s*(?:(?:-|–|bis)\s*\d{1,2}(?:[.,]\d)?\s*)?m(?:eter)?\b", re.IGNORECASE)
_KEINE = re.compile(r"keine?\s+(?:besonderen?\s+)?(?:anforderung|angabe|vorgabe)|k\.\s?a\.|\begal\b", re.IGNORECASE)   # nicht „regaliert“
_RAMPEN_ZEILE = re.compile(r"rampe|docks?\b|(?:ü|ue)berladebr", re.IGNORECASE)
_RAMPEN_WERT = re.compile(r"(\d{1,3})\s*(?:(?:-|–|bis)\s*\d{1,3}\s*)?(?:lkw[- ]?)?(?:rampen?|docks?|(?:ü|ue)berladebr)", re.IGNORECASE)
_RAMPEN_JE = re.compile(r"(\d)\s*rampen?\s*(?:je|pro|per)\s*1[. ]?000", re.IGNORECASE)

# Besonderheiten: kein Ausschluss, sondern ein Hinweis an den Vorschlag. Vorlagen-Platzhalter
# („Was wird gelagert? (Gefahrgut etc.)“) und Verneinungen („kein Gefahrgut“, „ohne Batterien“)
# zählen nicht.
_BESONDERHEITEN = {
    "Gefahrgut/WGK/Batterie": r"gefahrgut|gefahrg(?:ü|ue)ter|gefahrstoff|\bwgk\b|batterie|lithium|l(?:ö|oe)schwasser",
    "Kühlung": r"k(?:ü|ue)hl|temperatur|tiefk|\btk\b",
    "Kran": r"\bkran|kranbahn|kr(?:ä|ae)ne",
    "Gleisanschluss": r"gleis",
    "Freifläche": r"freifl|au(?:ß|ss)enfl|befestigte fl",
    "Produktion/Werkstatt": r"produktion|fertigung|werkstatt|schwei(?:ß|ss)|reparatur|instandsetzung",
    "ebenerdige Andienung": r"ebenerdig",
    "24/7": r"24\s?/\s?7",
    "Sprinkler": r"sprinkler|spinkler",
}
# Unausgefüllte Zeilen der Vorlage: „Was wird gelagert? (Gefahrgut etc.)“, „Art und Anzahl der Andienungen (…)“
_PLATZHALTER = re.compile(r"etc\.?\)|art und anzahl|ja\s?/\s?nein|ab wann\?|wie lange\?", re.IGNORECASE)
# Wunsch statt Bedingung: „Gerne 2mal 10t Kräne, im Zweifel rüsten sie selber nach“
_WUNSCH = re.compile(r"\bgerne?\b|nice to have|w(?:ü|ue)nschenswert|optional|wenn m(?:ö|oe)glich|bevorzugt|idealerweise|im idealfall|"
                     r"nicht zwingend|w(?:ä|ae)re (?:gut|sch(?:ö|oe)n|ideal)", re.IGNORECASE)
WUNSCH = " (Wunsch)"
_VERNEINT = re.compile(r"\b(kein|keine|keinen|ohne|nicht|no)\b[^.;/▪]{0,25}$", re.IGNORECASE)
_NICHT_NOETIG = re.compile(r"^[^.;/▪]{0,45}\b(nein|nicht (?:zwingend |unbedingt )?(?:erforderlich|notwendig|n(?:ö|oe)tig)|keine anforderung|k\.\s?a\.|ja\s?/\s?nein|etc\.?\))", re.IGNORECASE)

# Laut Notiz erledigt – das Profil steht aber noch auf aktiv
_ERLEDIGT = re.compile(
    r"hat sich erledigt|tender (?:wurde )?verloren|(?:haben|hat) .{0,40}\b(?:an)?gemietet|anderweitig (?:an)?gemietet|"
    r"meldet sich nicht|kein bedarf|abgesagt|nicht mehr aktuell",
    re.IGNORECASE,
)
# Kein Hallengesuch zur Miete, auch wenn das Profil so angelegt ist
_ANKAUF = re.compile(r"ankauf|portfolio|transaktion|vermietungsgrad|kaufpreis|greenfield|brownfield|grundst(?:ü|ue)cken?\b|"
                     r"investor|transformationsimmobilie", re.IGNORECASE)
_NOCH_NICHT_SENDEN = re.compile(r"noch nicht (?:an den kunden )?(?:senden|posten|anbieten)|erstmal noch nicht", re.IGNORECASE)
_ANGEBOTEN = re.compile(r"\bangeboten\s*:\s*(.*)", re.IGNORECASE | re.DOTALL)
# Ab hier beschreibt die Notiz nicht mehr den Wunsch, sondern schon gefundene oder angebotene Flächen
# (Notiz vom 11.08.2026: „PASSENDE FLAECHEN IM BESTAND … Einheit 5674869 … 5 Rampen“).
_AB_HIER_ERGEBNISSE = re.compile(r"passende fl(?:ä|ae)chen|\bangeboten\s*:|\bstand\s*:\s*$", re.IGNORECASE | re.MULTILINE)
_EINHEIT_ID = re.compile(r"\bEinheit\s+(\d{6,8})\b")


# Satzende: Punkt, Leerraum, Großbuchstabe – aber nicht nach Abkürzungen („ca. Mitte 2027“, „mind. Halle“)
_SATZENDE = (r"(?<!\bca)(?<!\bmind)(?<!\bmin)(?<!\bmax)(?<!\binkl)(?<!\blt)(?<!\bbzw)(?<!\bggf)(?<!\bevtl)"
             r"(?<!\bNr)(?<!\bStr)(?<!\bzzgl)(?<!\betc)(?<!\busw)(?<!\bDr)(?<!\bz)(?<!\bB)(?<!\bA)(?<!\bu)(?<!\ba)(?<!\bi)"
             r"(?<=[a-zäöüß\d\)])\.\s+(?=[A-ZÄÖÜ])")


@dataclass
class Gesuch:
    id: int
    kontakt_id: int
    betreuer_id: int | None
    angelegt: str                       # JJJJ-MM-TT
    aktiv: bool
    vermarktung: str | None             # RENT / BUY / None
    bearbeitet: str = ""                # letzte Änderung am Suchprofil, JJJJ-MM-TT
    # Gebiet
    lat: float | None = None
    lng: float | None = None
    umkreis_km: float | None = None
    polygon: list | None = None
    orte: list[str] = field(default_factory=list)
    laender: list[str] = field(default_factory=list)
    # Fläche
    flaeche_von: float | None = None
    flaeche_bis: float | None = None
    flaeche_quelle: str = ""            # „Text“, „Felder“, „Untergrenze“
    untergrenze: float | None = None    # Custom-Feld lagerflache
    # Weitere Anforderungen
    hoehe_min: float | None = None
    rampen_min: float | None = None
    ab_wann: tuple[int, int] | None = None
    besonderheiten: list[str] = field(default_factory=list)
    # Zustand
    erledigt_hinweis: str | None = None
    noch_nicht_senden: bool = False
    angeboten_text: str = ""            # was in der Notiz hinter „Angeboten:“ steht
    genannte_einheiten: list[int] = field(default_factory=list)   # „Einheit 5674869“ in der Notiz
    kurztext: str = ""
    text: str = ""
    typen: list[str] = field(default_factory=list)
    kein_hallengesuch: str | None = None    # Grund, wenn das Profil nicht in den Hallenabgleich gehört

    @property
    def gebiet(self) -> str:
        if self.lat is not None and self.umkreis_km:
            return "Umkreis"
        if self.polygon:
            return "Gebiet"
        if self.orte:
            return "Orte"
        if self.laender:
            return "Bundesland"
        return "ohne"


def _int(text: str) -> float:
    return float(re.sub(r"[. ]", "", text))


def zeilen(text: str) -> list[str]:
    """Die Vorlage trennt mit „▪️“ oder Zeilenumbruch, ältere Notizen mit „/“ oder Spiegelstrich."""
    roh = re.split(r"[\n\r▪•]+|\s/\s|^\s*[-−–]\s+|" + _SATZENDE, text or "", flags=re.MULTILINE)
    return [z.strip(" \t️-−–") for z in roh if z and z.strip(" \t️-−–")]


def _tausender_kurz(von: float, bis: float) -> tuple[float, float]:
    """„3-5.000 qm“ und „10-15.000“ meinen 3.000–5.000 und 10.000–15.000."""
    if von < 100 and bis >= 1000:
        von *= 1000
    return von, bis


def _flaeche_in_zeile(zeile: str) -> tuple[float | None, float | None] | None:
    """(von, bis) aus einer Zeile; bis = None heißt „mindestens“, von = None „höchstens“."""
    if m := _BEREICH.search(zeile):
        von, bis = _tausender_kurz(_int(m.group(1)), _int(m.group(2)))
        if 0 < von <= bis:
            return von, bis
    if m := _EINZEL.search(zeile):
        wert = _int(m.group(1))
        if wert < 100:
            return None
        davor = zeile[:m.start()]
        if _HOECHST.search(davor):
            return None, wert
        if _MINDEST.search(davor):
            return wert, None
        return wert, wert
    return None


def flaeche_aus_text(text: str) -> tuple[float | None, float | None] | None:
    """Die gesuchte Hallenfläche aus dem Freitext. Zuerst Zeilen, die Halle/Lager nennen; dann
    jede Zeile mit Quadratmetern, die nicht erkennbar etwas anderes meint (Büro, Grundstück,
    „1 Rampe je 1.000 m²“). „20K“ nur, wenn sonst nichts da ist."""
    alle = zeilen(text)
    for nur_halle in (True, False):
        for zeile in alle:
            ist_halle = bool(_HALLE.search(zeile))
            if nur_halle and not ist_halle:
                continue
            if not nur_halle and _NICHT_HALLE.search(zeile):
                continue
            # In einer Hallen-Zeile stören Rampen-Regeln trotzdem („Halle, 1 Rampe je 1.000 m²“)
            if nur_halle and re.search(r"je 1[. ]?000|pro 1[. ]?000|deckenh|\bukb\b", zeile, re.IGNORECASE):
                continue
            if nur_halle and re.search(r"b(?:ü|ue)rofl|grundst|freifl|befestigt|verkaufsfl", zeile, re.IGNORECASE) \
                    and not re.search(r"hallenfl|lagerfl|logistikhalle", zeile, re.IGNORECASE):
                continue
            if fund := _flaeche_in_zeile(zeile):
                return fund
    for zeile in alle:
        if _NICHT_HALLE.search(zeile):
            continue
        if m := _ZAHL_HALLE.search(zeile):
            wert = _int(m.group(1))
            if wert >= 100:
                return wert, wert
        if m := _KURZ_BEREICH.search(zeile):
            von, bis = _tausender_kurz(float(m.group(1)), _int(m.group(2)))
            if 0 < von <= bis:
                return von, bis
        if m := _TAUSEND_K.search(zeile):
            wert = float(m.group(1)) * 1000
            return wert, wert
    return None


def hoehe_aus_text(text: str) -> float | None:
    for zeile in zeilen(text):
        if not _HOEHE_ZEILE.search(zeile) or _KEINE.search(zeile):
            continue
        for m in _HOEHE_WERT.finditer(zeile):
            wert = float(m.group(1).replace(",", "."))
            if 2.5 <= wert <= 20:
                return wert
    return None


def rampen_aus_text(text: str, flaeche_von: float | None) -> float | None:
    for zeile in zeilen(text):
        if not _RAMPEN_ZEILE.search(zeile) or _KEINE.search(zeile):
            continue
        if m := _RAMPEN_JE.search(zeile):
            return max(1.0, round(float(m.group(1)) * flaeche_von / 1000)) if flaeche_von else None
        if m := _RAMPEN_WERT.search(zeile):
            return float(m.group(1))
    return None


def besonderheiten_aus_text(text: str) -> list[str]:
    """Namen aus _BESONDERHEITEN; ein bloßer Wunsch trägt den Zusatz „ (Wunsch)“. Steht etwas
    einmal als Bedingung und einmal als Wunsch da, gilt die Bedingung."""
    fest: list[str] = []
    wunsch: list[str] = []
    for name, muster in _BESONDERHEITEN.items():
        for zeile in zeilen(text):
            for m in re.finditer(muster, zeile, re.IGNORECASE):
                davor = zeile[:m.start()]
                if re.search(r"mit und ohne[^.;/▪]{0,25}$", davor, re.IGNORECASE):
                    pass                                   # „mit und ohne Batterien“ heißt: auch mit
                elif _VERNEINT.search(davor) or _NICHT_NOETIG.search(zeile[m.end():]) or _PLATZHALTER.search(zeile):
                    continue
                ziel = wunsch if _WUNSCH.search(zeile) else fest
                if name not in ziel:
                    ziel.append(name)
    return fest + [name + WUNSCH for name in wunsch if name not in fest]


def ab_wann_aus_text(text: str):
    """Der gewünschte Bezug. Nur Zeilen, die danach klingen („Ab …“, „zu April 2027“, „GoLive“) –
    ein Datum in einer Herkunftsnotiz („Stand 18.08.2026“) ist kein Bezugstermin."""
    for zeile in zeilen(text):
        if re.search(r"^\W*(ab|zum?|bis|sp(?:ä|ae)testens|bezug|golive|go-live|start|kurzfristig|asap)\b", zeile, re.IGNORECASE):
            if q := quartal(zeile):
                return q
    return None


def _kurztext(text: str, grenze: int = 160) -> str:
    kurz = " · ".join(zeilen(text)[:6])
    return kurz if len(kurz) <= grenze else kurz[:grenze - 1].rstrip() + "…"


def aus_suchprofil(row: dict) -> Gesuch:
    public = (row.get("public_note") or "").strip()
    note = (row.get("note") or "").strip()
    ganzer_text = "\n".join(t for t in (public, note) if t)
    schnitt = _AB_HIER_ERGEBNISSE.search(ganzer_text)
    text = ganzer_text[:schnitt.start()] if schnitt else ganzer_text      # nur der Wunsch
    aktiv_feld = custom(row, "aktiv")
    aktiv = bool(row.get("active")) and not (isinstance(aktiv_feld, list) and aktiv_feld and AKTIV_OPTION not in aktiv_feld)

    g = Gesuch(
        id=row["id"],
        kontakt_id=row["client_id"],
        betreuer_id=row.get("broker_id"),
        angelegt=str(row.get("created_at") or "")[:10],
        bearbeitet=str(row.get("updated_at") or row.get("created_at") or "")[:10],
        aktiv=aktiv,
        vermarktung=row.get("marketing_type"),
        typen=list(row.get("rs_types") or []),
        text=text,
        kurztext=_kurztext(public or note),
    )
    if row.get("lat") and row.get("lng") and row.get("radius"):
        g.lat, g.lng, g.umkreis_km = float(row["lat"]), float(row["lng"]), float(row["radius"]) / 1000
    elif isinstance(row.get("polygon"), list) and len(row["polygon"]) >= 3:
        g.polygon = row["polygon"]
    g.orte = [o for o in (row.get("cities") or []) if isinstance(o, str)]
    g.laender = [r for r in (row.get("regions") or []) if isinstance(r, str)]

    g.untergrenze = zahl(custom(row, "lagerflache"))
    aus_text = flaeche_aus_text(text)
    von_feld = zahl(row.get("industrial_area")) or zahl(row.get("total_floor_space"))
    bis_feld = zahl(row.get("industrial_area_to")) or zahl(row.get("total_floor_space_to"))
    if aus_text:
        von, bis = aus_text
        g.flaeche_quelle = "Text"
        if von is None:                                   # „bis zu 20.000 m²“
            von = g.untergrenze or bis * 0.5
        elif bis is None:                                 # „mind. 7.000 m²“
            bis = von * 1.5
        elif von == bis:                                  # „~10.000 m²“
            von, bis = von * 0.8, bis * 1.25
        g.flaeche_von, g.flaeche_bis = von, bis
    elif von_feld or bis_feld:
        g.flaeche_quelle = "Felder"
        g.flaeche_von = von_feld or g.untergrenze or bis_feld * 0.5
        g.flaeche_bis = bis_feld or g.flaeche_von * 1.5
    elif g.untergrenze:
        # Nur die Untergrenze: Das Team setzt sie meist auf 50–95 % des Wunsches. Bis zum Doppelten
        # gilt als passend; was darüber liegt, läuft als „größer“ (abgleich.py).
        g.flaeche_quelle = "Untergrenze"
        g.flaeche_von, g.flaeche_bis = g.untergrenze, g.untergrenze * 2

    g.hoehe_min = hoehe_aus_text(text)
    g.rampen_min = rampen_aus_text(text, g.flaeche_von)
    g.ab_wann = ab_wann_aus_text(text)
    g.besonderheiten = besonderheiten_aus_text(text)
    if g.vermarktung == "BUY":
        g.kein_hallengesuch = "Ankaufsprofil"
    elif g.typen and not (HALLEN_TYPEN & set(g.typen)):
        g.kein_hallengesuch = "andere Objektart (" + ", ".join(g.typen) + ")"
    elif text.strip().casefold() in ("test", "testprofil"):
        g.kein_hallengesuch = "Testprofil"
    elif any(b.startswith("Freifläche") for b in g.besonderheiten) and g.flaeche_quelle != "Text":
        g.kein_hallengesuch = "Freifläche gesucht, keine Halle"
    elif _ANKAUF.search(text) and g.flaeche_quelle != "Text" or re.search(r"ankaufsprofil|vermietungsgrad|portfoliotransaktion", text, re.IGNORECASE):
        g.kein_hallengesuch = "Ankauf oder Grundstück laut Text"
    if m := _ERLEDIGT.search(ganzer_text):
        g.erledigt_hinweis = m.group(0)
    g.noch_nicht_senden = bool(_NOCH_NICHT_SENDEN.search(ganzer_text))
    if m := _ANGEBOTEN.search(ganzer_text):
        g.angeboten_text = m.group(1)[:1500]
    g.genannte_einheiten = sorted({int(i) for i in _EINHEIT_ID.findall(ganzer_text)})
    return g


def ist_hallengesuch(g: Gesuch) -> bool:
    """Miet- oder offenes Gesuch nach einer Halle. Ankaufsprofile, Wohnungen, Läden und reine
    Grundstücksgesuche laufen nicht durch den Abgleich."""
    return g.kein_hallengesuch is None
