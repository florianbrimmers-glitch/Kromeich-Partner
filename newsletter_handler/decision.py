from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from .models import Deal, Decision, MatchResult, MatchStatus, Tier

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


def decide(deal: Deal | None, match: MatchResult | None) -> Decision:
    """Stufe-A/B-Entscheidung für einen Deal. DRY_RUN=true zwingt alles auf Stufe B."""
    if deal is None:
        return Decision(tier=Tier.B, grund="Deal nicht extrahierbar")

    # Phase 1: nur Vermietungen sind überhaupt relevant.
    if not deal.ist_vermietung:
        return Decision(tier=Tier.NONE, grund=f"Keine Vermietung (deal_typ={deal.deal_typ.value})")

    # Fremd-Deal ohne eigenen Bestand: nur loggen, keine Aktion, kein Review-Task.
    if match is None or match.status == MatchStatus.NONE:
        grund = match.grund if match else "Kein Objekt-Matching möglich"
        return Decision(tier=Tier.NONE, grund=f"Vermietung ohne eigenen Bestands-Match: {grund}")

    if match.status != MatchStatus.UNIQUE:
        return Decision(
            tier=Tier.B,
            grund=f"Kein eindeutiger Objekt-Match: {match.grund}",
            geplante_aktionen=["Review-Aufgabe mit Kandidatenliste"],
        )

    if deal.confidence < config.CONFIDENCE_THRESHOLD:
        return Decision(
            tier=Tier.B,
            grund=f"Confidence {deal.confidence:.2f} unter Schwelle {config.CONFIDENCE_THRESHOLD}",
            geplante_aktionen=["Review-Aufgabe mit vorbereiteter Aktion"],
        )

    aktionen = [f"Unit {u.id} ({u.adresse()}) auf rented=true setzen" for u in match.units]
    aktionen.append("Doku-Notiz anlegen")
    aktionen.append(f"Offene Deals absagen (Grund {config.RESERVATION_REASON_ABSAGE})")

    if config.dry_run():
        return Decision(
            tier=Tier.B,
            grund="DRY_RUN aktiv – Vermietung nur als Review-Aufgabe",
            geplante_aktionen=aktionen,
        )

    return Decision(tier=Tier.A, grund="Vermietung eindeutig einem eigenen Objekt zugeordnet", geplante_aktionen=aktionen)
