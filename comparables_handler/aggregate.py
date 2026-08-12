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
    # Gruppiert wird über PLZ + ADRESSE:
    #  - über den Objektnamen allein würden Multi-Unit-Standorte verschmelzen,
    #    weil Propstack die Einheiten eines Standorts gleich benennt;
    #  - über die Adresse allein würden gleichnamige Straßen in verschiedenen
    #    Orten verschmelzen ("Hauptstraße 1" gibt es tausendfach). In der
    #    Gesamtzeile über alle Regionen hinweg wäre das falsch.
    standorte = {(z.plz, z.adresse or z.objekt or z.datei) for z in zeilen}
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

    # Belastbare Mediane und Einzelwerte werden getrennt ausgewiesen, aber
    # BEIDE gezeigt. Bekannte Mieten sind rar; eine Region wegen n=1 ganz
    # wegzulassen würde die wertvollste Information verschweigen.
    belastbar: list[RegionStats] = []
    einzelwerte: list[RegionStats] = []
    for key, gruppe in sorted(nach_leitregion.items()):
        ebene = "leitregion" if len(gruppe) >= config.MIN_N_LEITREGION else "leitregion_einzel"
        stat = _stats(ebene, key, gruppe[0].region_label or key, gruppe)
        (belastbar if ebene == "leitregion" else einzelwerte).append(stat)

    logger.info(
        "%d Leitregion(en) mit belastbarem Median (n>=%d), %d als Einzelwerte",
        len(belastbar), config.MIN_N_LEITREGION, len(einzelwerte),
    )
    ergebnis.extend(sorted(belastbar, key=lambda s: (-s.n, s.key)))
    ergebnis.extend(sorted(einzelwerte, key=lambda s: (-s.n, s.key)))

    ergebnis.extend(
        _stats("zone", key, gruppe[0].zone_label or key, gruppe)
        for key, gruppe in sorted(nach_zone.items())
    )

    ergebnis.append(_stats("gesamt", "*", "Alle Regionen", verwertbar))
    return ergebnis


def leitregionen(stats: list[RegionStats]) -> list[RegionStats]:
    """Leitregionen mit belastbarem Median (n >= MIN_N_LEITREGION)."""
    return [s for s in stats if s.ebene == "leitregion"]


def einzelwerte(stats: list[RegionStats]) -> list[RegionStats]:
    """Leitregionen mit n < MIN_N_LEITREGION – als Einzelwerte, nicht als Median."""
    return [s for s in stats if s.ebene == "leitregion_einzel"]


def zonen(stats: list[RegionStats]) -> list[RegionStats]:
    return [s for s in stats if s.ebene == "zone"]


def gesamt(stats: list[RegionStats]) -> RegionStats | None:
    for s in stats:
        if s.ebene == "gesamt":
            return s
    return None
