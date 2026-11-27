"""Gesuch gegen Bestand: Welche Flächen passen – und sind noch nicht angeboten?

Die Regeln sind an den echten Angeboten des Teams ausgerichtet (Deals der Pipeline „300 Mieter“,
gelesen am 26.11.2026):

- Angeboten wird nicht nur die Fläche, die genau passt: Für „~10.000 m²“ gingen vier Einheiten zu
  je 5.000 m² aus demselben Park raus (Düsseldorf-Flingern, 20.04.2026). Deshalb gibt es neben
  „passt“ die Arten „teilbar“, „Kombination“ (mehrere Einheiten eines Projekts) und „größer“.
- Die Untergrenze im Suchprofil ist kein Wunsch. Gilt nur sie, zählt bis zum Doppelten als passend.
- Ein fehlender Wert (Hallenhöhe, Rampen) schließt nicht aus, er steht unter „prüfen“. Ist die
  Höhe gepflegt und zu niedrig, fällt die Einheit raus. Rampen sind nur ein Hinweis – gepflegt bei
  weniger als der Hälfte der Einheiten, und gezählt wird uneinheitlich.
- Kühlung, Kran und Gleisanschluss als Bedingung: Vorgeschlagen wird nur, was das am Objekt
  erkennen lässt. Kühlung ist an einer Handvoll Einheiten gepflegt – ein Kühlgesuch lässt sich aus
  den Feldern kaum beantworten, und der Bericht sagt das, statt zwölf ungekühlte Hallen zu nennen.
- „Schon angeboten“ heißt: Es gibt einen Deal des Kontakts zur Einheit oder zu ihrem Projekt (egal
  in welcher Stufe, auch Absage), die Einheit steht mit ID in der Notiz des Suchprofils, oder ihre
  Straße steht dort hinter „Angeboten:“. Steht dieselbe Halle zweimal in Propstack, gilt ein
  Angebot zu einem der beiden Datensätze für beide (bestand.fasse_zwillinge).
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import combinations

from .bestand import ALTBESTAND, VERMARKTUNG, Flaeche
from .felder import (SOFORT, entfernung_km, gleiche_ortsschluessel, im_polygon, ort_grundname, ort_schluessel,
                     quartal_text, quartal_von, quartale_zwischen)
from .gesuch import WUNSCH, Gesuch

PASST, TEILBAR, KOMBINATION, GROESSER = "passt", "teilbar", "Kombination", "größer"
TOLERANZ = 0.10                    # ±10 % um den Flächenwunsch
GROESSER_BIS = 2.0                 # bis zum Doppelten der Obergrenze: „größer – Teilfläche erfragen“
SPAETER_QUARTALE = 2               # Einheit wird mehr als zwei Quartale nach dem Bedarf frei: kein Vorschlag
ORT_UMKREIS_KM = 8.0               # „Orte“ ohne Koordinaten: Ort selbst oder so nah an seiner Mitte
# Der Umkreis im Suchprofil ist von Hand gezogen. Das Team bietet auch knapp dahinter an (Gesuch mit
# 17 km: Angebote bei 17 und 20 km, 24.11.2026). Bis 25 % darüber – mindestens 5, höchstens 10 km –
# gilt als „knapp außerhalb“: Vorschlag mit Abzug und Hinweis. Die Obergrenze, weil 25 % von einem
# 114-km-Umkreis kein „knapp“ mehr sind.
KNAPP_FAKTOR, KNAPP_MIN_KM, KNAPP_MAX_KM = 0.25, 5.0, 10.0
ZUSCHLAG_GESCHAETZT_KM = 10.0      # Lage nur über PLZ-Gebiet geschätzt
BUNDESWEIT_AB_LAENDERN = 8         # so viele Bundesländer angekreuzt: das Profil hat faktisch kein Gebiet
BUNDESWEIT_GRAD = (5.0, 7.0)       # ein gezeichnetes Gebiet über mehr als 5° Breite und 7° Länge ist Deutschland
BUNDESWEIT_UMKREIS_KM = 300.0
KO_BESONDERHEITEN = ("Kühlung", "Kran", "Gleisanschluss")
_PUNKTE_ART = {PASST: 100.0, TEILBAR: 85.0, KOMBINATION: 80.0, GROESSER: 50.0}


@dataclass
class Vorschlag:
    art: str
    flaechen: list[Flaeche]
    summe: float
    entfernung_km: float | None
    punkte: float
    gruende: list[str] = field(default_factory=list)
    pruefen: list[str] = field(default_factory=list)
    neu: bool = False
    weitere_im_projekt: list[int] = field(default_factory=list)    # IDs weiterer passender Einheiten
    dubletten: list[int] = field(default_factory=list)             # dieselbe Halle ein zweites Mal in Propstack
    neue_flaeche: bool = False                                     # eine der Einheiten ist neu im Bestand

    @property
    def erste(self) -> Flaeche:
        return self.flaechen[0]

    @property
    def schluessel(self):
        return ("p", self.erste.projekt_id) if self.erste.projekt_id else ("e", self.erste.id)


@dataclass
class Ergebnis:
    gesuch: Gesuch
    vorschlaege: list[Vorschlag] = field(default_factory=list)
    schon_angeboten: int = 0           # passende Einheiten, die der Kontakt schon kennt
    spaeter_frei: int = 0              # passende Einheiten, die erst nach dem Bedarf frei werden
    ohne_nachweis: dict[str, int] = field(default_factory=dict)   # K.-o.-Besonderheit → Einheiten ohne Nachweis
    grund_ohne_vorschlag: str = ""


@dataclass
class Angebote:
    """Was ein Kontakt schon kennt – aus den Deals (`GET /v1/client_properties`)."""
    einheiten: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    projekte: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))

    @classmethod
    def aus_deals(cls, deals: list[dict]) -> "Angebote":
        a = cls()
        for deal in deals:
            kontakt = deal.get("client_id")
            if not kontakt:
                continue
            if deal.get("property_id"):
                a.einheiten[kontakt].add(int(deal["property_id"]))
            if deal.get("project_id"):
                a.projekte[kontakt].add(int(deal["project_id"]))
        return a

    def kennt(self, kontakt_id: int, f: Flaeche) -> bool:
        """Deal zur Einheit, zu ihrem Projekt – oder zum zweiten Datensatz derselben Halle."""
        einheiten = self.einheiten.get(kontakt_id, ())
        if f.id in einheiten or any(z in einheiten for z in f.zwillinge):
            return True
        projekte = self.projekte.get(kontakt_id, ())
        return any(p in projekte for p in (f.projekt_id, *f.zwillings_projekte) if p is not None)


def _norm(text: str) -> str:
    t = re.sub(r"str\.|strasse\b", "straße", (text or "").casefold())
    return re.sub(r"[ \t]+", " ", t)


def _ganzes_wort(wort: str, text: str) -> re.Match | None:
    return re.search(rf"(?<![\w-]){re.escape(wort)}(?![\w-])", text) if wort else None


def _hausnummern(text: str) -> set[int]:
    """„30“ → {30}, „49-53“ → {49 … 53}, „12a“ → {12}."""
    m = re.search(r"(\d+)\s*[a-z]?(?:\s*[-–/]\s*(\d+))?\s*[a-z]?\s*$", (text or "").casefold())
    if not m:
        return set()
    von, bis = int(m.group(1)), int(m.group(2) or m.group(1))
    return set(range(von, bis + 1)) if von <= bis <= von + 60 else {von}


_EINHEIT_NR = re.compile(r"\b(?:unit|halle|einheit|geb(?:ä|ae)ude)\s*([\d.]+)")
# Ortsnamen, die in einer Notiz auch etwas anderes heißen
_KEIN_ORTSHINWEIS = {"halle", "hof", "lage"}


def _in_notiz_angeboten(g: Gesuch, f: Flaeche, bekannte_orte: frozenset[str] = frozenset(),
                        eindeutige_orte: frozenset[str] = frozenset()) -> bool:
    """Steht die Fläche schon in der Notiz des Suchprofils? Mit ID – oder hinter „Angeboten:“, so wie
    das Team es schreibt (Suchprofil 11656279, gelesen 26.11.2026): „Teilungsweg 30, Essen“,
    „Im Freihafen 4“, „Märkische Straße Bochum“, „Herne Prologis“, „Herten Unit 2.1 und 2.2“.

    Der Straßenname zählt als Ganzes und als ganzes Wort („Hafenstraße“ steckt nicht in
    „Rheinhafenstraße“, und „Industriestraße“ gibt es in jeder Stadt). Nennt die Zeile eine
    Hausnummer, eine andere Stadt oder eine andere Unit, ist es eine andere Fläche. Ein Ort allein
    („Dorfen“) zählt nur, wenn es dort genau ein Objekt im Bestand gibt."""
    if f.id in g.genannte_einheiten or any(z in g.genannte_einheiten for z in f.zwillinge):
        return True
    if not g.angeboten_text:
        return False
    ort = ort_grundname(f.ort)
    strasse = re.sub(r"[\s,]*\d+\s*[a-z]?(?:\s*[-–/]\s*\d+\s*[a-z]?)?\s*$", "", _norm(f.strasse)).strip(" ,")
    if not strasse or strasse[0].isdigit() or strasse in ("straße", ort) or strasse in bekannte_orte \
            or (len(strasse) < 6 and " " not in strasse):
        strasse = ""
    hausnummern = _hausnummern(f.hausnummer) or _hausnummern(f.strasse)
    eigner = re.split(r"[\s,(]+", f.eigentuemer.strip())[0].casefold() if f.eigentuemer else ""
    einheit = _EINHEIT_NR.search(f.kennung)
    for zeile in re.split(r"[\n;]+", _norm(g.angeboten_text)):
        genannt = _EINHEIT_NR.search(zeile)
        if genannt and einheit:                                   # „Industriering 21 Unit 2“ ist nicht Unit 1
            nummern = {genannt.group(1).rstrip(".")} | {n.rstrip(".") for n in re.findall(r"\bund\s+([\d.]+)", zeile[genannt.end():])}
            if einheit.group(1).rstrip(".") not in nummern:
                continue
        nennt_ort = bool(_ganzes_wort(ort, zeile)) and ort not in _KEIN_ORTSHINWEIS
        if nennt_ort and zeile.strip(" .,-") == ort and ort in eindeutige_orte:
            return True
        if strasse and (m := _ganzes_wort(strasse, zeile)):
            nummer = re.match(r"\s*(\d+)", zeile[m.end():])
            if nummer and hausnummern and int(nummer.group(1)) not in hausnummern:
                continue
            if not nennt_ort and any(_ganzes_wort(o, zeile) for o in bekannte_orte if o != ort and o not in _KEIN_ORTSHINWEIS):
                continue
            return True
        if nennt_ort and len(ort) >= 4:
            if len(eigner) >= 4 and _ganzes_wort(eigner, zeile):   # „Herne Prologis“, „Mileway Oberhausen“
                return True
            if genannt and einheit:                               # „Herten Unit 2.1 und 2.2“
                return True
    return False


def _bundesweit(g: Gesuch) -> bool:
    """Hat das Profil faktisch kein Gebiet? Dann ist jede Auswahl von fünf aus Hunderten Zufall."""
    if g.gebiet == "ohne":
        return True
    if g.gebiet == "Bundesland":
        return len(g.laender) >= BUNDESWEIT_AB_LAENDERN
    if g.gebiet == "Gebiet":
        breiten, laengen = [p[1] for p in g.polygon], [p[0] for p in g.polygon]
        return max(breiten) - min(breiten) > BUNDESWEIT_GRAD[0] and max(laengen) - min(laengen) > BUNDESWEIT_GRAD[1]
    if g.gebiet == "Umkreis":
        return g.umkreis_km >= BUNDESWEIT_UMKREIS_KM
    return False


class Abgleich:
    def __init__(self, flaechen: list[Flaeche], angebote: Angebote, heute: date, neu_tage: int = 7, je_gesuch: int = 5):
        self.flaechen = flaechen
        self.angebote = angebote
        self.heute = heute
        self.jetzt = quartal_von(heute)
        self.neu_ab = (heute - timedelta(days=neu_tage)).isoformat()
        self.veraltet_vor = (heute - timedelta(days=365)).isoformat()
        self.je_gesuch = je_gesuch
        mitten: dict[str, list] = defaultdict(list)
        for f in flaechen:
            if f.lat is not None and not f.lage_geschaetzt and f.ort:
                mitten[ort_schluessel(f.ort)].append((f.lat, f.lng))
        self.ortsmitten = {ort: (sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps)) for ort, ps in mitten.items()}
        self.bekannte_orte = frozenset(ort_grundname(f.ort) for f in flaechen if f.ort) - {""}
        je_ort: dict[str, set] = defaultdict(set)
        for f in flaechen:
            je_ort[ort_grundname(f.ort)].add(("p", f.projekt_id) if f.projekt_id else ("e", f.id))
        self.eindeutige_orte = frozenset(ort for ort, objekte in je_ort.items() if ort and len(objekte) == 1)
        self._mitte_je_ort: dict[str, tuple[float, float] | None] = {}

    def _ortsmitte(self, ort: str) -> tuple[float, float] | None:
        """Mitte eines Orts aus dem Bestand. „Mülheim“ findet „Mülheim an der Ruhr“, „Frankfurt (Oder)“
        aber nicht „Frankfurt am Main“."""
        if ort not in self._mitte_je_ort:
            schluessel = ort_schluessel(ort)
            self._mitte_je_ort[ort] = self.ortsmitten.get(schluessel) or next(
                (mitte for k, mitte in self.ortsmitten.items() if gleiche_ortsschluessel(k, schluessel)), None)
        return self._mitte_je_ort[ort]

    # --- Gebiet ---------------------------------------------------------------------------

    def im_gebiet(self, g: Gesuch, f: Flaeche) -> tuple[bool, float | None]:
        """(liegt im Gebiet, Entfernung zur Mitte in km oder None)."""
        if g.gebiet == "Umkreis":
            if f.lat is None:
                return False, None
            abstand = entfernung_km(g.lat, g.lng, f.lat, f.lng)
            grenze = g.umkreis_km + min(max(g.umkreis_km * KNAPP_FAKTOR, KNAPP_MIN_KM), KNAPP_MAX_KM)
            grenze += ZUSCHLAG_GESCHAETZT_KM if f.lage_geschaetzt == "PLZ-Gebiet" else 0
            return abstand <= grenze, abstand
        if g.gebiet == "Gebiet":
            if f.lat is None:
                return False, None
            return im_polygon(f.lat, f.lng, g.polygon), None
        if g.gebiet == "Orte":
            eigener = ort_schluessel(f.ort)
            beste = None
            for ort in g.orte:
                if gleiche_ortsschluessel(eigener, ort_schluessel(ort)):
                    return True, None
                mitte = self._ortsmitte(ort)
                if mitte and f.lat is not None:
                    abstand = entfernung_km(mitte[0], mitte[1], f.lat, f.lng)
                    beste = abstand if beste is None else min(beste, abstand)
            return (beste is not None and beste <= ORT_UMKREIS_KM), None      # eine Kilometerzahl hätte hier keinen klaren Bezugspunkt
        if g.gebiet == "Bundesland":
            return f.land in g.laender, None
        return True, None

    # --- Einzelne Bedingungen -------------------------------------------------------------

    def _zeit(self, g: Gesuch, f: Flaeche) -> tuple[bool, str | None, str | None]:
        """(kommt zeitlich in Frage, Grund, Prüfhinweis)."""
        if f.bezug is None:
            return True, None, (f"Bezug: „{f.bezug_text}“" if f.bezug_text else "Bezug nicht gepflegt")
        frei = max(f.bezug, self.jetzt)
        bedarf = max(g.ab_wann, self.jetzt) if g.ab_wann else self.jetzt
        abstand = quartale_zwischen(bedarf, frei)
        frei_text = "sofort" if f.bezug == SOFORT or f.bezug <= self.jetzt else quartal_text(f.bezug)
        # Ohne Termin im Gesuch gilt „möglichst bald“, mit vier statt zwei Quartalen Spielraum
        if abstand > (SPAETER_QUARTALE if g.ab_wann else 4):
            return False, None, None
        if abstand < -4:
            return True, None, f"frei ab {frei_text}, Bedarf erst ab {quartal_text(g.ab_wann)}"
        return True, f"frei ab {frei_text}", None

    def _hoehe(self, g: Gesuch, f: Flaeche) -> tuple[bool, str | None, str | None]:
        if g.hoehe_min is None:
            return True, None, None
        if f.hoehe is None:
            return True, None, f"Hallenhöhe nicht gepflegt (gewünscht ab {_komma(g.hoehe_min)} m)"
        if f.hoehe < g.hoehe_min - 0.5:
            return False, None, None
        if f.hoehe < g.hoehe_min:
            return True, None, f"Höhe {_komma(f.hoehe)} m – knapp unter den gewünschten {_komma(g.hoehe_min)} m"
        return True, f"Höhe {_komma(f.hoehe)} m", None

    def _art(self, g: Gesuch, f: Flaeche) -> str | None:
        """Wie passt die Fläche einer einzelnen Einheit? None = gar nicht (zu klein → Kombination)."""
        if not f.flaeche:
            return None
        unten, oben = g.flaeche_von * (1 - TOLERANZ), g.flaeche_bis * (1 + TOLERANZ)
        if unten <= f.flaeche <= oben:
            return PASST
        if f.flaeche > oben:
            if f.teilbar_ab is not None and f.teilbar_ab <= oben:
                return TEILBAR
            if f.flaeche <= g.flaeche_bis * GROESSER_BIS:
                return GROESSER
        return None

    # --- Bewertung ------------------------------------------------------------------------

    def _bewerte(self, g: Gesuch, art: str, flaechen: list[Flaeche], abstand: float | None) -> Vorschlag:
        erste = flaechen[0]
        summe = sum(f.flaeche or 0 for f in flaechen)
        punkte = _PUNKTE_ART[art]
        gruende: list[str] = []
        pruefen: list[str] = []

        mitte = (g.flaeche_von + g.flaeche_bis) / 2
        if art in (PASST, KOMBINATION):
            punkte += 15 * max(0.0, 1 - abs(summe - mitte) / mitte)
        if art == TEILBAR:
            gruende.append(f"teilbar ab {_m2(erste.teilbar_ab)}")
        if art == KOMBINATION:
            gruende.append(f"{len(flaechen)} Einheiten im selben Projekt, zusammen {_m2(summe)}")
        if art == GROESSER:
            pruefen.append("größer als gesucht – Teilfläche beim Eigentümer erfragen")
        for f in flaechen:
            if f.flaeche_gesamt:
                pruefen.append(f"frei sind {_m2(f.flaeche)} von {_m2(f.flaeche_gesamt)} (Feld „Lagerfläche verfügbar“)")
            if f.flaeche_hinweis:
                pruefen.append(f"Fläche unklar: Lagerfläche {_m2(f.flaeche)}, {f.flaeche_hinweis}")

        if abstand is not None and g.gebiet == "Umkreis" and g.umkreis_km:
            punkte += 15 * max(0.0, 1 - abstand / g.umkreis_km)
            if abstand > g.umkreis_km:
                punkte -= 10
                pruefen.append(f"{abstand:.0f} km – knapp außerhalb des Umkreises ({g.umkreis_km:.0f} km)")
        if erste.lage_geschaetzt:
            punkte -= 3
            pruefen.append(f"Lage geschätzt (über {erste.lage_geschaetzt}) – Koordinaten fehlen in Propstack")

        _, grund, hinweis = self._hoehe(g, erste)
        if grund:
            punkte += 5
            gruende.append(grund)
        if hinweis:
            pruefen.append(hinweis)

        if g.rampen_min is not None:
            werte = [f.rampen for f in flaechen if f.rampen is not None]
            rampen = sum(werte) if werte else None
            tore = sum(f.tore_ebenerdig or 0 for f in flaechen)
            if rampen is None:
                punkte -= 2
                pruefen.append(f"Rampen nicht gepflegt (gewünscht {_komma(g.rampen_min)})")
            elif rampen >= g.rampen_min:
                punkte += 5
                gruende.append(f"{_komma(rampen)} {'Rampe' if rampen == 1 else 'Rampen'}")
            elif rampen == 0:
                punkte -= 8
                pruefen.append(f"keine Rampen laut Objekt (gewünscht {_komma(g.rampen_min)})"
                               + (f", {_komma(tore)} ebenerdige {'Tor' if tore == 1 else 'Tore'}" if tore else ""))
            else:
                punkte -= 8
                pruefen.append(f"nur {_komma(rampen)} {'Rampe' if rampen == 1 else 'Rampen'} gepflegt (gewünscht {_komma(g.rampen_min)})")

        _, grund, hinweis = self._zeit(g, erste)
        if grund:
            punkte += 5
            gruende.append(grund)
        if hinweis:
            pruefen.append(hinweis)

        for besonderheit in g.besonderheiten:
            name = besonderheit.removesuffix(WUNSCH)
            ist_wunsch = besonderheit.endswith(WUNSCH)
            if name in erste.merkmale:
                punkte += 5 if ist_wunsch else 10
                gruende.append(f"{name} laut Objekt")
            elif name in ("24/7", "ebenerdige Andienung", "Freifläche", "Produktion/Werkstatt", "Sprinkler"):
                pruefen.append(f"{name}{' gewünscht' if ist_wunsch else ' gefordert'} – am Objekt nicht gepflegt")
            elif not ist_wunsch:
                punkte -= 5
                pruefen.append(f"{name} gefordert – am Objekt nicht gepflegt")

        if erste.gruppe == VERMARKTUNG:
            punkte += 5
        elif erste.gruppe == ALTBESTAND:
            punkte -= 10
            pruefen.append("Altbestand ohne Propstack-Status – Verfügbarkeit vor dem Angebot prüfen")

        if erste.voll_vermietet_laut_feld:
            punkte -= 15
            pruefen.append("Feld „Vermietungsstand“ sagt 100 % – vor dem Angebot klären, ob die Fläche frei ist")
        if erste.geaendert and erste.geaendert < self.veraltet_vor:
            punkte -= 5
            pruefen.append(f"Datensatz seit {erste.geaendert[5:7]}/{erste.geaendert[:4]} nicht geändert")

        neue_flaeche = any(f.angelegt >= self.neu_ab for f in flaechen)
        if neue_flaeche:
            punkte += 8
            gruende.append("neu im Bestand")
        return Vorschlag(art=art, flaechen=flaechen, summe=summe, entfernung_km=abstand, punkte=round(punkte, 1),
                         gruende=gruende, pruefen=pruefen, neu=neue_flaeche or g.angelegt >= self.neu_ab,
                         dubletten=[z for f in flaechen for z in f.zwillinge], neue_flaeche=neue_flaeche)

    # --- Der Abgleich für ein Gesuch ------------------------------------------------------

    def _kombination(self, g: Gesuch, kleine: list[Flaeche]) -> list[Flaeche] | None:
        """Wenige Einheiten eines Projekts, deren Summe in den Wunsch fällt. Bevorzugt: möglichst
        wenige Einheiten, dann die Summe nächst der Mitte."""
        unten, oben = g.flaeche_von * (1 - TOLERANZ), g.flaeche_bis * (1 + TOLERANZ)
        mitte = (g.flaeche_von + g.flaeche_bis) / 2
        kandidaten = sorted(kleine, key=lambda f: -(f.flaeche or 0))[:10]
        for anzahl in (2, 3, 4):
            passende = [c for c in combinations(kandidaten, anzahl) if unten <= sum(f.flaeche for f in c) <= oben]
            if passende:
                return list(min(passende, key=lambda c: abs(sum(f.flaeche for f in c) - mitte)))
        return None

    def pruefe(self, g: Gesuch) -> Ergebnis:
        e = Ergebnis(gesuch=g)
        if not g.flaeche_von or not g.flaeche_bis:
            e.grund_ohne_vorschlag = "Fläche im Suchprofil nicht lesbar"
            return e
        ko = [b for b in g.besonderheiten if b in KO_BESONDERHEITEN]

        einzelne: list[Vorschlag] = []
        kleine: dict[int, list[tuple[Flaeche, float | None]]] = defaultdict(list)
        unten = g.flaeche_von * (1 - TOLERANZ)
        for f in self.flaechen:
            if not f.flaeche or g.kontakt_id in f.eigentuemer_kontakt_ids:
                continue
            drin, abstand = self.im_gebiet(g, f)
            if not drin:
                continue
            art = self._art(g, f)
            zu_klein = art is None and f.flaeche < unten and f.projekt_id and f.flaeche >= unten / 4
            if art is None and not zu_klein:
                continue
            if not self._hoehe(g, f)[0]:
                continue
            if not self._zeit(g, f)[0]:
                if art:
                    e.spaeter_frei += 1
                continue
            fehlt = [b for b in ko if b not in f.merkmale]
            if fehlt:
                if art:
                    for b in fehlt:
                        e.ohne_nachweis[b] = e.ohne_nachweis.get(b, 0) + 1
                continue
            if self.angebote.kennt(g.kontakt_id, f) or _in_notiz_angeboten(g, f, self.bekannte_orte, self.eindeutige_orte):
                if art:
                    e.schon_angeboten += 1
                continue
            if zu_klein:
                kleine[f.projekt_id].append((f, abstand))
            else:
                einzelne.append(self._bewerte(g, art, [f], abstand))

        vorschlaege = einzelne
        for teile in kleine.values():
            if len(teile) >= 2 and (kombi := self._kombination(g, [f for f, _ in teile])):
                abstand = next((a for f, a in teile if f is kombi[0]), None)
                vorschlaege.append(self._bewerte(g, KOMBINATION, kombi, abstand))

        # Je Projekt nur der beste Vorschlag; die übrigen passenden Einheiten werden genannt. Ist eine
        # davon neu im Bestand, bleibt das sichtbar – sonst verschwindet sie im Lauf „nur neu“ hinter
        # einer älteren Einheit desselben Projekts.
        je_schluessel: dict = {}
        for v in sorted(vorschlaege, key=lambda v: -v.punkte):
            kopf = je_schluessel.get(v.schluessel)
            if kopf is None:
                je_schluessel[v.schluessel] = v
                continue
            kopf.weitere_im_projekt.extend(f.id for f in v.flaechen)
            if v.neue_flaeche and not kopf.neue_flaeche:
                kopf.neue_flaeche = kopf.neu = True
                kopf.gruende.append("weitere Einheit im Projekt neu im Bestand")
        e.vorschlaege = sorted(je_schluessel.values(), key=lambda v: -v.punkte)
        if _bundesweit(g) and e.vorschlaege:
            # Ohne Gebiet ist jede Auswahl von fünf aus Hunderten Zufall (Stichprobe 26.11.2026: drei
            # Hallen in Bitterfeld, Duisburg und Dresden für ein Gesuch ohne Ort). Gezählt wird, gezeigt nicht.
            # Dasselbe gilt für ein Profil, das alle 16 Bundesländer ankreuzt oder ganz Deutschland umrandet.
            e.grund_ohne_vorschlag = (f"kein Gebiet im Suchprofil – {len(e.vorschlaege)} passende Objekte bundesweit; "
                                      "Ort, Umkreis oder Bundesland eintragen")
            e.vorschlaege = []
            return e
        if not e.vorschlaege:
            if e.ohne_nachweis:
                namen = ", ".join(f"{name} ({zahl} passende Flächen ohne Nachweis)" for name, zahl in e.ohne_nachweis.items())
                e.grund_ohne_vorschlag = f"Bedingung am Objekt nicht gepflegt: {namen} – von Hand suchen"
            elif e.schon_angeboten:
                e.grund_ohne_vorschlag = "alles Passende ist schon angeboten"
            elif e.spaeter_frei:
                e.grund_ohne_vorschlag = "Passendes wird erst nach dem Bedarf frei"
            else:
                e.grund_ohne_vorschlag = "nichts Passendes im Bestand"
        return e


def _komma(wert: float) -> str:
    return f"{wert:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def _m2(wert: float | None) -> str:
    return f"{wert:,.0f} m²".replace(",", ".") if wert else "– m²"
