from __future__ import annotations

import logging
from statistics import median

from . import config
from .models import ComparableZeile, RegionStats

logger = logging.getLogger(__name__)


def _median(werte: list[float]) -> float | None:
    return round(median(werte), 2) if werte else None


def _stats(ebene: str, key: str, label: str, zeilen: list[ComparableZeile]) -> RegionStats:
    kaltmieten = [z.kaltmiete_eur_qm for z in zeilen if z.kaltmiete_eur_qm is not None]
    nebenkosten = [z.nebenkosten_eur_qm for z in zeilen if z.nebenkosten_eur_qm is not None]
    effektiv = [z.effektivmiete_eur_qm for z in zeilen if z.effektivmiete_eur_qm is not None]
    flaechen = [z.flaeche_qm for z in zeilen if z.flaeche_qm is not None]
    daten = [z.datum for z in zeilen if z.datum]

    # n zählt Report-ZEILEN (Laufzeit-Optionen bzw. Einheiten); n_objekte die
    # dahinterliegenden Standorte – bei Laufzeitstaffeln ist n größer.
    # Gruppiert wird über die ADRESSE: in Propstack tragen bei Multi-Unit-
    # Standorten mehrere Einheiten denselben Objektnamen, über den Namen
    # würden sie fälschlich zu einem Objekt verschmelzen.
    standorte = {(z.adresse or z.objekt or z.datei) for z in zeilen}
    objekte = sorted({(z.objekt or z.adresse or z.datei) for z in zeilen})

    return RegionStats(
        ebene=ebene,
        key=key,
        label=label,
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


def aggregiere(zeilen: list[ComparableZeile]) -> list[RegionStats]:
    """Median + Spanne + n pro Region (Task-Vorgabe).

    Zwei Ebenen: Leitregion (PLZ 2-stellig) ab MIN_N_LEITREGION Datenpunkten,
    Postleitzone (1-stellig) immer – plus eine Gesamtzeile. Zeilen mit
    Ausschlussgrund gehen NICHT ein.
    """
    verwertbar = [z for z in zeilen if z.verwertbar]
    if not verwertbar:
        logger.warning("Keine verwertbaren Zeilen – keine Statistik möglich")
        return []

    nach_leitregion: dict[str, list[ComparableZeile]] = {}
    nach_zone: dict[str, list[ComparableZeile]] = {}
    for zeile in verwertbar:
        if zeile.region_key:
            nach_leitregion.setdefault(zeile.region_key, []).append(zeile)
        if zeile.zone_key:
            nach_zone.setdefault(zeile.zone_key, []).append(zeile)

    ergebnis: list[RegionStats] = []

    leitregionen = [
        _stats("leitregion", key, gruppe[0].region_label or key, gruppe)
        for key, gruppe in sorted(nach_leitregion.items())
        if len(gruppe) >= config.MIN_N_LEITREGION
    ]
    duenn = len(nach_leitregion) - len(leitregionen)
    if duenn:
        logger.info(
            "%d Leitregion(en) mit weniger als n=%d – nur in der Postleitzone ausgewiesen",
            duenn, config.MIN_N_LEITREGION,
        )
    ergebnis.extend(sorted(leitregionen, key=lambda s: (-s.n, s.key)))

    ergebnis.extend(
        _stats("zone", key, gruppe[0].zone_label or key, gruppe)
        for key, gruppe in sorted(nach_zone.items())
    )

    ergebnis.append(_stats("gesamt", "*", "Alle Regionen", verwertbar))
    return ergebnis


def leitregionen(stats: list[RegionStats]) -> list[RegionStats]:
    return [s for s in stats if s.ebene == "leitregion"]


def zonen(stats: list[RegionStats]) -> list[RegionStats]:
    return [s for s in stats if s.ebene == "zone"]


def gesamt(stats: list[RegionStats]) -> RegionStats | None:
    for s in stats:
        if s.ebene == "gesamt":
            return s
    return None
