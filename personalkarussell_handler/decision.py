from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from .matcher import alte_firma_plausibel, alte_links, ist_bereits_aktuell
from .models import (
    Classification,
    CompanyMatch,
    Decision,
    Link,
    MatchStatus,
    MessageType,
    PersonMatch,
    Tier,
    Wechsel,
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
    return current.replace(hour=10, minute=0, second=0, microsecond=0).isoformat()


def decide_message(cls: Classification | None) -> Decision | None:
    """Entscheidung auf Nachrichtenebene. None = pro Wechsel entscheiden (decide_wechsel)."""
    if cls is None:
        return Decision(tier=Tier.B, grund="Nachricht nicht klassifizierbar")
    if cls.typ == MessageType.IGNORIEREN:
        return Decision(tier=Tier.NONE, grund="Kein Personalwechsel (ignorieren)")
    if cls.typ == MessageType.LINKEDIN:
        return Decision(tier=Tier.B, grund="Nur LinkedIn-Link – Inhalt bitte manuell prüfen")
    if cls.typ == MessageType.UMFIRMIERUNG:
        return Decision(
            tier=Tier.B,
            grund="Umfirmierung betrifft alle Kontakte der Firma – nur manuell",
        )
    if cls.typ in (MessageType.WECHSEL, MessageType.ABGANG) and not cls.wechsel:
        return Decision(tier=Tier.B, grund=f"{cls.typ.value.capitalize()} erkannt, aber keine Person extrahiert")
    return None


def decide_wechsel(
    cls: Classification,
    wechsel: Wechsel,
    person: PersonMatch | None,
    firma: CompanyMatch | None,
    links: list[Link],
) -> Decision:
    """Stufe A nur bei eindeutiger Person, eindeutiger Zielfirma und stimmigem Altbestand."""
    name = wechsel.name()

    if cls.typ == MessageType.ABGANG or not wechsel.neue_firma:
        return Decision(
            tier=Tier.B,
            grund=f"{name}: Abgang ohne bekanntes Ziel – neue Firma recherchieren",
            geplante_aktionen=["Review-Aufgabe: neuen Arbeitgeber ermitteln"],
        )

    if person is None or person.status == MatchStatus.NONE:
        return Decision(
            tier=Tier.B,
            grund=f"{name}: nicht in Propstack gefunden (neu anlegen oder Schreibweise prüfen)",
            geplante_aktionen=[f"Review-Aufgabe: {name} bei {wechsel.neue_firma} anlegen/zuordnen"],
        )
    if person.status == MatchStatus.AMBIGUOUS:
        return Decision(
            tier=Tier.B,
            grund=f"{name}: {person.grund}",
            geplante_aktionen=["Review-Aufgabe: Dubletten zusammenführen, dann Wechsel nachziehen"],
        )

    p = person.person
    if firma is None or firma.status == MatchStatus.NONE:
        return Decision(
            tier=Tier.B,
            grund=f"{name}: Firma '{wechsel.neue_firma}' nicht in Propstack – bitte anlegen und verknüpfen",
            geplante_aktionen=[f"Review-Aufgabe: Firma {wechsel.neue_firma} anlegen, {p.name()} verknüpfen"],
        )
    if firma.status == MatchStatus.AMBIGUOUS:
        return Decision(
            tier=Tier.B,
            grund=f"{name}: {firma.grund}",
            geplante_aktionen=["Review-Aufgabe mit Firmen-Kandidaten"],
        )

    ziel = firma.company
    if ist_bereits_aktuell(p, links, ziel):
        return Decision(tier=Tier.A, grund=f"{name}: steht bereits bei {ziel.name}", bereits_aktuell=True)

    if not alte_firma_plausibel(p, links, wechsel.alte_firma):
        return Decision(
            tier=Tier.B,
            grund=(
                f"{name}: Propstack führt '{p.company or 'keine Firma'}', gemeldet war "
                f"'{wechsel.alte_firma}' – bitte prüfen"
            ),
            geplante_aktionen=[f"Review-Aufgabe: {p.name()} zu {ziel.name} umhängen"],
        )

    if cls.confidence < config.CONFIDENCE_THRESHOLD:
        return Decision(
            tier=Tier.B,
            grund=f"{name}: Confidence {cls.confidence:.2f} unter Schwelle {config.CONFIDENCE_THRESHOLD}",
            geplante_aktionen=["Review-Aufgabe mit vorbereiteter Aktion"],
        )

    aktionen = [f"Firma von {p.name()} auf {ziel.name} setzen und verknüpfen"]
    for link in alte_links(links, p, wechsel.alte_firma, ziel.id):
        aktionen.append(f"Verknüpfung zu {link.company_name} entfernen")
    aktionen.append("Notiz am Kontakt anlegen")

    if config.dry_run():
        return Decision(tier=Tier.B, grund=f"{name}: DRY_RUN aktiv – alles als Stufe B", geplante_aktionen=aktionen)

    return Decision(tier=Tier.A, grund=f"{name}: eindeutig", geplante_aktionen=aktionen)
