from __future__ import annotations

import logging
from statistics import median

from . import config, marktgebiete, snapshots
from .models import ComparableZeile, KennzahlenTabelle, KennzahlenZeile

logger = logging.getLogger(__name__)


def _median(werte: list[float]) -> float | None:
    return round(median(werte), 2) if werte else None


def _veraenderung(jetzt: float | None, vorher: float | None) -> float | None:
    """Relative Veränderung in Prozent. None, wenn keine Basis existiert."""
    if jetzt is None or vorher is None or vorher == 0:
        return None
    return round((jetzt - vorher) / vorher * 100, 1)


def _zeile(
    label: str, gruppe: str, zeilen: list[ComparableZeile], vergleich: dict | None,
    flaechenart: str, ist_summe: bool = False, ebene: str = "position",
) -> KennzahlenZeile:
    mieten = [z.kaltmiete_eur_qm for z in zeilen if z.kaltmiete_eur_qm is not None]
    nk = [z.nebenkosten_eur_qm for z in zeilen if z.nebenkosten_eur_qm is not None]
    jetzt = _median(mieten)

    vorher = None
    if vergleich:
        vorher = (vergleich.get("werte") or {}).get(snapshots.schluessel(flaechenart, label))

    return KennzahlenZeile(
        label=label,
        gruppe=gruppe,
        ebene=ebene,
        n=len(zeilen),
        n_standorte=len({(z.plz, z.adresse or z.objekt or z.datei) for z in zeilen}),
        median_jetzt=jetzt,
        median_vorher=vorher,
        veraenderung_prozent=_veraenderung(jetzt, vorher),
        min_kaltmiete=round(min(mieten), 2) if mieten else None,
        max_kaltmiete=round(max(mieten), 2) if mieten else None,
        median_nebenkosten=_median(nk),
        ist_summe=ist_summe,
    )


def baue_tabelle(
    zeilen: list[ComparableZeile],
    flaechenart: str,
    vergleich: dict | None = None,
) -> KennzahlenTabelle:
    """Kennzahlen-Tabelle einer Flächenart im Marktbericht-Layout.

    Aufbau wie in den Marktberichten: die bedeutenden Logistikmärkte einzeln,
    Zwischensumme, dann Ruhrgebiet und übrige Standorte, Zwischensumme,
    Gesamtsumme – plus abgeleitete Anteile.

    WICHTIG zur Lesart: n summiert sich über die Gruppen, der Median NICHT.
    Der Gruppen-Median wird über alle Datenpunkte der Gruppe neu berechnet,
    nicht aus den Zeilen-Medianen gemittelt.
    """
    relevant = [z for z in zeilen if z.verwertbar and z.nutzungsart == flaechenart]

    nach_label: dict[str, list[ComparableZeile]] = {}
    for zeile in relevant:
        nach_label.setdefault(marktgebiete.zeilen_label(zeile.region_key), []).append(zeile)

    tabelle = KennzahlenTabelle(flaechenart=flaechenart)

    # --- Gruppe 1: bedeutende Logistikmärkte (feste Reihenfolge) ----------
    top_zeilen: list[ComparableZeile] = []
    for name in marktgebiete.TOP_NAMEN:
        gruppe_zeilen = nach_label.get(name, [])
        if not gruppe_zeilen:
            continue          # Markt ohne Datenpunkt wird nicht als Leerzeile geführt
        top_zeilen.extend(gruppe_zeilen)
        tabelle.zeilen.append(
            _zeile(name, config.GRUPPE_TOP, gruppe_zeilen, vergleich, flaechenart)
        )
    if top_zeilen:
        tabelle.zeilen.append(_zeile(
            f"{config.GRUPPE_TOP} gesamt", config.GRUPPE_TOP, top_zeilen, vergleich,
            flaechenart, ist_summe=True, ebene="zwischensumme",
        ))

    # --- Gruppe 2: Ruhrgebiet + übrige Standorte --------------------------
    sonstige_zeilen: list[ComparableZeile] = []
    for name in (marktgebiete.RUHR_NAME, config.LABEL_UEBRIGE):
        gruppe_zeilen = nach_label.get(name, [])
        if not gruppe_zeilen:
            continue
        sonstige_zeilen.extend(gruppe_zeilen)
        tabelle.zeilen.append(
            _zeile(name, config.GRUPPE_SONSTIGE, gruppe_zeilen, vergleich, flaechenart)
        )
    if sonstige_zeilen:
        tabelle.zeilen.append(_zeile(
            f"{config.GRUPPE_SONSTIGE} gesamt", config.GRUPPE_SONSTIGE, sonstige_zeilen,
            vergleich, flaechenart, ist_summe=True, ebene="zwischensumme",
        ))

    # --- Gesamtsumme ------------------------------------------------------
    if relevant:
        tabelle.gesamt = _zeile(
            "Gesamt", "", relevant, vergleich, flaechenart,
            ist_summe=True, ebene="gesamtsumme",
        )

    # --- Abgeleitete Anteile (analog Eigennutzer-/Neubauanteil) -----------
    tabelle.anteile = _anteile(relevant, vergleich, flaechenart)
    return tabelle


ANTEIL_INTERN = "Anteil intern bekannter Konditionen"
ANTEIL_VERMIETET = "Anteil bereits vermieteter Flächen"
ANTEIL_MIT_NK = "Anteil mit Nebenkosten-Angabe"


def _anteil(teil: int, gesamt: int) -> float | None:
    return round(teil / gesamt * 100, 1) if gesamt else None


def _anteile(
    zeilen: list[ComparableZeile], vergleich: dict | None, flaechenart: str
) -> list[KennzahlenZeile]:
    """Prozentuale Kennzahlen unter der Tabelle.

    Veränderung wird hier in PROZENTPUNKTEN geführt, nicht relativ – wie in
    den Marktberichten ("-2,7 %-Pkte.").
    """
    gesamt = len(zeilen)
    if not gesamt:
        return []

    werte = {
        # "intern_*" heißt: die Kondition ist uns aus Mandat/Beratung bekannt,
        # nicht bloß ausgeschrieben – das Qualitätsmerkmal der Datenbasis.
        ANTEIL_INTERN: _anteil(
            sum(1 for z in zeilen if (z.miete_feld or "").startswith("custom_fields.intern_")),
            gesamt,
        ),
        ANTEIL_VERMIETET: _anteil(sum(1 for z in zeilen if z.vermietet is True), gesamt),
        ANTEIL_MIT_NK: _anteil(
            sum(1 for z in zeilen if z.nebenkosten_eur_qm is not None), gesamt),
    }

    ergebnis: list[KennzahlenZeile] = []
    for label, jetzt in werte.items():
        vorher = None
        if vergleich:
            vorher = (vergleich.get("werte") or {}).get(
                snapshots.schluessel(flaechenart, label))
        ergebnis.append(KennzahlenZeile(
            label=label, gruppe="", ebene="anteil", n=gesamt,
            median_jetzt=jetzt, median_vorher=vorher,
            # Prozentpunkte, nicht relative Veränderung
            veraenderung_prozent=(round(jetzt - vorher, 1)
                                  if jetzt is not None and vorher is not None else None),
            ist_prozentwert=True,
        ))
    return ergebnis


def snapshot_werte(tabellen: list[KennzahlenTabelle]) -> dict[str, float]:
    """Alle Werte des Laufs für die Snapshot-Ablage flach einsammeln."""
    werte: dict[str, float] = {}
    for tabelle in tabellen:
        for zeile in list(tabelle.zeilen) + list(tabelle.anteile):
            if zeile.median_jetzt is not None:
                werte[snapshots.schluessel(tabelle.flaechenart, zeile.label)] = zeile.median_jetzt
        if tabelle.gesamt and tabelle.gesamt.median_jetzt is not None:
            werte[snapshots.schluessel(tabelle.flaechenart, tabelle.gesamt.label)] = \
                tabelle.gesamt.median_jetzt
    return werte
