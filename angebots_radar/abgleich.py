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
  Straße steht dort hinter „Angeboten:“.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import combinations

from .bestand import ALTBESTAND, VERMARKTUNG, Flaeche
from .felder import SOFORT, entfernung_km, im_polygon, ort_schluessel, quartal_text, quartal_von, quartale_zwischen
from .gesuch import WUNSCH, Gesuch

PASST, TEILBAR, KOMBINATION, GROESSER = "passt", "teilbar", "Kombination", "größer"
TOLERANZ = 0.10                    # ±10 % um den Flächenwunsch
GROESSER_BIS = 2.0                 # bis zum Doppelten der Obergrenze: „größer – Teilfläche erfragen“
SPAETER_QUARTALE = 2               # Einheit wird mehr als zwei Quartale nach dem Bedarf frei: kein Vorschlag
ORT_UMKREIS_KM = 8.0               # „Orte“ ohne Koordinaten: Ort selbst oder so nah an seiner Mitte
# Der Umkreis im Suchprofil ist von Hand gezogen. Das Team bietet auch knapp dahinter an (Gesuch mit
# 17 km: Angebote bei 17 und 20 km, 24.11.2026). Bis 25 % (mindestens 5 km) darüber gilt als
# „knapp außerhalb“ – Vorschlag mit Abzug und Hinweis.
KNAPP_FAKTOR, KNAPP_MIN_KM = 1.25, 5.0
ZUSCHLAG_GESCHAETZT_KM = 10.0      # Lage nur über PLZ-Gebiet geschätzt
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
        return f.id in self.einheiten.get(kontakt_id, ()) or (
            f.projekt_id is not None and f.projekt_id in self.projekte.get(kontakt_id, ()))


def _in_notiz_angeboten(g: Gesuch, f: Flaeche) -> bool:
    if f.id in g.genannte_einheiten:
        return True
    if not g.angeboten_text:
        return False
    text = g.angeboten_text.casefold()
    # Straße: das erste Wort mit Gewicht („Teilungsweg 30, Essen“, „Klöcknerstraße 55“)
    wort = re.split(r"[\s,]+", f.strasse.strip())[0].casefold() if f.strasse else ""
    if len(wort) >= 7 and not wort[0].isdigit() and wort in text:
        return True
    # „Herne Prologis“, „Mileway Oberhausen“: Ort und Eigentümer in derselben Zeile
    ort = ort_schluessel(f.ort)
    eigner = re.split(r"[\s,(]+", f.eigentuemer.strip())[0].casefold() if f.eigentuemer else ""
    if len(ort) >= 4 and len(eigner) >= 4:
        return any(ort in zeile and eigner in zeile for zeile in re.split(r"[\n/]+", text))
    return False


class Abgleich:
    def __init__(self, flaechen: list[Flaeche], angebote: Angebote, heute: date, neu_tage: int = 7, je_gesuch: int = 5):
        self.flaechen = flaechen
        self.angebote = angebote
        self.heute = heute
        self.jetzt = quartal_von(heute)
        self.neu_ab = (heute - timedelta(days=neu_tage)).isoformat()
        self.je_gesuch = je_gesuch
        mitten: dict[str, list] = defaultdict(list)
        for f in flaechen:
            if f.lat is not None and not f.lage_geschaetzt and f.ort:
                mitten[ort_schluessel(f.ort)].append((f.lat, f.lng))
        self.ortsmitten = {ort: (sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps)) for ort, ps in mitten.items()}

    # --- Gebiet ---------------------------------------------------------------------------

    def im_gebiet(self, g: Gesuch, f: Flaeche) -> tuple[bool, float | None]:
        """(liegt im Gebiet, Entfernung zur Mitte in km oder None)."""
        if g.gebiet == "Umkreis":
            if f.lat is None:
                return False, None
            abstand = entfernung_km(g.lat, g.lng, f.lat, f.lng)
            grenze = max(g.umkreis_km * KNAPP_FAKTOR, g.umkreis_km + KNAPP_MIN_KM)
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
                schluessel = ort_schluessel(ort)
                if eigener and eigener == schluessel:
                    return True, 0.0
                mitte = self.ortsmitten.get(schluessel)
                if mitte and f.lat is not None:
                    abstand = entfernung_km(mitte[0], mitte[1], f.lat, f.lng)
                    beste = abstand if beste is None else min(beste, abstand)
            return (beste is not None and beste <= ORT_UMKREIS_KM), beste
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
            rampen = sum(f.rampen for f in flaechen if f.rampen) if any(f.rampen for f in flaechen) else None
            if rampen is None:
                punkte -= 2
                pruefen.append(f"Rampen nicht gepflegt (gewünscht {_komma(g.rampen_min)})")
            elif rampen >= g.rampen_min:
                punkte += 5
                gruende.append(f"{_komma(rampen)} {'Rampe' if rampen == 1 else 'Rampen'}")
            else:
                punkte -= 8
                pruefen.append(f"nur {_komma(rampen)} Rampen gepflegt (gewünscht {_komma(g.rampen_min)})")

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

        neu = any(f.angelegt >= self.neu_ab for f in flaechen) or g.angelegt >= self.neu_ab
        if any(f.angelegt >= self.neu_ab for f in flaechen):
            punkte += 8
            gruende.append("neu im Bestand")
        return Vorschlag(art=art, flaechen=flaechen, summe=summe, entfernung_km=abstand, punkte=round(punkte, 1),
                         gruende=gruende, pruefen=pruefen, neu=neu)

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
            if self.angebote.kennt(g.kontakt_id, f) or _in_notiz_angeboten(g, f):
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

        # Je Projekt nur der beste Vorschlag; die übrigen passenden Einheiten werden genannt.
        # Dieselbe Halle zweimal in Propstack (gleiche Straße, gleicher Ort, gleiche Fläche) zählt
        # einmal – die Dublette wird genannt (24.11.2026: sieben Hillwood-Einheiten doppelt angelegt).
        je_schluessel: dict = {}
        je_halle: dict = {}
        for v in sorted(vorschlaege, key=lambda v: -v.punkte):
            halle = (ort_schluessel(v.erste.ort), v.erste.strasse.casefold(), round(v.summe)) if v.erste.strasse else None
            if halle and halle in je_halle and je_halle[halle].schluessel != v.schluessel:
                je_halle[halle].dubletten.extend(f.id for f in v.flaechen)
                continue
            if halle:
                je_halle.setdefault(halle, v)
            if v.schluessel in je_schluessel:
                je_schluessel[v.schluessel].weitere_im_projekt.extend(f.id for f in v.flaechen)
            else:
                je_schluessel[v.schluessel] = v
        e.vorschlaege = sorted(je_schluessel.values(), key=lambda v: -v.punkte)
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
