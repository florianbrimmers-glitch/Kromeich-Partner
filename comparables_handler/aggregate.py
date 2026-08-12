from __future__ import annotations

import logging
from statistics import median

from . import config
from .models import ComparableZeile, RegionStats

logger = logging.getLogger(__name__)

OHNE_ART = "ohne Angabe"


def _median(werte: list[float]) -> float | None:
    return round(median(werte), 2) if werte else None


def _stats(
    ebene: str, key: str, label: str, zeilen: list[ComparableZeile], nutzungsart: str = ""
) -> RegionStats:
    kaltmieten = [z.kaltmiete_eur_qm for z in zeilen if z.kaltmiete_eur_qm is not None]
    nebenkosten = [z.nebenkosten_eur_qm for z in zeilen if z.nebenkosten_eur_qm is not None]
    effektiv = [z.effektivmiete_eur_qm for z in zeilen if z.effektivmiete_eur_qm is not None]
    flaechen = [z.flaeche_qm for z in zeilen if z.flaeche_qm is not None]
    daten = [z.datum for z in zeilen if z.datum]

    # n zählt Report-ZEILEN (Laufzeit-Optionen bzw. Flächen); n_objekte die
    # dahinterliegenden Standorte – bei Laufzeitstaffeln ist n größer.
    # Gruppiert wird über PLZ + ADRESSE:
    #  - über den Objektnamen allein würden Multi-Unit-Standorte verschmelzen,
    #    weil Propstack die Einheiten eines Standorts gleich benennt;
    #  - über die Adresse allein würden gleichnamige Straßen in verschiedenen
    #    Orten verschmelzen ("Hauptstraße 1" gibt es tausendfach).
    standorte = {(z.plz, z.adresse or z.objekt or z.datei) for z in zeilen}
    objekte = sorted({(z.objekt or z.adresse or z.datei) for z in zeilen})

    return RegionStats(
        ebene=ebene,
        key=key,
        label=label,
        nutzungsart=nutzungsart,
        n=len(zeilen),
        n_objekte=len(standorte),
        n_eigene=sum(1 for z in zeilen if z.eigenes_angebot is True),
        n_erhalten=sum(1 for z in zeilen if z.eigenes_angebot is False),
        n_propstack=sum(1 for z in zeilen if z.quelle == config.QUELLE_PROPSTACK),
        n_drive=sum(1 for z in zeilen if z.quelle == config.QUELLE_DRIVE),
        median_kaltmiete=_median(kaltmieten),
        min_kaltmiete=round(min(kaltmieten), 2) if kaltmieten else None,
        max_kaltmiete=round(max(kaltmieten), 2) if kaltmieten else None,
        median_nebenkosten=_median(nebenkosten),
        median_effektivmiete=_median(effektiv),
        median_flaeche=_median(flaechen),
        jüngstes_datum=max(daten) if daten else None,
        objekte=objekte,
    )


def _regionen_einer_art(
    zeilen: list[ComparableZeile], nutzungsart: str
) -> list[RegionStats]:
    """Leitregionen, Einzelwerte, Zonen und Gesamtzeile EINER Flächenart."""
    nach_leitregion: dict[str, list[ComparableZeile]] = {}
    nach_zone: dict[str, list[ComparableZeile]] = {}
    for zeile in zeilen:
        if zeile.region_key:
            nach_leitregion.setdefault(zeile.region_key, []).append(zeile)
        if zeile.zone_key:
            nach_zone.setdefault(zeile.zone_key, []).append(zeile)

    # Belastbare Mediane und Einzelwerte werden getrennt ausgewiesen, aber
    # BEIDE gezeigt. Bekannte Mieten sind rar; eine Region wegen n=1 ganz
    # wegzulassen würde die wertvollste Information verschweigen.
    belastbar: list[RegionStats] = []
    einzeln: list[RegionStats] = []
    for key, gruppe in sorted(nach_leitregion.items()):
        ebene = "leitregion" if len(gruppe) >= config.MIN_N_LEITREGION else "leitregion_einzel"
        stat = _stats(ebene, key, gruppe[0].region_label or key, gruppe, nutzungsart)
        (belastbar if ebene == "leitregion" else einzeln).append(stat)

    ergebnis: list[RegionStats] = []
    ergebnis.extend(sorted(belastbar, key=lambda s: (-s.n, s.key)))
    ergebnis.extend(sorted(einzeln, key=lambda s: (-s.n, s.key)))
    ergebnis.extend(
        _stats("zone", key, gruppe[0].zone_label or key, gruppe, nutzungsart)
        for key, gruppe in sorted(nach_zone.items())
    )
    ergebnis.append(_stats("gesamt", "*", "Alle Regionen", zeilen, nutzungsart))
    return ergebnis


def aggregiere(zeilen: list[ComparableZeile]) -> list[RegionStats]:
    """Median + Spanne + n pro Flächenart und Region (Task-Vorgabe).

    Getrennt JE FLÄCHENART: Hallenmieten (4-8 €/m²) und Büromieten (12-14 €/m²)
    in denselben Median zu werfen ergäbe eine Zahl, die keinen Markt beschreibt.

    Innerhalb einer Flächenart zwei Ebenen: Leitregion (PLZ 2-stellig) mit
    belastbarem Median ab MIN_N_LEITREGION, darunter als Einzelwerte, plus
    Postleitzone und eine Gesamtzeile. Zeilen mit Ausschlussgrund gehen nicht ein.
    """
    verwertbar = [z for z in zeilen if z.verwertbar]
    if not verwertbar:
        logger.warning("Keine verwertbaren Zeilen – keine Statistik möglich")
        return []

    nach_art: dict[str, list[ComparableZeile]] = {}
    for zeile in verwertbar:
        nach_art.setdefault(zeile.nutzungsart or OHNE_ART, []).append(zeile)

    ergebnis: list[RegionStats] = []
    # Flächenarten nach Datenmenge: die belegteste (in der Regel Halle) zuerst
    for art, art_zeilen in sorted(nach_art.items(), key=lambda x: (-len(x[1]), x[0])):
        logger.info("Flächenart %r: %d Datenpunkte", art, len(art_zeilen))
        ergebnis.extend(_regionen_einer_art(art_zeilen, art))

    ergebnis.append(_stats("gesamt", "**", "Alle Flächenarten", verwertbar, ""))
    return ergebnis


# --- Zugriffshelfer ---------------------------------------------------------
def flaechenarten(stats: list[RegionStats]) -> list[str]:
    """Flächenarten in Report-Reihenfolge (datenreichste zuerst)."""
    gesehen: list[str] = []
    for s in stats:
        if s.nutzungsart and s.nutzungsart not in gesehen:
            gesehen.append(s.nutzungsart)
    return gesehen


def _filter(stats: list[RegionStats], ebene: str, nutzungsart: str | None) -> list[RegionStats]:
    return [
        s for s in stats
        if s.ebene == ebene and (nutzungsart is None or s.nutzungsart == nutzungsart)
    ]


def leitregionen(stats: list[RegionStats], nutzungsart: str | None = None) -> list[RegionStats]:
    """Leitregionen mit belastbarem Median (n >= MIN_N_LEITREGION)."""
    return _filter(stats, "leitregion", nutzungsart)


def einzelwerte(stats: list[RegionStats], nutzungsart: str | None = None) -> list[RegionStats]:
    """Leitregionen mit n < MIN_N_LEITREGION – Einzelwerte, kein Median."""
    return _filter(stats, "leitregion_einzel", nutzungsart)


def zonen(stats: list[RegionStats], nutzungsart: str | None = None) -> list[RegionStats]:
    return _filter(stats, "zone", nutzungsart)


def art_gesamt(stats: list[RegionStats], nutzungsart: str) -> RegionStats | None:
    """Gesamtzeile EINER Flächenart."""
    for s in stats:
        if s.ebene == "gesamt" and s.nutzungsart == nutzungsart and s.key == "*":
            return s
    return None


def gesamt(stats: list[RegionStats]) -> RegionStats | None:
    """Gesamtzeile über ALLE Flächenarten."""
    for s in stats:
        if s.ebene == "gesamt" and s.key == "**":
            return s
    return None
