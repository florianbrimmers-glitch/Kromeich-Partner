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

from .felder import SOFORT, custom, quartal, zahl

AKTIV_OPTION = 182817          # Custom-Feld „aktiv“ am Suchprofil: 182817 = Aktiv, 182818 = Inaktiv
# Diese Ausschlüsse stammen aus dem Freitext, nicht aus einem Feld – sie können falsch sein und
# stehen deshalb einzeln im Bericht (bericht.als_daten, „nicht_abgeglichen“).
AUS_TEXT_AUSGESCHLOSSEN = ("Ankauf oder Grundstück laut Text", "Freifläche gesucht, keine Halle")
HALLEN_TYPEN = {"INDUSTRY", "SPECIAL_PURPOSE"}

# --- Fläche -------------------------------------------------------------------------------------
# Tausender mit Punkt oder Leerzeichen („10.000“, „10 000“) oder nackt („4000“)
_NUM = r"(\d{1,3}(?:[. ]\d{3})+|\d+)"
_M2 = r"(?:m\s?[²2]|qm|quadratmeter)"
_DEZ = r"(?:,\d{1,2})?"                                               # „12.500,00 m²“
_BEREICH = re.compile(rf"{_NUM}{_DEZ}\s*{_M2}?\s*(?:-|–|—|bis)\s*~?\s*{_NUM}{_DEZ}\s*(?:{_M2}\s*)+", re.IGNORECASE)
_EINZEL = re.compile(rf"(?<![\d.,]){_NUM}{_DEZ}\s*{_M2}", re.IGNORECASE)
_K_BEREICH = re.compile(r"(?<![\d.,])(\d{1,3})\s?(?:-|–|bis)\s?(\d{1,3})\s?k\b", re.IGNORECASE)   # „5-7k“
_TAUSEND_K = re.compile(r"(?<![\d.,])(\d{1,3}(?:[.,]\d)?)\s?k\b", re.IGNORECASE)                    # „20K“, „3,5k“
_ZAHL_HALLE = re.compile(rf"{_NUM}\s+(?:halle|hallenfl\w*|lager|lagerfl\w*)\b", re.IGNORECASE)     # „suchen 5.000 Halle“
_KURZ_BEREICH = re.compile(r"(?<![\d.,])(\d{1,2})\s?(?:-|–|bis)\s?(\d{1,3}\.\d{3})(?![\d.,])")      # „10-15.000“
_HALLE = re.compile(r"hallenfl|lagerfl|logistikfl|\w*halle\b|\blager\b|geb(?:ä|ae)ude\b|mietfl", re.IGNORECASE)
# Teilsätze, deren Quadratmeter nicht die gesuchte Hallenfläche sind
_NICHT_HALLE = re.compile(
    r"b(?:ü|ue)ro|grundst|au(?:ß|ss)enfl|freifl|befestigt|park|stellpl|verkaufsfl|nebenfl|sozial|einwohner|haushalte|"
    r"rampe|docks?\b|\btore?\b|andienung|je 1\.?000|pro 1\.?000|deckenh|\bukb\b|palette|mezzanin|miete\b|eur|€|budget|umsatz",
    re.IGNORECASE,
)
_STOERT_IN_HALLENZEILE = re.compile(r"je 1[. ]?000|pro 1[. ]?000|deckenh|\bukb\b|palette", re.IGNORECASE)
_ANDERE_FLAECHE = re.compile(r"b(?:ü|ue)ro|grundst|freifl|befestigt|verkaufsfl|sozial|nebenfl|au(?:ß|ss)enfl", re.IGNORECASE)
_HALLENFLAECHE = re.compile(r"hallenfl|lagerfl|logistikhalle|\w*halle\b|\blager\b", re.IGNORECASE)
# Was der Kunde heute hat, ist nicht, was er sucht („aktuell 1.500 m² Halle in Dortmund, sucht 3.000 m²“)
_BESTAND_DES_KUNDEN = re.compile(r"\b(aktuell|derzeit|bisher|bislang|momentan|heute|zurzeit|zur zeit)\b", re.IGNORECASE)
_MINDEST = re.compile(r"(?:\b(?:mind\.?|mindestens|min\.?|minimal|minimum|ab|mindestfl\w*|gr(?:ö|oe)(?:ß|ss)er(?: als)?|(?:ü|ue)ber)|[>≥]=?)"
                      r"\s*(?:von\s+)?(?:ca\.?\s*)?~?\s*$", re.IGNORECASE)
_HOECHST = re.compile(r"(?:\b(?:bis zu|bis|max\.?|maximal|h(?:ö|oe)chstens|unter|kleiner als|nicht gr(?:ö|oe)(?:ß|ss)er als)|[<≤]=?)"
                      r"\s*(?:ca\.?\s*)?~?\s*$", re.IGNORECASE)

# --- Höhe, Rampen -------------------------------------------------------------------------------
_HOEHE_ZEILE = re.compile(r"h(?:ö|oe)he|\bukb\b|\bhoch\b|lichte", re.IGNORECASE)
# Die Höhe eines Tors, einer Rampe oder des Büros ist nicht die Hallenhöhe („Torhöhe 4,5 m“)
_HOEHE_FREMD = re.compile(r"\btor|rampe|b(?:ü|ue)ro|einfahrt|durchfahrt|(?:ü|ue)berladebr|andienung", re.IGNORECASE)
_HOEHE_HALLE = re.compile(r"halle|decke|\bukb\b|licht", re.IGNORECASE)
_HOEHE_WERT = re.compile(r"(?<![\d.,])(\d{1,2}(?:[.,]\d{1,2})?)\s*m?\s*(?:(?:-|–|bis|und)\s*\d{1,2}(?:[.,]\d{1,2})?\s*)?m(?:etern?)?\b", re.IGNORECASE)
_HOEHE_OBERGRENZE = re.compile(r"(?:max\.?|maximal|h(?:ö|oe)chstens|nicht (?:ü|ue)ber|unter)\s*$", re.IGNORECASE)
_KEINE = re.compile(r"keine?\s+(?:besonderen?\s+)?(?:anforderung|angabe|vorgabe)|k\.\s?a\.|\begal\b", re.IGNORECASE)   # nicht „regaliert“
_RAMPEN_ZEILE = re.compile(r"rampe|docks?\b|(?:ü|ue)berladebr", re.IGNORECASE)
_RAMPEN_DING = r"(?:lkw[- ]?)?(?:lade)?(?:rampen?(?:tore?)?|docks?|(?:ü|ue)berladebr\w*)"
_RAMPEN_WERT = re.compile(rf"(?<![\d.,])(\d{{1,3}})\+?\s*(?:(?:-|–|bis)\s*\d{{1,3}}\s*)?{_RAMPEN_DING}", re.IGNORECASE)
_RAMPEN_DANACH = re.compile(rf"{_RAMPEN_DING}\s*:?\s*(?:mind\.?\s*|ca\.?\s*)?(\d{{1,3}})\b(?!\s*(?:t\b|to\b|m\b|[.,]\d))", re.IGNORECASE)   # „Rampen: 4“
_RAMPEN_JE = re.compile(rf"(?:(?<![\d.,])(\d{{1,2}}(?:,\d)?)\s*)?{_RAMPEN_DING}\s*(?:je|pro|per|/)\s*(\d{{1,2}}[. ]\d{{3}}|\d{{3,5}})\s*(?:m|qm)",
                        re.IGNORECASE)

# --- Besonderheiten -----------------------------------------------------------------------------
# Kein Ausschluss der Zeile, sondern je Teilsatz gelesen: „Kühlung ja, Gefahrgut nein“ sind zwei Aussagen.
_BESONDERHEITEN = {
    "Gefahrgut/WGK/Batterie": r"gefahrgut|gefahrg(?:ü|ue)ter|gefahrstoff|\bwgk\b|batterie|lithium|l(?:ö|oe)schwasser",
    # nicht „ungekühlt“, nicht „TK-Anlage“ (Telefon), nicht „12 Grad Temperatur“ der Heizung
    # nicht „Kühlschränke“, „Kühlerbau“, „kühl und trocken“, „Herr Kühl“ – nur, was eine gekühlte Fläche meint
    "Kühlung": r"tiefk(?:ü|ue)hl|(?<!un)(?<!unge)(?:ge)?k(?:ü|ue)hl(?:ung\w*|t\w*|lager\w*|halle\w*|haus|h(?:ä|ae)user|fl(?:ä|ae)che\w*|zelle\w*|"
               r"raum|r(?:ä|ae)ume\w*|logistik|bereich\w*|ware\w*|kette\w*|pflicht\w*|bedarf|kost)|"
               r"temperaturgef|\btk-(?:lager|ware|halle)|temperatur\s*:?\s*-?\d",
    "Kran": r"\w*kran(?:bahn\w*|anlage\w*)?\b|kr(?:ä|ae|a)ne\b",                 # nicht „Krankenhausbetten“
    "Gleisanschluss": r"gleisanschl|bahnanschl",                                  # nicht „Am Gleis 5“, „Nähe Gleis“
    "Freifläche": r"freifl|au(?:ß|ss)enfl|befestigte fl",
    "Produktion/Werkstatt": r"produktion|fertigung|werkstatt|schwei(?:ß|ss)|reparatur|instandsetzung",
    "ebenerdige Andienung": r"ebenerdig",
    "24/7": r"24\s?/\s?7",
    "Sprinkler": r"sprinkler|spinkler",
}
# Unausgefüllte Zeilen der Vorlage: „Was wird gelagert? (Gefahrgut etc.)“, „Art und Anzahl der Andienungen (…)“
_PLATZHALTER = re.compile(r"etc\.?\)|art und anzahl|ja\s?/\s?nein|ab wann\?|wie lange\?", re.IGNORECASE)
# Wunsch statt Bedingung: „Gerne 2mal 10t Kräne, im Zweifel rüsten sie selber nach“
_WUNSCH = re.compile(r"\bgerne?\b|nice to have|w(?:ü|ue)nschenswert|gew(?:ü|ue)nscht|optional|wenn m(?:ö|oe)glich|bevorzugt|"
                     r"idealerweise|im idealfall|w(?:ä|ae)re (?:gut|sch(?:ö|oe)n|ideal)", re.IGNORECASE)
WUNSCH = " (Wunsch)"
_VERNEINT = re.compile(r"\b(kein|keine|keinen|keiner|ohne|nicht|no)\b[^,;]{0,25}$", re.IGNORECASE)
_NICHT_NOETIG = re.compile(
    r"^[^,;]{0,45}\b(nein|nicht (?:zwingend |unbedingt )?(?:erforderlich|notwendig|n(?:ö|oe)tig|ben(?:ö|oe)tigt|gew(?:ü|ue)nscht|gebraucht|relevant)|"
    r"entf(?:ä|ae)llt|unn(?:ö|oe)tig|unklar|offen\b|keine? (?:anforderung|angabe)\w*|k\.\s?a\.|nicht\W*$|keine?\W*$)", re.IGNORECASE)
_NUR_NEIN = re.compile(r"^\W*(nein|nicht|keine?)\W*$", re.IGNORECASE)                # „Gefahrgut (nein)“
# Ein Teilsatz, der nur einschränkt: „…, aber nicht notwendig“ macht aus dem davor einen Wunsch
_NUR_EINSCHRAENKUNG = re.compile(r"^\W*(?:ist\s+)?(?:nicht|kein\w*)\b.{0,25}(notwendig|erforderlich|zwingend|n(?:ö|oe)tig|muss|pflicht)", re.IGNORECASE)

# --- Zustand des Gesuchs ------------------------------------------------------------------------
# Kein Hallengesuch zur Miete, auch wenn das Profil so angelegt ist
_ANKAUF = re.compile(r"ankaufsprofil|(?<!kein )(?<!keinen )\bankauf\b|\bportfolio(?:transaktion\w*)?\b|\btransaktion\w*|vermietungsgrad|"
                     r"kaufpreis|greenfield|brownfield|\bgrundst(?:ü|ue)cken?\b|transformationsimmobilie", re.IGNORECASE)
_NOCH_NICHT_SENDEN = re.compile(r"noch nicht (?:an den kunden )?(?:senden|posten|anbieten)|erstmal noch nicht", re.IGNORECASE)
_ANGEBOTEN = re.compile(r"\bangeboten\s*:\s*(.*)", re.IGNORECASE | re.DOTALL)
# Ab hier beschreibt die Notiz nicht mehr den Wunsch, sondern schon gefundene oder angebotene Flächen
# (Notiz vom 11.08.2026: „PASSENDE FLAECHEN IM BESTAND … Einheit 5674869 … 5 Rampen“). Nur die
# Überschrift zählt – „Kunde sucht passende Flächen in Köln“ ist der Wunsch selbst.
_AB_HIER_ERGEBNISSE = re.compile(r"PASSENDE FL(?:Ä|AE)CHEN|[Pp]assende Fl(?:ä|ae)chen im Bestand|\b[Aa]ngeboten\s*:|^\s*[Ss]tand\s*:\s*$",
                                 re.MULTILINE)
_EINHEIT_ID = re.compile(r"(?:\bEinheit|\bID|\bObjekt|properties/)\s*:?\s*(\d{6,8})\b")


# Satzende: Punkt, Leerraum, Großbuchstabe – aber nicht nach Abkürzungen („ca. Mitte 2027“, „mind. Halle“)
_SATZENDE = (r"(?<!\bca)(?<!\bmind)(?<!\bmin)(?<!\bmax)(?<!\binkl)(?<!\blt)(?<!\bbzw)(?<!\bggf)(?<!\bevtl)"
             r"(?<!\bk)(?<!\bNr)(?<!\bStr)(?<!\bzzgl)(?<!\betc)(?<!\busw)(?<!\bDr)(?<!\bz)(?<!\bB)(?<!\bA)(?<!\bu)(?<!\ba)(?<!\bi)"
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
    flaeche_ziel: float | None = None   # der genannte Wunsch („~10.000 m²“ → 10.000), für „1 Rampe je 1.000 m²“
    # Weitere Anforderungen
    hoehe_min: float | None = None
    rampen_min: float | None = None
    ab_wann: tuple[int, int] | None = None
    besonderheiten: list[str] = field(default_factory=list)
    # Zustand
    erledigt_hinweis: str | None = None
    noch_nicht_senden: bool = False
    angeboten_text: str = ""            # was in der Notiz hinter „Angeboten:“ steht
    genannte_einheiten: list[int] = field(default_factory=list)   # „Einheit 5674869“, „(ID 4807608)“ in der Notiz
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
    """Die Vorlage trennt mit „▪️“ oder Zeilenumbruch, ältere Notizen mit „ / “ oder Spiegelstrich."""
    text = re.sub(r"24\s*/\s*7", "24/7", text or "")                 # „24 / 7“ ist kein Trenner
    text = re.sub(r"((?:rampen?(?:tore?)?|docks?)\s*)/\s*(?=\d)", r"\1je ", text, flags=re.IGNORECASE)   # „1 Rampe / 1.000 m²“ auch nicht
    roh = re.split(r"[\n\r▪•]+|\s/\s|^\s*[-−–]\s+|" + _SATZENDE, text, flags=re.MULTILINE)
    return [z.strip(" \t\ufe0f-−–") for z in roh if z and z.strip(" \t\ufe0f-−–")]


def teilsaetze(zeile: str, klammern: bool = False) -> list[str]:
    """Komma (nicht das Dezimalkomma), Semikolon, „aber“ – jede Aussage für sich. Mit `klammern`
    auch der Einschub: „Gleisanschluss (keine Angabe zu Kran)“ sind zwei Aussagen."""
    muster = r"(?<!\d),|,(?!\d)|;|\s+aber\s+|\s+jedoch\s+" + (r"|[()]" if klammern else "")
    return [t.strip() for t in re.split(muster, zeile) if t and t.strip()]


def _tausender_kurz(von: float, bis: float) -> tuple[float, float]:
    """„3-5.000 qm“ und „10-15.000“ meinen 3.000–5.000 und 10.000–15.000."""
    if von < 100 and bis >= 1000:
        von *= 1000
    return von, bis


def _ohne_fremde_zahlen(zeile: str) -> str:
    """Datum, Jahreszahl und PLZ sind keine Fläche („Lager ab 01.07.2026 – 5.000 m²“, „PLZ 40764 Lager“)."""
    z = re.sub(r"\b\d{1,2}\.\d{1,2}\.(?:\d{4}|\d{2})?", " ", zeile)
    z = re.sub(r"\b(?:PLZ|D-)\s*\d{5}\b", " ", z, flags=re.IGNORECASE)
    z = re.sub(r"\b(ab|seit|in|bis|anfang|mitte|ende|sommer|herbst|winter|fr(?:ü|ue)hjahr|Q[1-4])\s*/?\s*(?:19|20)\d\d(?![\d.,])",
               r"\1 ", z, flags=re.IGNORECASE)
    z = re.sub(rf"(?<![\d.,])(?:19|20)\d\d(?![\d.,])(?!\s*{_M2})(?!\s*(?:-|–|bis)\s*\d[\d. ]*\s*{_M2})", " ", z, flags=re.IGNORECASE)
    z = re.sub(rf"\bzwischen\s+({_NUM[1:-1]}(?:\s*{_M2})?)\s+und\s+", r"\1 - ", z, flags=re.IGNORECASE)       # „zwischen 2.500 und 5.000 m²“
    return re.sub(r"\bbis\s+(?:max\.?|maximal|zu)\s+", "bis ", z, flags=re.IGNORECASE)                       # „mind. 2.500 bis max. 5.000 m²“


def _flaechen_teile(zeile: str) -> list[str]:
    """Die Teilaussagen einer Zeile: „500 m² Büro und 3.000 m² Lager“ sind zwei."""
    return [t.strip() for t in re.split(r"(?<!\d),|,(?!\d)|[;()]|\s\+\s|\s+(?:und|sowie|plus|mit|auf|f(?:ü|ue)r|zzgl\.?)\s+",
                                        _ohne_fremde_zahlen(zeile)) if t and t.strip()]


def _bereich_in(teil: str) -> tuple[float, float] | None:
    if m := _BEREICH.search(teil):
        von, bis = _tausender_kurz(_int(m.group(1)), _int(m.group(2)))
        if 0 < von <= bis and bis >= 100:
            return von, bis
    return None


def _einzelwert_in(teil: str) -> tuple[float | None, float | None] | None:
    """(von, bis); bis = None heißt „mindestens“, von = None „höchstens“."""
    if m := _EINZEL.search(teil):
        wert = _int(m.group(1))
        if wert < 100:
            return None
        davor = teil[:m.start()]
        if _HOECHST.search(davor):
            return None, wert
        if _MINDEST.search(davor):
            return wert, None
        return wert, wert
    return None


def flaeche_aus_text(text: str) -> tuple[float | None, float | None] | None:
    """Die gesuchte Hallenfläche aus dem Freitext, je Teilaussage gelesen.

    Reihenfolge: (1) Aussagen, die Halle/Lager nennen, (2) jede Aussage mit Quadratmetern, die nicht
    erkennbar etwas anderes meint (Büro, Grundstück, „1 Rampe je 1.000 m²“), (3) Kurzformen ohne
    Einheit („5.000 Halle“, „10-15.000“, „20K“). In jeder Stufe schlägt eine Spanne den Einzelwert
    („Mind. 1.000 m², gewünscht 5.000–10.000 m²“). Was der Kunde heute hat, zählt nicht."""
    alle = [[t for t in _flaechen_teile(z) if not _BESTAND_DES_KUNDEN.search(t)] for z in zeilen(text)]
    for nur_halle in (True, False):
        kandidaten = []
        for teile in alle:
            for teil in teile:
                if nur_halle:
                    if not _HALLE.search(teil) or _STOERT_IN_HALLENZEILE.search(teil):
                        continue
                    if _ANDERE_FLAECHE.search(teil) and not _HALLENFLAECHE.search(teil):
                        continue
                elif _NICHT_HALLE.search(teil):
                    continue
                kandidaten.append(teil)
        for lese in (_bereich_in, _einzelwert_in):
            for teil in kandidaten:
                if fund := lese(teil):
                    return fund
    for teile in alle:
        for teil in teile:
            if _NICHT_HALLE.search(teil):
                continue
            if m := _ZAHL_HALLE.search(teil):
                roh = m.group(1)
                wert = _int(roh)
                if wert >= 100 and not re.fullmatch(r"\d{5,}", roh):      # „40764 Lager“ wäre eine PLZ
                    return wert, wert
            if m := _KURZ_BEREICH.search(teil):
                von, bis = _tausender_kurz(float(m.group(1)), _int(m.group(2)))
                if 0 < von <= bis:
                    return von, bis
            if not (_HALLE.search(teil) or len(teil) <= 8) or re.search(r"monat|jahr", teil, re.IGNORECASE):
                continue
            if m := _K_BEREICH.search(teil):
                return float(m.group(1)) * 1000, float(m.group(2)) * 1000
            if m := _TAUSEND_K.search(teil):
                wert = float(m.group(1).replace(",", ".")) * 1000
                return wert, wert
    return None


def hoehe_aus_text(text: str) -> float | None:
    """Die geforderte Hallenhöhe in Metern – nicht die Höhe eines Tors, einer Rampe oder des Büros."""
    for zeile in zeilen(text):
        for teil in teilsaetze(zeile):
            if not _HOEHE_ZEILE.search(teil) or _KEINE.search(teil):
                continue
            if _HOEHE_FREMD.search(teil) and not _HOEHE_HALLE.search(teil):
                continue
            for m in _HOEHE_WERT.finditer(teil):
                wert = float(m.group(1).replace(",", "."))
                if 2.5 <= wert <= 20 and not _HOEHE_OBERGRENZE.search(teil[:m.start()]):   # „max. 6 m“ ist kein Mindestmaß
                    return wert
    return None


def rampen_aus_text(text: str, flaeche_ziel: float | None) -> float | None:
    """Gewünschte Rampenzahl. „1 Rampe je 1.000 m²“ rechnet mit dem genannten Wunsch, nicht mit der
    für den Abgleich gesenkten Untergrenze. Ein bloßer Wunsch („nice to have“) ist keine Zahl."""
    for zeile in zeilen(text):
        if not _RAMPEN_ZEILE.search(zeile) or _KEINE.search(zeile):
            continue
        if m := _RAMPEN_JE.search(zeile):
            je, anzahl = _int(m.group(2)), float((m.group(1) or "1").replace(",", "."))
            return max(1.0, round(anzahl * flaeche_ziel / je)) if flaeche_ziel and je else None
        if re.search(r"nice to have|w(?:ü|ue)nschenswert|optional", zeile, re.IGNORECASE):
            continue
        if (m := _RAMPEN_WERT.search(zeile) or _RAMPEN_DANACH.search(zeile)) and float(m.group(1)) > 0:
            return float(m.group(1))
    return None


def besonderheiten_aus_text(text: str) -> list[str]:
    """Namen aus _BESONDERHEITEN; ein bloßer Wunsch trägt den Zusatz „ (Wunsch)“. Steht etwas
    einmal als Bedingung und einmal als Wunsch da, gilt die Bedingung. Gelesen wird je Teilsatz:
    Eine Verneinung oder ein „gerne“ gilt nur für die Aussage, in der es steht."""
    fest: list[str] = []
    wunsch: list[str] = []
    for zeile in zeilen(text):
        if _PLATZHALTER.search(zeile):
            continue
        teile = teilsaetze(zeile, klammern=True)
        for nr, teil in enumerate(teile):
            if re.search(r"\bweder\b", teil, re.IGNORECASE) or (nr + 1 < len(teile) and _NUR_NEIN.search(teile[nr + 1])):
                continue                                   # „weder Kühlung noch Kran“, „Gefahrgut (nein)“
            nur_wunsch = bool(_WUNSCH.search(teil)) or (nr + 1 < len(teile) and bool(_NUR_EINSCHRAENKUNG.search(teile[nr + 1])))
            for name, muster in _BESONDERHEITEN.items():
                for m in re.finditer(muster, teil, re.IGNORECASE):
                    davor = teil[:m.start()]
                    if re.search(r"mit und ohne[^,;]{0,25}$", davor, re.IGNORECASE):
                        pass                               # „mit und ohne Batterien“ heißt: auch mit
                    elif _VERNEINT.search(davor) or _NICHT_NOETIG.search(teil[m.end():]):
                        continue
                    ziel = wunsch if nur_wunsch else fest
                    if name not in ziel:
                        ziel.append(name)
    namen = list(_BESONDERHEITEN)
    fest.sort(key=namen.index)
    wunsch.sort(key=namen.index)
    return fest + [name + WUNSCH for name in wunsch if name not in fest]


_TERMIN_ZEILE = re.compile(r"^\W*(ab|zum?|bis|sp(?:ä|ae)testens|bezug\w*|mietbeginn|einzug|(?:ü|ue)bernahme|golive|go-live|start|"
                           r"kurzfristig|asap)\b", re.IGNORECASE)
_KEIN_TERMIN = re.compile(r"suche\b|angelegt|\bstand\b|herkunft|profil", re.IGNORECASE)


def ab_wann_aus_text(text: str):
    """Der gewünschte Bezug. Nur Zeilen, die danach klingen („Ab …“, „Mietbeginn …“, „GoLive“) –
    ein Datum in einer Herkunftsnotiz („Stand 18.08.2026“, „Start der Suche: …“) ist kein
    Bezugstermin. Fehlt so eine Zeile, zählt ein „ab sofort“ irgendwo im Text."""
    for zeile in zeilen(text):
        if _TERMIN_ZEILE.search(zeile) and not _KEIN_TERMIN.search(zeile):
            if q := quartal(zeile):
                return q
    if re.search(r"(?<!nicht )\b(ab sofort|asap|schnellstm(?:ö|oe)glich|ab jetzt)\b", text or "", re.IGNORECASE):
        return SOFORT
    return None


def erledigt_aus_text(text: str) -> str | None:
    """Sagt die Notiz, dass das Gesuch erledigt ist? Satzweise, und nur, wenn der Satz nicht das
    Gegenteil sagt („hat noch nichts angemietet“, „hat bereits 3.000 m² angemietet und sucht eine
    Erweiterung“, „Besichtigung abgesagt, neuer Termin folgt“)."""
    for satz in zeilen(text):
        if m := re.search(r"hat sich erledigt|tender (?:wurde )?verloren|meldet sich nicht|anderweitig (?:an)?gemietet", satz, re.IGNORECASE):
            return m.group(0)
        if (m := re.search(r"\b(?:haben|hat)\b.{0,40}\b(?:an)?gemietet", satz, re.IGNORECASE)) and not re.search(
                r"\b(nicht|nichts|kein\w*|sucht|suchen|erweiter\w*|zus(?:ä|ae)tzlich\w*|weitere\w*|bereits)\b", satz, re.IGNORECASE):
            return m.group(0)
        if m := re.search(r"\bkein(?:en)? bedarf(?: mehr)?\b(?!\s+an\b)", satz, re.IGNORECASE):
            return m.group(0)
        if m := re.search(r"\b(?:kunde|gesuch|interessent|mieter|anfrage)\b.{0,30}\b(?:abgesagt|zur(?:ü|ue)ckgezogen)", satz, re.IGNORECASE):
            return m.group(0)
        if m := re.search(r"\b(?:gesuch|suche|bedarf|anfrage|profil)\b.{0,30}nicht mehr aktuell|^\W*nicht mehr aktuell", satz, re.IGNORECASE):
            return m.group(0)
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
        g.flaeche_ziel = von if von is not None else bis
        if von is None:                                   # „bis zu 20.000 m²“
            von = g.untergrenze if g.untergrenze and g.untergrenze < bis else bis * 0.5
        elif bis is None:                                 # „mind. 7.000 m²“
            bis = von * 1.5
        elif von == bis:                                  # „~10.000 m²“
            von, bis = von * 0.8, bis * 1.25
        g.flaeche_von, g.flaeche_bis = von, bis
    elif von_feld or bis_feld:
        if von_feld and bis_feld and von_feld > bis_feld:              # vertauscht eingetragen
            von_feld, bis_feld = bis_feld, von_feld
        g.flaeche_quelle = "Felder"
        g.flaeche_von = von_feld or (g.untergrenze if g.untergrenze and g.untergrenze < bis_feld else bis_feld * 0.5)
        g.flaeche_bis = bis_feld or g.flaeche_von * 1.5
        g.flaeche_ziel = g.flaeche_von
    elif g.untergrenze:
        # Nur die Untergrenze: Das Team setzt sie meist auf 50–95 % des Wunsches. Bis zum Doppelten
        # gilt als passend; was darüber liegt, läuft als „größer“ (abgleich.py).
        g.flaeche_quelle = "Untergrenze"
        g.flaeche_von, g.flaeche_bis = g.untergrenze, g.untergrenze * 2
        g.flaeche_ziel = g.untergrenze

    g.hoehe_min = hoehe_aus_text(text)
    g.rampen_min = rampen_aus_text(text, g.flaeche_ziel)
    g.ab_wann = ab_wann_aus_text(text)
    g.besonderheiten = besonderheiten_aus_text(text)
    if g.vermarktung == "BUY":
        g.kein_hallengesuch = "Ankaufsprofil"
    elif g.typen and not (HALLEN_TYPEN & set(g.typen)):
        g.kein_hallengesuch = "andere Objektart (" + ", ".join(g.typen) + ")"
    elif text.strip().casefold() in ("test", "testprofil"):
        g.kein_hallengesuch = "Testprofil"
    elif "Freifläche" in g.besonderheiten and g.flaeche_quelle != "Text" and not _HALLE.search(text):
        g.kein_hallengesuch = "Freifläche gesucht, keine Halle"
    elif _ANKAUF.search(text) and g.flaeche_quelle != "Text" or re.search(r"ankaufsprofil|vermietungsgrad|portfoliotransaktion", text, re.IGNORECASE):
        g.kein_hallengesuch = "Ankauf oder Grundstück laut Text"
    g.erledigt_hinweis = erledigt_aus_text(ganzer_text)
    g.noch_nicht_senden = bool(_NOCH_NICHT_SENDEN.search(ganzer_text))
    if m := _ANGEBOTEN.search(ganzer_text):
        # Die Liste endet an der ersten Leerzeile – was danach kommt, ist wieder Notiz
        # („Kunde sitzt heute in der Industriestraße in Neuss“ ist kein Angebot).
        g.angeboten_text = re.split(r"\n[ \t]*\n", m.group(1).lstrip())[0][:1500]
    g.genannte_einheiten = sorted({int(i) for i in _EINHEIT_ID.findall(ganzer_text)})
    return g


def ist_hallengesuch(g: Gesuch) -> bool:
    """Miet- oder offenes Gesuch nach einer Halle. Ankaufsprofile, Wohnungen, Läden und reine
    Grundstücksgesuche laufen nicht durch den Abgleich."""
    return g.kein_hallengesuch is None
