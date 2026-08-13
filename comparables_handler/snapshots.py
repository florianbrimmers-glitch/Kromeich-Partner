from __future__ import annotations

import json
import logging
import os
from datetime import date

logger = logging.getLogger(__name__)

# Ein Snapshot je Lauf: {"stand": "2026-08", "werte": {"<key>": median, …}}
# Der Schlüssel ist "<Flächenart>|<Zeilenlabel>", z.B. "Halle/Lager|Ruhrgebiet".
#
# Propstack führt KEINE Miethistorie – ohne diese Ablage gäbe es keine
# Veränderungsspalte, nur eine erfundene. Die Zeitreihe entsteht dadurch, dass
# jeder Quartalslauf seinen Stand anhängt.


def schluessel(flaechenart: str, label: str) -> str:
    return f"{flaechenart}|{label}"


def aktueller_stand(heute: date | None = None) -> str:
    heute = heute or date.today()
    return f"{heute.year:04d}-{heute.month:02d}"


def laden(pfad: str) -> list[dict]:
    if not pfad or not os.path.exists(pfad):
        return []
    try:
        with open(pfad, encoding="utf-8") as f:
            daten = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Snapshot-Datei nicht lesbar (%s) – Lauf ohne Vergleich", e)
        return []
    if not isinstance(daten, list):
        logger.warning("Snapshot-Datei hat unerwartetes Format – ignoriert")
        return []
    snapshots = [s for s in daten if isinstance(s, dict) and s.get("stand")]
    snapshots.sort(key=lambda s: s["stand"])
    logger.info("Snapshots geladen: %d (%s)", len(snapshots),
                ", ".join(s["stand"] for s in snapshots[-6:]))
    return snapshots


def _monatsindex(stand: str) -> int | None:
    """'2026-08' -> 24320 (Monate seit Jahr 0) für Differenzrechnung."""
    try:
        jahr, monat = stand.split("-")
        return int(jahr) * 12 + int(monat)
    except (ValueError, AttributeError):
        return None


def vergleichs_snapshot(
    snapshots: list[dict], stand: str, monate: int, toleranz: int
) -> dict | None:
    """Den Snapshot, der `monate` zurückliegt (nächstgelegener in der Toleranz).

    Gibt es keinen passenden, wird KEIN Ersatz genommen – die Veränderungs-
    spalte bleibt dann leer, statt eine falsche Basis auszuweisen.
    """
    jetzt = _monatsindex(stand)
    if jetzt is None:
        return None

    ziel = jetzt - monate
    beste: tuple[int, dict] | None = None
    for snapshot in snapshots:
        index = _monatsindex(snapshot["stand"])
        if index is None or index >= jetzt:
            continue
        abstand = abs(index - ziel)
        if abstand > toleranz:
            continue
        if beste is None or abstand < beste[0]:
            beste = (abstand, snapshot)

    if beste is None:
        logger.info(
            "Kein Vergleichs-Snapshot ~%d Monate vor %s (±%d) – "
            "Veränderungsspalte bleibt leer", monate, stand, toleranz,
        )
        return None
    logger.info("Vergleichsbasis: Snapshot %s", beste[1]["stand"])
    return beste[1]


def anhaengen(snapshots: list[dict], stand: str, werte: dict[str, float]) -> list[dict]:
    """Aktuellen Stand ergänzen bzw. einen bestehenden gleichen Stand ersetzen.

    Zwei Läufe im selben Monat sollen keine zwei Datenpunkte erzeugen.
    """
    ohne_aktuell = [s for s in snapshots if s.get("stand") != stand]
    ohne_aktuell.append({"stand": stand, "werte": werte})
    ohne_aktuell.sort(key=lambda s: s["stand"])
    return ohne_aktuell


def schreiben(pfad: str, snapshots: list[dict]) -> bool:
    if not pfad:
        return False
    try:
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(snapshots, f, ensure_ascii=False, indent=1)
            f.write("\n")
        logger.info("Snapshots geschrieben: %s (%d Stände)", pfad, len(snapshots))
        return True
    except OSError as e:
        logger.error("Snapshot-Datei nicht schreibbar: %s", e)
        return False
