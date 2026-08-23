from __future__ import annotations

import logging
from dataclasses import dataclass

from . import config, geo
from .models import HallCard, SearchProfile

logger = logging.getLogger(__name__)

# Toleranz um den angegebenen Flächenbedarf – knapp daneben ist oft trotzdem passend
UNTERGRENZE_FAKTOR = 0.6
OBERGRENZE_FAKTOR = 1.6

# Sortier-Aufschläge (in "Pseudo-Kilometern") für unvollständig gepflegte Objekte
STRAFE_OHNE_KOORDINATEN = 10_000.0
STRAFE_OHNE_FLAECHE = 500.0


@dataclass
class Zentrum:
    lat: float | None = None
    lng: float | None = None
    quelle: str = "unbekannt"

    def bekannt(self) -> bool:
        return self.lat is not None and self.lng is not None


def finde_zentrum(ort: str, karten: list[HallCard]) -> Zentrum:
    """Suchmittelpunkt bestimmen: PLZ-Leitregion, sonst Ortsname im Bestand.

    Ist beides erfolglos, wird ohne Umkreisfilter gearbeitet statt ein leeres
    Deck auszuliefern."""
    aus_plz = geo.zentrum_aus_plz(ort)
    if aus_plz:
        return Zentrum(aus_plz[0], aus_plz[1], "plz")

    gesucht = geo.normalisiere(ort)
    if gesucht:
        treffer = [
            k for k in karten
            if k.lat is not None and k.lng is not None and k.stadt
            and gesucht in geo.normalisiere(k.stadt)
        ]
        if treffer:
            lat = sum(k.lat for k in treffer) / len(treffer)
            lng = sum(k.lng for k in treffer) / len(treffer)
            return Zentrum(lat, lng, "bestand")

    logger.info("Kein Suchmittelpunkt für '%s' – Umkreisfilter wird ausgelassen", ort)
    return Zentrum()


def _flaeche_passt(karte: HallCard, minimum: int, maximum: int) -> bool:
    if karte.flaeche is None or (minimum == 0 and maximum == 0):
        return True
    if minimum and karte.flaeche < minimum * UNTERGRENZE_FAKTOR:
        return False
    if maximum and karte.flaeche > maximum * OBERGRENZE_FAKTOR:
        return False
    return True


def _flaechen_abweichung(karte: HallCard, minimum: int, maximum: int) -> float:
    """0.0 = innerhalb des Wunschbereichs, sonst relative Abweichung."""
    if karte.flaeche is None:
        return STRAFE_OHNE_FLAECHE
    if minimum and karte.flaeche < minimum:
        return (minimum - karte.flaeche) / max(minimum, 1)
    if maximum and karte.flaeche > maximum:
        return (karte.flaeche - maximum) / max(maximum, 1)
    return 0.0


def _mit_entfernung(karte: HallCard, zentrum: Zentrum) -> HallCard:
    if not zentrum.bekannt() or karte.lat is None or karte.lng is None:
        return karte.model_copy(update={"entfernung_km": None})
    km = geo.distanz_km(zentrum.lat, zentrum.lng, karte.lat, karte.lng)
    return karte.model_copy(update={"entfernung_km": round(km, 1)})


def _filtere(karten: list[HallCard], profil: SearchProfile, zentrum: Zentrum, radius_km: int) -> list[HallCard]:
    minimum, maximum = profil.spanne()
    ergebnis: list[HallCard] = []
    for karte in karten:
        if not _flaeche_passt(karte, minimum, maximum):
            continue
        angereichert = _mit_entfernung(karte, zentrum)
        if angereichert.entfernung_km is not None and angereichert.entfernung_km > radius_km:
            continue
        ergebnis.append(angereichert)
    return ergebnis


def _sortiere(karten: list[HallCard], profil: SearchProfile) -> list[HallCard]:
    minimum, maximum = profil.spanne()

    def schluessel(karte: HallCard) -> tuple[float, int]:
        entfernung = karte.entfernung_km if karte.entfernung_km is not None else STRAFE_OHNE_KOORDINATEN
        # 20 km Aufschlag pro 100 % Flächenabweichung: Lage schlägt Fläche, aber nicht beliebig
        score = entfernung + _flaechen_abweichung(karte, minimum, maximum) * 20.0
        return (score, karte.id)  # id als Tiebreaker → deterministische Reihenfolge

    return sorted(karten, key=schluessel)


def rangliste(karten: list[HallCard], profil: SearchProfile) -> tuple[list[HallCard], Zentrum, int]:
    """Passende Karten in fester Reihenfolge, plus verwendeter Radius.

    Bleiben zu wenige Treffer, wird der Radius verdoppelt, statt ein fast
    leeres Deck auszuliefern."""
    zentrum = finde_zentrum(profil.ort, karten)
    radius = profil.radius_km or config.default_radius_km()

    treffer = _filtere(karten, profil, zentrum, radius)
    while (
        zentrum.bekannt()
        and len(treffer) < config.MIN_CARDS_BEFORE_EXPANSION
        and radius < config.MAX_RADIUS_KM
    ):
        radius = min(radius * 2, config.MAX_RADIUS_KM)
        treffer = _filtere(karten, profil, zentrum, radius)
        logger.info("Zu wenige Treffer – Radius auf %d km erweitert (%d Karten)", radius, len(treffer))

    return _sortiere(treffer, profil), zentrum, radius
