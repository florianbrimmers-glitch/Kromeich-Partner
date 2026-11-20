from __future__ import annotations

import logging
import os
import sys
import time
from datetime import date

from .models import (
    ContactResult,
    ContactStatus,
    GroupCategory,
    GROUP_ID_MAP,
    PipelineReport,
)
from .slack_reader import (
    fetch_recent_messages,
    get_bot_user_id,
    get_message_images,
    get_message_text,
    has_images,
    ist_verarbeitet,
    markiere_verarbeitet,
)
from .contact_extractor import (
    extract_contact_from_image,
    extract_contact_from_text,
    categorize_contact,
)
from .apollo_client import enrich_contact, apply_enrichment, starte_lauf as apollo_starte_lauf
from .propstack_client import (
    check_duplicate,
    check_duplicate_by_name,
    create_contact,
    find_or_create_company,
    link_contact_to_company,
)
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


def run_pipeline() -> PipelineReport:
    problems.leeren()
    report = PipelineReport(run_date=date.today().isoformat())
    processed_emails: set[str] = set()
    company_cache: dict[str, int] = {}

    if DRY_RUN:
        logger.info("=== DRY RUN MODE – keine Kontakte werden angelegt ===")
    apollo_starte_lauf()

    # 48 h bei täglichem Lauf: Jede Karte wird zweimal gesehen, ein verspäteter oder
    # ausgefallener Lauf reißt keine Lücke. Die Dublettenprüfung macht das folgenlos.
    scan_hours = int(os.environ.get("SCAN_HOURS") or "48")
    scan_latest_hours = int(os.environ.get("SCAN_LATEST_HOURS") or "0")
    if scan_latest_hours:
        logger.info("Step 1: Reading #visitenkarten (Fenster: %dh bis %dh zurück)...", scan_hours, scan_latest_hours)
    else:
        logger.info("Step 1: Reading #visitenkarten channel (last %dh)...", scan_hours)
    messages = fetch_recent_messages(hours=scan_hours, latest_hours=scan_latest_hours)
    report.emails_searched = len(messages)
    logger.info("Found %d messages in #visitenkarten", len(messages))
    bot_user_id = get_bot_user_id()

    for i, msg in enumerate(messages, 1):
        msg_text = get_message_text(msg)
        msg_preview = msg_text[:80] if msg_text else "(Bild)"
        logger.info("--- Processing message %d/%d: %s ---", i, len(messages), msg_preview)

        if ist_verarbeitet(msg, bot_user_id):
            logger.info("Bereits verarbeitet (eigenes ✅) – übersprungen")
            continue
        fehler_vorher = len(report.errors) + problems.anzahl()
        erkannt = 0

        try:
            contacts: list = []

            if has_images(msg):
                for image_data, media_type in get_message_images(msg):
                    # Ein Bild, das scheitert, darf die übrigen Bilder der Nachricht nicht kosten
                    try:
                        contact = extract_contact_from_image(image_data, media_type)
                    except Exception as e:
                        problems.melde("Visitenkarte nicht auswertbar", f"{type(e).__name__}: {str(e)[:100]}")
                        contact = None
                    time.sleep(3)
                    if contact:
                        contacts.append(contact)

            if msg_text and not contacts:
                contact = extract_contact_from_text(msg_text)
                time.sleep(3)
                if contact:
                    contacts.append(contact)

            if not contacts:
                logger.info("No contact data extracted from message %d", i)
                report.contacts_skipped_no_email += 1
                continue

            erkannt = len(contacts)
            for contact in contacts:
                if not contact.first_name or not contact.last_name:
                    logger.info("Skipping – missing name: %s %s", contact.first_name, contact.last_name)
                    report.contacts_skipped_no_email += 1
                    continue

                dedup_key = contact.email or f"{contact.first_name}_{contact.last_name}".lower()
                if dedup_key in processed_emails:
                    logger.info("Session duplicate: %s", dedup_key)
                    report.contacts_skipped_session_duplicate += 1
                    continue

                name = f"{contact.first_name} {contact.last_name}".strip()

                # Propstack duplicate check (ohne Email: über Vor-/Nachname) – VOR Apollo
                # und Kategorisierung: Für einen längst bekannten Kontakt lohnt beides nicht.
                if contact.email:
                    is_duplicate = check_duplicate(contact.email)
                else:
                    is_duplicate = check_duplicate_by_name(contact.first_name, contact.last_name)
                if is_duplicate is None:
                    # Prüfung fehlgeschlagen – nicht anlegen, sonst drohen Dubletten
                    report.errors.append(ContactResult(
                        email=contact.email or name,
                        name=name,
                        status=ContactStatus.ERROR,
                        error="Propstack-Duplikat-Prüfung fehlgeschlagen – Kontakt übersprungen",
                    ))
                    logger.warning("Duplikat-Prüfung fehlgeschlagen, überspringe %s", name)
                    continue
                if is_duplicate:
                    processed_emails.add(dedup_key)
                    result = ContactResult(
                        email=contact.email,
                        name=name,
                        company=contact.company,
                        status=ContactStatus.SKIPPED_DUPLICATE,
                    )
                    report.contacts_skipped_duplicate.append(result)
                    logger.info("Übersprungen (existiert bereits): %s", contact.email or name)
                    continue

                # Apollo enrichment
                apollo_enriched = False
                enriched_fields: list[str] = []
                if contact.has_missing_fields():
                    logger.info("Missing fields for %s, trying Apollo...", name)
                    enrichment = enrich_contact(contact)
                    if enrichment and enrichment.enriched_fields:
                        contact = apply_enrichment(contact, enrichment)
                        apollo_enriched = True
                        enriched_fields = enrichment.enriched_fields
                    time.sleep(3)

                # Categorize
                group_ids = categorize_contact(contact, "Visitenkarte aus Slack", msg_text[:2000])
                group_labels = [GROUP_LABEL_MAP.get(gid, str(gid)) for gid in group_ids]
                time.sleep(3)

                # Create contact
                if DRY_RUN:
                    logger.info("[DRY RUN] Would create: %s (%s) groups=%s", name, contact.email, group_labels)
                else:
                    propstack_result = create_contact(contact, group_ids if group_ids else None, quelle="Visitenkarte")
                    if not propstack_result:
                        report.errors.append(ContactResult(
                            email=contact.email or name,
                            name=name,
                            status=ContactStatus.ERROR,
                            error="Propstack create failed",
                        ))
                        continue

                    person_id = propstack_result.get("id")
                    if person_id and contact.company:
                        cache_key = contact.company.strip().lower()
                        company_id = company_cache.get(cache_key)
                        if company_id is None:
                            # Scheitert die Firma, steht es unter den Problemen des Laufs.
                            company_id = find_or_create_company(contact)
                            if company_id:
                                company_cache[cache_key] = company_id
                        if company_id:
                            link_contact_to_company(person_id, company_id)
                        time.sleep(0.5)

                # Erst nach Anlage als verarbeitet merken: Scheitert sie, darf dieselbe
                # Karte aus einer zweiten Nachricht es noch einmal versuchen.
                processed_emails.add(dedup_key)

                result = ContactResult(
                    email=contact.email or "",
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
                    logger.info("[DRY RUN] Nicht angelegt: %s – %s", name, group_labels)
                else:
                    logger.info("Kontakt angelegt: %s – %s", name, group_labels)
                time.sleep(3)

        except Exception as e:
            logger.error("Error processing message %d: %s", i, e, exc_info=True)
            report.errors.append(ContactResult(
                email=msg_preview,
                status=ContactStatus.ERROR,
                error=f"{type(e).__name__}: {str(e)[:200]}",
            ))

        # ✅ nur, wenn eine Karte erkannt wurde und nichts schiefging: Eine Nachricht mit
        # Fehler sieht der nächste Lauf wieder; Geplauder ohne Karte bekommt keinen Haken.
        ohne_fehler = len(report.errors) + problems.anzahl() == fehler_vorher
        if erkannt and ohne_fehler and not DRY_RUN and msg.get("ts"):
            markiere_verarbeitet(msg["ts"])

    # Was unterwegs schiefging (Slack, Apollo, Bilder, Firmen …), gehört in den Report
    for zeile in problems.zusammenfassung():
        report.errors.append(ContactResult(email="Lauf", status=ContactStatus.ERROR, error=zeile))

    if not DRY_RUN:
        logger.info("Sending Slack notification...")
        try:
            send_summary(report, quelle="Visitenkarte")
        except Exception as e:
            logger.error("Slack notification failed: %s", e)

    _print_summary(report)
    return report


def _print_summary(report: PipelineReport) -> None:
    logger.info("=" * 60)
    logger.info("ZUSAMMENFASSUNG – Visitenkarten-Scan vom %s", report.run_date)
    logger.info("=" * 60)
    logger.info("Nachrichten verarbeitet: %d", report.emails_searched)
    logger.info("Übersprungen (kein Kontakt): %d", report.contacts_skipped_no_email)
    logger.info("Übersprungen (Duplikat): %d", len(report.contacts_skipped_duplicate))
    logger.info("%s: %d", "Würde anlegen (DRY RUN)" if DRY_RUN else "Neu angelegt", len(report.contacts_created))
    for cr in report.contacts_created:
        fields_info = f" [Apollo: {', '.join(cr.enriched_fields)}]" if cr.apollo_enriched else ""
        logger.info("  + %s (%s) – %s%s", cr.name, cr.email or "keine Email", ", ".join(cr.group_labels) if cr.group_labels else "Kein Merkmal", fields_info)
    if report.errors:
        logger.info("Fehler: %d", len(report.errors))
        for err in report.errors:
            logger.info("  ! %s: %s", err.email, err.error)
    logger.info("=" * 60)


if __name__ == "__main__":
    # Rot, wenn etwas schiefging: Ein grüner Lauf mit Fehlern fällt niemandem auf.
    sys.exit(1 if run_pipeline().errors else 0)
