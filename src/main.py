from __future__ import annotations

import logging
import os
import sys
import time
from datetime import date
from email.utils import parseaddr

from .models import (
    ContactResult,
    ContactStatus,
    GroupCategory,
    GROUP_ID_MAP,
    PipelineReport,
)
from .gmail_client import search_recent_emails
from .contact_extractor import extract_contact, categorize_contact
from .apollo_client import enrich_contact, apply_enrichment, starte_lauf as apollo_starte_lauf
from .propstack_client import check_duplicate, create_contact, find_or_create_company, link_contact_to_company
from .slack_client import send_summary
from . import problems

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("true", "1", "yes")

GROUP_LABEL_MAP: dict[str, str] = {v: k.value for k, v in GROUP_ID_MAP.items()}


def scan_hours() -> int:
    """Wie weit zurück gelesen wird. 48 h bei täglichem Lauf: Jeder Tag wird zweimal
    gesehen, ein verspäteter oder ausgefallener Lauf reißt keine Lücke. Die
    Dublettenprüfung macht das Wiedersehen folgenlos."""
    return int(os.environ.get("SCAN_HOURS") or "48")


# Adressen, hinter denen wechselnde Personen schreiben
SAMMELADRESSEN = (
    "info", "kontakt", "contact", "office", "mail", "post", "hallo", "hello", "team", "service",
    "vertrieb", "sales", "vermietung", "leasing", "anfrage", "anfragen", "empfang", "sekretariat",
    "buero", "büro", "verwaltung", "zentrale", "welcome", "germany", "deutschland",
)


def _ist_sammeladresse(adresse: str) -> bool:
    return adresse.split("@", 1)[0].strip().lower() in SAMMELADRESSEN


def _absender_name(email_data) -> str:
    name, _ = parseaddr(email_data.sender or "")
    return name.strip() or email_data.sender_email


def run_pipeline() -> PipelineReport:
    problems.leeren()
    report = PipelineReport(run_date=date.today().isoformat())
    processed_emails: set[str] = set()
    bekannt: dict[str, bool | None] = {}  # Propstack-Prüfung je Adresse, einmal je Lauf
    company_cache: dict[str, int] = {}

    def in_propstack(adresse: str) -> bool | None:
        if adresse not in bekannt:
            ergebnis = check_duplicate(adresse)
            if ergebnis is None:
                return None  # nicht merken: die nächste Mail desselben Absenders prüft neu
            bekannt[adresse] = ergebnis
        return bekannt[adresse]

    def pruefe(adresse: str, name: str) -> bool:
        """True = neu, weiter verarbeiten. Sonst ist der Fall im Report vermerkt."""
        if adresse in processed_emails:
            logger.info("Session duplicate: %s", adresse)
            report.contacts_skipped_session_duplicate += 1
            return False
        vorhanden = in_propstack(adresse)
        if vorhanden is None:
            # Prüfung fehlgeschlagen – nicht anlegen, sonst drohen Dubletten
            report.errors.append(
                ContactResult(
                    email=adresse,
                    name=name,
                    status=ContactStatus.ERROR,
                    error="Propstack-Duplikat-Prüfung fehlgeschlagen – Kontakt übersprungen",
                )
            )
            logger.warning("Duplikat-Prüfung fehlgeschlagen, überspringe %s", adresse)
            return False
        if vorhanden:
            processed_emails.add(adresse)
            report.contacts_skipped_duplicate.append(
                ContactResult(email=adresse, name=name, status=ContactStatus.SKIPPED_DUPLICATE)
            )
            logger.info("Übersprungen (existiert bereits in Propstack): %s", adresse)
            return False
        return True

    if DRY_RUN:
        logger.info("=== DRY RUN MODE – keine Kontakte werden angelegt ===")
    apollo_starte_lauf()

    # Step 1: Search emails
    logger.info("Step 1: Searching Gmail for recent emails (last %dh)...", scan_hours())
    try:
        emails = search_recent_emails(hours=scan_hours())
    except Exception as e:
        problems.melde("Gmail-Suche fehlgeschlagen", str(e)[:120])
        emails = []

    report.emails_searched = len(emails)
    logger.info("Found %d emails after initial filtering", len(emails))

    # Step 2-8: Process each email
    for i, email_data in enumerate(emails, 1):
        logger.info("--- Processing email %d/%d: %s ---", i, len(emails), email_data.sender_email)

        try:
            # Step 2: Ist der Absender schon in Propstack? Dann ohne einen KI-Aufruf weiter.
            # Am 19.11.2026 waren 18 von 19 erkannten Kontakten längst vorhanden – jeder
            # lief vorher durch Extraktion, Apollo und Kategorisierung mit Websuche.
            # Ausnahme Sammeladressen (info@, vertrieb@ …): Dahinter schreiben wechselnde
            # Personen mit eigener Adresse in der Signatur – die wären sonst unsichtbar.
            sammeladresse = _ist_sammeladresse(email_data.sender_email)
            if not sammeladresse and not pruefe(email_data.sender_email, _absender_name(email_data)):
                continue

            # Step 3: Extract contact from signature
            contact = extract_contact(email_data)
            time.sleep(3)
            if not contact:
                logger.info("No contact data extracted from %s", email_data.sender_email)
                report.contacts_skipped_no_email += 1
                continue

            if not contact.first_name or not contact.last_name:
                logger.info(
                    "Skipping %s – missing first_name or last_name (got: %s %s)",
                    contact.email,
                    contact.first_name or "None",
                    contact.last_name or "None",
                )
                report.contacts_skipped_no_email += 1
                continue

            name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or contact.email

            # Step 4: Die Signatur nennt eine andere Adresse als der Absender (oder der
            # Absender ist eine Sammeladresse und wurde oben nicht geprüft) – jetzt prüfen
            if (sammeladresse or contact.email != email_data.sender_email) and not pruefe(contact.email, name):
                continue

            # Step 5: Apollo enrichment if fields are missing
            apollo_enriched = False
            enriched_fields: list[str] = []
            if contact.has_missing_fields():
                logger.info("Missing fields for %s, trying Apollo enrichment...", contact.email)
                enrichment = enrich_contact(contact)
                if enrichment and enrichment.enriched_fields:
                    contact = apply_enrichment(contact, enrichment)
                    apollo_enriched = True
                    enriched_fields = enrichment.enriched_fields
                    logger.info("Apollo enriched %s: %s", contact.email, enriched_fields)
                time.sleep(3)

            # Step 6: Categorize contact
            group_ids = categorize_contact(contact, email_data.subject, email_data.body[:2000])
            group_labels = [GROUP_LABEL_MAP.get(gid, str(gid)) for gid in group_ids]
            time.sleep(3)

            # Step 7: Person anlegen und mit dem Firmen-Datensatz verknüpfen
            if DRY_RUN:
                company_info = f" | Firma: {contact.company}" if contact.company else ""
                logger.info(
                    "[DRY RUN] Would create contact: %s (%s) groups=%s%s",
                    name, contact.email, group_labels, company_info,
                )
            else:
                propstack_result = create_contact(contact, group_ids if group_ids else None)
                if not propstack_result:
                    result = ContactResult(
                        email=contact.email,
                        name=name,
                        status=ContactStatus.ERROR,
                        error="Propstack create failed",
                    )
                    report.errors.append(result)
                    continue

                person_id = propstack_result.get("id")
                if person_id and contact.company:
                    cache_key = contact.company.strip().lower()
                    company_id = company_cache.get(cache_key)
                    if company_id is None:
                        # Scheitert die Firma, steht es unter den Problemen des Laufs.
                        # None wird nicht gemerkt: der nächste Kontakt versucht es neu.
                        company_id = find_or_create_company(contact)
                        if company_id:
                            company_cache[cache_key] = company_id
                    if company_id:
                        link_contact_to_company(person_id, company_id)
                    time.sleep(0.5)

            # Erst jetzt gilt die Adresse als verarbeitet: Scheitert die Anlage, darf
            # eine zweite Mail desselben Absenders es noch einmal versuchen.
            processed_emails.update({contact.email, email_data.sender_email})
            bekannt[contact.email] = bekannt[email_data.sender_email] = True

            result = ContactResult(
                email=contact.email,
                name=name,
                company=contact.company,
                status=ContactStatus.CREATED,
                group_ids=group_ids,
                group_labels=group_labels,
                apollo_enriched=apollo_enriched,
                enriched_fields=enriched_fields,
            )
            report.contacts_created.append(result)
            if DRY_RUN:
                logger.info("[DRY RUN] Nicht angelegt: %s (%s) – Merkmale: %s", name, contact.email, group_labels)
            else:
                logger.info("Kontakt angelegt: %s (%s) – Merkmale: %s", name, contact.email, group_labels)

            time.sleep(3)

        except Exception as e:
            logger.error("Error processing email from %s: %s", email_data.sender_email, e, exc_info=True)
            report.errors.append(
                ContactResult(
                    email=email_data.sender_email,
                    status=ContactStatus.ERROR,
                    error=f"{type(e).__name__}: {str(e)[:200]}",
                )
            )

    # Was unterwegs schiefging (Apollo, Postfächer, Firmen …), gehört in den Report
    for zeile in problems.zusammenfassung():
        report.errors.append(ContactResult(email="Lauf", status=ContactStatus.ERROR, error=zeile))

    # Step 9: Slack notification
    if not DRY_RUN:
        logger.info("Step 9: Sending Slack notification...")
        try:
            send_summary(report)
        except Exception as e:
            logger.error("Failed to send Slack notification: %s", e)

    # Step 10: Summary
    _print_summary(report)

    return report


def _print_summary(report: PipelineReport) -> None:
    logger.info("=" * 60)
    logger.info("ZUSAMMENFASSUNG – KI-Scan vom %s", report.run_date)
    logger.info("=" * 60)
    logger.info("Durchsuchte Emails: %d", report.emails_searched)
    logger.info("Übersprungen (Session-Duplikate): %d", report.contacts_skipped_session_duplicate)
    logger.info("Übersprungen (kein Kontakt extrahiert): %d", report.contacts_skipped_no_email)
    logger.info(
        "Übersprungen (bereits in Propstack): %d",
        len(report.contacts_skipped_duplicate),
    )
    logger.info("%s: %d", "Würde anlegen (DRY RUN)" if DRY_RUN else "Neu angelegt", len(report.contacts_created))

    for cr in report.contacts_created:
        fields_info = ""
        if cr.apollo_enriched:
            fields_info = f" [Apollo: {', '.join(cr.enriched_fields)}]"
        logger.info(
            "  + %s (%s) – %s%s",
            cr.name,
            cr.email,
            ", ".join(cr.group_labels) if cr.group_labels else "Kein Merkmal",
            fields_info,
        )

    if report.errors:
        logger.info("Fehler: %d", len(report.errors))
        for err in report.errors:
            logger.info("  ! %s: %s", err.email, err.error)

    logger.info("=" * 60)


if __name__ == "__main__":
    # Rot, wenn etwas schiefging: Ein grüner Lauf mit Fehlern fällt niemandem auf.
    sys.exit(1 if run_pipeline().errors else 0)
