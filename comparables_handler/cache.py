from __future__ import annotations

import json
import logging
import os

from . import config
from .models import Mietangebot

logger = logging.getLogger(__name__)


def _key(file_id: str, modified_time: str | None) -> str:
    """Cache-Schlüssel: Datei-ID + Änderungszeit.

    Wird ein Angebot im Drive überschrieben, ändert sich modifiedTime und das
    Dokument wird neu extrahiert.
    """
    return f"{file_id}@{modified_time or ''}"


def laden() -> dict[str, Mietangebot]:
    """Extraktions-Cache lesen. Fehlende/kaputte Zeilen werden ignoriert."""
    pfad = config.cache_path()
    if not pfad or not os.path.exists(pfad):
        return {}

    cache: dict[str, Mietangebot] = {}
    try:
        with open(pfad, encoding="utf-8") as f:
            for zeile in f:
                zeile = zeile.strip()
                if not zeile:
                    continue
                try:
                    eintrag = json.loads(zeile)
                    cache[eintrag["key"]] = Mietangebot.model_validate(eintrag["angebot"])
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.warning("Cache-Zeile übersprungen: %s", e)
    except OSError as e:
        logger.warning("Cache nicht lesbar (%s) – Lauf ohne Cache", e)
        return {}

    logger.info("Extraktions-Cache: %d Einträge aus %s", len(cache), pfad)
    return cache


def hole(cache: dict[str, Mietangebot], file_id: str, modified_time: str | None) -> Mietangebot | None:
    return cache.get(_key(file_id, modified_time))


def schreiben(cache: dict[str, Mietangebot]) -> None:
    """Cache komplett neu schreiben.

    Der Aufrufer übergibt nur die im Lauf berührten Einträge – so fallen
    verwaiste Schlüssel (gelöschte oder im Drive überschriebene Dateien) weg
    und die Datei wächst nicht unbegrenzt.
    """
    pfad = config.cache_path()
    if not pfad:
        return
    try:
        with open(pfad, "w", encoding="utf-8") as f:
            for key, angebot in cache.items():
                f.write(json.dumps(
                    {"key": key, "angebot": angebot.model_dump()},
                    ensure_ascii=False,
                ) + "\n")
        logger.info("Extraktions-Cache geschrieben: %d Einträge", len(cache))
    except OSError as e:
        logger.error("Cache nicht schreibbar: %s", e)


def merken(
    cache: dict[str, Mietangebot], file_id: str, modified_time: str | None, angebot: Mietangebot
) -> None:
    cache[_key(file_id, modified_time)] = angebot
