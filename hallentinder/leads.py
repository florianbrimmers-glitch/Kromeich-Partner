from __future__ import annotations

import logging
import re

from . import config, propstack
from .models import HallCard, LeadPayload, LeadResult, SearchProfile
from .session import Session

logger = logging.getLogger(__name__)

EMAIL_MUSTER = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")

NUTZUNG_TEXT = {
    "lager": "Lager",
    "produktion": "Produktion",
    "umschlag": "Umschlag",
    "egal": "keine Präferenz",
}
ZEIT_TEXT = {
    "sofort": "sofort",
    "3_monate": "in 3 Monaten",
    "6_monate": "in 6 Monaten",
    "flexibel": "flexibel",
}


class LeadFehler(Exception):
    """Eingabe des Interessenten ist nicht verwertbar – wird als 400 beantwortet."""


def profil_text(profil: SearchProfile) -> str:
    minimum, maximum = profil.spanne()
    if minimum and maximum and minimum != maximum:
        flaeche = f"{minimum:,.0f}–{maximum:,.0f} m²".replace(",", ".")
    elif minimum or maximum:
        flaeche = f"ca. {(minimum or maximum):,.0f} m²".replace(",", ".")
    else:
        flaeche = "Fläche offen"
    return (
        f"Suchprofil: {profil.ort}, {flaeche}, "
        f"Nutzung {NUTZUNG_TEXT.get(profil.nutzung.value, profil.nutzung.value)}, "
        f"Bedarf {ZEIT_TEXT.get(profil.zeithorizont.value, profil.zeithorizont.value)}"
    )


def _deal_notiz(profil: SearchProfile, karte: HallCard, nachricht: str) -> str:
    zeilen = [
        f"Über {config.QUELLE} angefragt: {karte.titel} ({karte.adresse()})",
        profil_text(profil),
    ]
    if nachricht.strip():
        zeilen.append(f"Nachricht: {nachricht.strip()}")
    return "\n".join(zeilen)


def pruefe(lead: LeadPayload) -> None:
    if lead.website.strip():
        # Honeypot gefüllt – wie ein normaler Erfolg behandeln, aber nichts schreiben
        raise LeadFehler("honeypot")
    if not lead.einwilligung:
        raise LeadFehler("Ohne Einwilligung in die Datenverarbeitung können wir dich nicht kontaktieren.")
    if not EMAIL_MUSTER.match(lead.email.strip()):
        raise LeadFehler("Bitte gib eine gültige E-Mail-Adresse an.")
    if not lead.nachname.strip():
        raise LeadFehler("Bitte gib deinen Namen an.")


def verarbeite(session: Session, lead: LeadPayload) -> LeadResult:
    """Kontakt sichern (Dublettencheck) und je gelikter Halle einen Deal anlegen.

    Dislikes werden nie nach Propstack geschrieben. Ein fehlgeschlagener Deal
    stoppt die übrigen nicht."""
    pruefe(lead)

    likes = session.gelikte_karten()
    if not likes:
        raise LeadFehler("Bitte markiere zuerst mindestens eine Halle als interessant.")

    ergebnis = LeadResult(no_write=config.no_write())

    kontakt_id = propstack.find_contact_by_email(lead.email)
    if kontakt_id:
        logger.info("Bestehender Kontakt %s für %s", kontakt_id, lead.email)
    else:
        kontakt_id = propstack.create_contact(lead)
        ergebnis.kontakt_neu = kontakt_id is not None or config.no_write()
    ergebnis.kontakt_id = kontakt_id

    if config.no_write():
        for karte in likes:
            propstack.create_deal(kontakt_id, karte.id, _deal_notiz(session.profil, karte, lead.nachricht))
        ergebnis.deals_geplant = len(likes)
        session.lead_gesendet = True
        return ergebnis

    if kontakt_id is None:
        raise LeadFehler("Kontakt konnte nicht angelegt werden.")

    for karte in likes:
        try:
            propstack.create_deal(kontakt_id, karte.id, _deal_notiz(session.profil, karte, lead.nachricht))
            ergebnis.deals_angelegt += 1
        except Exception as e:
            logger.error("Deal für Objekt %s fehlgeschlagen: %s", karte.id, e)
            ergebnis.deals_fehlgeschlagen += 1

    session.lead_gesendet = True
    logger.info(
        "Lead verarbeitet: Kontakt %s, %d Deals angelegt, %d fehlgeschlagen",
        kontakt_id, ergebnis.deals_angelegt, ergebnis.deals_fehlgeschlagen,
    )
    return ergebnis
