from __future__ import annotations

import logging

from . import config
from .propstack import fetch_open_review_units

logger = logging.getLogger(__name__)


class OffeneReviews:
    """Dublettenschutz für Review-Aufgaben: je Einheit höchstens eine offene Aufgabe.

    Der Radar meldet dieselbe Vermietung oft an mehreren Tagen, mit wechselnder
    Überschrift („Garbe“, „Garbe Industrial“). Der ✅-Marker verhindert nur, dass
    dieselbe Nachricht zweimal verarbeitet wird – nicht, dass dieselbe Einheit an
    jedem dieser Tage eine neue Aufgabe bekommt. Stand 19.11.2026: 58 von 156
    offenen Aufgaben wiederholten nur eine ältere offene Aufgabe zur selben Einheit.

    Der Bestand wird beim ersten Bedarf einmal je Lauf geladen und um die im Lauf
    neu angelegten Aufgaben ergänzt. Verglichen wird nur mit Aufgaben der letzten
    config.REVIEW_DEDUP_TAGE Tage. Scheitert das Laden, wird wie bisher angelegt (eine
    doppelte Aufgabe ist weniger schädlich als eine verlorene Meldung) – der Lauf
    meldet es aber als Fehler, statt still wieder Dubletten zu erzeugen.
    """

    def __init__(self) -> None:
        self._by_unit: dict[int, int | None] | None = None
        self.laden_fehlgeschlagen = False
        self.fehler = ""

    def _bestand(self) -> dict[int, int | None]:
        if self._by_unit is None:
            try:
                self._by_unit = dict(
                    fetch_open_review_units(
                        config.BROKER_REVIEW, config.REVIEW_TITEL_PRAEFIX, config.REVIEW_DEDUP_TAGE
                    )
                )
            except Exception as e:  # bewusst breit: der Schutz darf den Lauf nie stoppen
                logger.error(
                    "Offene Review-Aufgaben nicht lesbar (%s) – Dublettenschutz für diesen Lauf aus", e
                )
                self.laden_fehlgeschlagen = True
                self.fehler = str(e)
                self._by_unit = {}
        return self._by_unit

    def vorhanden(self, unit_ids: list[int]) -> tuple[bool, int | None]:
        """(True, Task-ID), wenn zu JEDER der Einheiten schon eine offene Aufgabe liegt.

        Ohne Einheit (kein Objekt zugeordnet) gibt es nichts zu vergleichen -> (False, None).
        Die Task-ID kann None sein (im Lauf unter NO_WRITE „angelegt“)."""
        if not unit_ids:
            return False, None
        bestand = self._bestand()
        if all(unit_id in bestand for unit_id in unit_ids):
            return True, bestand[unit_ids[0]]
        return False, None

    def merke(self, unit_ids: list[int], task_id: int | None) -> None:
        """Im Lauf neu angelegte Aufgabe eintragen – zwei Meldungen zur selben Einheit
        im selben Lauf ergeben sonst wieder zwei Aufgaben."""
        bestand = self._bestand()
        for unit_id in unit_ids:
            bestand.setdefault(unit_id, task_id)
