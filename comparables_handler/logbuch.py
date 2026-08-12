from __future__ import annotations

import csv
import logging

from . import config
from .models import ComparableZeile, DecisionRecord

logger = logging.getLogger(__name__)

CSV_SPALTEN = (
    "quelle", "datum", "objekt", "adresse", "plz", "ort", "region_key", "region_label",
    "zone_key", "zone_label", "anbieter", "empfaenger", "eigenes_angebot",
    "nutzungsart", "flaeche_qm", "laufzeit_monate", "kaltmiete_eur_qm",
    "nebenkosten_eur_qm", "mietfreie_monate", "effektivmiete_eur_qm",
    "sicherheit", "indexierung", "option_hinweis", "vermietet", "miete_feld",
    "normalisiert_aus_absolut", "confidence", "ausschluss_grund",
    "datei", "quelle_link", "fundstellen", "file_id",
)


def append_record(record: DecisionRecord) -> None:
    """Eine JSONL-Zeile pro Dokument – läuft in jedem Modus (auch NO_WRITE)."""
    try:
        with open(config.decision_log_path(), "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")
    except OSError as e:
        logger.error("Entscheidungslog nicht schreibbar: %s", e)


def schreibe_dataset(zeilen: list[ComparableZeile]) -> str | None:
    """Flache Comparables-Tabelle als CSV (Actions-Artefakt, Excel-fähig).

    Enthält bewusst AUCH die ausgeschlossenen Zeilen mit Grund – so ist
    nachvollziehbar, warum ein Angebot nicht im Median steht.
    """
    pfad = config.dataset_path()
    try:
        with open(pfad, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(CSV_SPALTEN), delimiter=";")
            writer.writeheader()
            for zeile in zeilen:
                daten = zeile.model_dump()
                writer.writerow({spalte: daten.get(spalte) for spalte in CSV_SPALTEN})
        logger.info("Datensatz geschrieben: %s (%d Zeilen)", pfad, len(zeilen))
        return pfad
    except OSError as e:
        logger.error("Datensatz nicht schreibbar: %s", e)
        return None
