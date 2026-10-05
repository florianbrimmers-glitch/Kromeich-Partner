"""E-Mail-Benachrichtigungen des Eigentümer-Portals.

Ohne SMTP-Konfiguration wird nichts verschickt, sondern ins Log geschrieben –
derselbe Gedanke wie NO_WRITE beim Hallentinder: Wer testet, schickt keine Post
an echte Eigentümer.

Der Versand darf einen Vorgang nie scheitern lassen. Eine Einreichung, die an
einem SMTP-Timeout stirbt, wäre schlimmer als eine Einreichung ohne Mail.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from . import config
from .models import Einreichung, Nachweisart, Status

logger = logging.getLogger(__name__)

NACHWEIS_TEXT = {
    Nachweisart.GRUNDBUCHAUSZUG: "Grundbuchauszug",
    Nachweisart.ALLEINVERMARKTUNGSAUFTRAG: "Alleinvermarktungsauftrag",
}

GRUSS = "Mit freundlichen Grüßen\nKromeich & Partner"


def statuslink(einreichung: Einreichung) -> str:
    return f"{config.basis_url()}/status.html?t={einreichung.token}"


def _anrede(einreichung: Einreichung) -> str:
    name = einreichung.kontakt.name()
    return f"Guten Tag {name}," if name else "Guten Tag,"


def _versenden(an: list[str], betreff: str, text: str) -> bool:
    empfaenger = [a for a in an if a]
    if not empfaenger:
        return False

    if not config.mail_aktiv():
        logger.info(
            "[KEIN VERSAND] Mail an %s – '%s'\n%s",
            ", ".join(empfaenger), betreff, text,
        )
        return False

    nachricht = EmailMessage()
    nachricht["From"] = config.absender()
    nachricht["To"] = ", ".join(empfaenger)
    nachricht["Subject"] = betreff
    nachricht.set_content(text)

    try:
        if config.smtp_port() == 465:
            server = smtplib.SMTP_SSL(config.smtp_host(), config.smtp_port(), timeout=20)
        else:
            server = smtplib.SMTP(config.smtp_host(), config.smtp_port(), timeout=20)
        with server:
            if config.smtp_port() != 465:
                server.starttls()
            if config.smtp_benutzer():
                server.login(config.smtp_benutzer(), config.smtp_passwort())
            server.send_message(nachricht)
    except Exception as e:
        # Bewusst breit: der Vorgang ist wichtiger als die Benachrichtigung
        logger.error("Mail an %s fehlgeschlagen (%s): %s", ", ".join(empfaenger), betreff, e)
        return False

    logger.info("Mail verschickt an %s – '%s'", ", ".join(empfaenger), betreff)
    return True


def eingang_bestaetigen(einreichung: Einreichung) -> bool:
    """Wichtigste Mail überhaupt: sie enthält den Statuslink.

    Ohne sie ist der Link nur einmal auf dem Bildschirm zu sehen und danach
    für den Einsender verloren."""
    text = f"""{_anrede(einreichung)}

vielen Dank – Ihre Fläche {einreichung.objekt.adresse()} ist bei uns eingegangen.

Vorgangsnummer: {einreichung.nummer}

Unter diesem Link sehen Sie jederzeit den Stand und können Ihr Objekt ändern:
{statuslink(einreichung)}

Bitte bewahren Sie den Link auf – er ist Ihr Zugang zu diesem Vorgang.

Wir prüfen als Nächstes den {NACHWEIS_TEXT[einreichung.nachweis_art]}. Die Datei
löschen wir unmittelbar nach der Prüfung; gespeichert bleibt nur, wer sie wann
geprüft hat.

{GRUSS}"""
    return _versenden([einreichung.kontakt.email], f"Ihr Objekt ist eingegangen – {einreichung.nummer}", text)


def entscheidung_melden(einreichung: Einreichung) -> bool:
    if einreichung.status is Status.FREIGEGEBEN:
        betreff = f"Ihr Objekt ist online – {einreichung.nummer}"
        kern = f"""Ihr Objekt {einreichung.objekt.adresse()} ist geprüft und seit heute für
Suchende sichtbar.

Änderungen und das Zurückziehen des Objekts erledigen Sie selbst über diesen Link:
{statuslink(einreichung)}"""
    else:
        betreff = f"Ihr Objekt konnten wir nicht freigeben – {einreichung.nummer}"
        grund = einreichung.ablehnungsgrund or "Kein Grund hinterlegt."
        kern = f"""Ihr Objekt {einreichung.objekt.adresse()} konnten wir nicht freigeben.

Grund: {grund}

Sie können Ihre Angaben über diesen Link überarbeiten und erneut einreichen:
{statuslink(einreichung)}"""

    text = f"{_anrede(einreichung)}\n\n{kern}\n\n{GRUSS}"
    return _versenden([einreichung.kontakt.email], betreff, text)


def intern_melden(einreichung: Einreichung, anlass: str) -> bool:
    empfaenger = config.intern_empfaenger()
    if not empfaenger:
        return False
    text = f"""{anlass}

Vorgang:  {einreichung.nummer}
Objekt:   {einreichung.objekt.adresse()}
Fläche:   {einreichung.objekt.flaeche_qm:.0f} m²
Rolle:    {einreichung.rolle.value}
Nachweis: {NACHWEIS_TEXT[einreichung.nachweis_art]}

Prüfansicht: {config.basis_url()}/pruefung.html"""
    return _versenden(empfaenger, f"[Hallenbörse] {anlass} – {einreichung.nummer}", text)
