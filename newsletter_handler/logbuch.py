from __future__ import annotations

import logging

from . import config
from .models import DecisionRecord

logger = logging.getLogger(__name__)


def append_record(record: DecisionRecord) -> None:
    """Eine JSONL-Zeile pro Deal – läuft in jedem Modus (auch NO_WRITE)."""
    try:
        with open(config.decision_log_path(), "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")
    except OSError as e:
        logger.error("Entscheidungslog nicht schreibbar: %s", e)
