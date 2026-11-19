"""Sammelt, was in einem Lauf schiefging – damit kein Fehler nur im Log steht.

Anlass (Produktionslog vom 19.11.2026): Apollo wies jeden der 11 Aufrufe mit 401 ab,
zwei Antworten der KI ließen sich nicht lesen, ein Postfach stieß an die 50-Mail-Grenze –
der Lauf war grün und meldete „Fehler: 0“. Was hier gemeldet wird, steht am Ende in der
Zusammenfassung, in der Slack-Nachricht und macht den Lauf rot.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_probleme: dict[str, list[str]] = {}


def melde(art: str, detail: str = "") -> None:
    """Ein Problem festhalten. Gleiche `art` wird in der Zusammenfassung gezählt statt wiederholt."""
    logger.error("%s%s", art, f": {detail}" if detail else "")
    _probleme.setdefault(art, []).append(detail)


def zusammenfassung() -> list[str]:
    """Je Art eine Zeile: „Art (3×): erstes Detail“."""
    zeilen = []
    for art, details in _probleme.items():
        anzahl = f" ({len(details)}×)" if len(details) > 1 else ""
        erstes = next((d for d in details if d), "")
        zeilen.append(f"{art}{anzahl}{': ' + erstes if erstes else ''}")
    return zeilen


def leeren() -> None:
    _probleme.clear()
