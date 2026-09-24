from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from .models import (
    AktionsTyp,
    Classification,
    Decision,
    MatchResult,
    MatchStatus,
    MessageType,
    Tier,
)

BERLIN = ZoneInfo("Europe/Berlin")


def due_date_plus_business_days(n: int = 2, now: datetime | None = None) -> str:
    """Fälligkeit +n Werktage (Sa/So übersprungen, Feiertage bewusst nicht), 10:00 Berlin."""
    current = (now or datetime.now(BERLIN)).astimezone(BERLIN)
    remaining = n
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    due = current.replace(hour=10, minute=0, second=0, microsecond=0)
    return due.isoformat()


def decide(cls: Classification | None, match: MatchResult | None) -> Decision:
    """Stufe-A/B-Entscheidung. DRY_RUN=true zwingt alles auf Stufe B (Woche-1-Regel)."""
    if cls is None:
        return Decision(tier=Tier.B, grund="Nachricht nicht klassifizierbar")

    if cls.typ == MessageType.IGNORIEREN:
        return Decision(tier=Tier.NONE, grund="Kein Objektbezug (ignorieren)")

    if cls.typ == MessageType.FEHLT_IN_PS:
        return Decision(
            tier=Tier.B,
            grund="Objekt fehlt in Propstack – Anlage nur manuell",
            geplante_aktionen=[
                f"Review-Aufgabe an {config.BROKER_REVIEW_FALLBACK_NAME} "
                f"({config.BROKER_REVIEW_FALLBACK}): Objekt anlegen"
            ],
        )

    if cls.typ == MessageType.FLAECHENUPDATE:
        return Decision(
            tier=Tier.B,
            grund="Flächenupdate – nur sammeln, kein Auto-Write",
            geplante_aktionen=["Review-Aufgabe: Flächenupdate abgleichen"],
        )

    # status_anweisung
    if cls.aktion != AktionsTyp.VERMIETET:
        return Decision(
            tier=Tier.B,
            grund=f"Aktion '{cls.aktion.value if cls.aktion else 'unbekannt'}' nicht automatisierbar",
            geplante_aktionen=["Review-Aufgabe mit Original-Anweisung"],
        )

    if match is None or match.status != MatchStatus.UNIQUE:
        grund = match.grund if match else "Kein Objekt-Matching möglich"
        return Decision(
            tier=Tier.B,
            grund=f"Kein eindeutiger Objekt-Match: {grund}",
            geplante_aktionen=["Review-Aufgabe mit Kandidatenliste"],
        )

    if cls.confidence < config.CONFIDENCE_THRESHOLD:
        return Decision(
            tier=Tier.B,
            grund=f"Confidence {cls.confidence:.2f} unter Schwelle {config.CONFIDENCE_THRESHOLD}",
            geplante_aktionen=["Review-Aufgabe mit vorbereiteter Aktion"],
        )

    aktionen = [f"Unit {u.id} ({u.adresse()}) auf rented=true setzen" for u in match.units]
    aktionen.append("Doku-Notiz anlegen")
    aktionen.append("Offene Deals absagen (Grund 256998)")

    if config.dry_run():
        return Decision(
            tier=Tier.B,
            grund="DRY_RUN aktiv – Woche-1-Regel: alles als Stufe B",
            geplante_aktionen=aktionen,
        )

    return Decision(tier=Tier.A, grund="Eindeutig + reversibel", geplante_aktionen=aktionen)
