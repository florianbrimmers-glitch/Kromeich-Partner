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
from .slack_reader import fetch_recent_messages, get_message_images, get_message_text, has_images
from .contact_extractor import (
    extract_contact_from_image,
    extract_contact_from_text,
    categorize_contact,
)
from .apollo_client import enrich_contact, apply_enrichment
from .propstack_client import check_duplicate, create_contact, find_or_create_company, link_contact_to_company
from .slack_client import send_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("true", "1", "yes")

GROUP_LABEL_MAP: dict[str, str] = {v: k.value for k, v in GROUP_ID_MAP.items()}


def run_pipeline() -> PipelineReport:
    report = PipelineReport(run_date=date.today().isoformat())
    processed_emails: set[str] = set()
    company_cache: dict[str, int | None] = {}

    if DRY_RUN:
        logger.info("=== DRY RUN MODE – keine Kontakte werden angelegt ===")

    scan_hours = int(os.environ.get("SCAN_HOURS", "24"))
    logger.info("Step 1: Reading #visitenkarten channel (last %dh)...", scan_hours)
    messages = fetch_recent_messages(hours=scan_hours)
    report.emails_searched = len(messages)
    logger.info("Found %d messages in #visitenkarten", len(messages))

    for i, msg in enumerate(messages, 1):
        msg_text = get_message_text(msg)
        msg_preview = msg_text[:80] if msg_text else "(Bild)"
        logger.info("--- Processing message %d/%d: %s ---", i, len(messages), msg_preview)

        try:
            contacts: list = []

            if has_images(msg):
                images = get_message_images(msg)
                for img_data in images:
                    contact = extract_contact_from_image(img_data)
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
                processed_emails.add(dedup_key)

                name = f"{contact.first_name} {contact.last_name}".strip()

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

                # Propstack duplicate check
                if contact.email and check_duplicate(contact.email):
                    result = ContactResult(
                        email=contact.email,
                        name=name,
                        company=contact.company,
                        status=ContactStatus.SKIPPED_DUPLICATE,
                        group_ids=group_ids,
                        group_labels=group_labels,
                    )
                    report.contacts_skipped_duplicate.append(result)
                    logger.info("Übersprungen (existiert bereits): %s", contact.email)
                    continue

                # Create contact
                if DRY_RUN:
                    logger.info("[DRY RUN] Would create: %s (%s) groups=%s", name, contact.email, group_labels)
                else:
                    propstack_result = create_contact(contact, group_ids if group_ids else None)
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
                        if cache_key not in company_cache:
                            company_cache[cache_key] = find_or_create_company(contact)
                        company_id = company_cache[cache_key]
                        if company_id:
                            link_contact_to_company(person_id, company_id)
                        time.sleep(0.5)

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
                logger.info("Kontakt angelegt: %s – %s", name, group_labels)
                time.sleep(3)

        except Exception as e:
            logger.error("Error processing message %d: %s", i, e, exc_info=True)
            report.errors.append(ContactResult(
                email=msg_preview,
                status=ContactStatus.ERROR,
                error=str(e),
            ))

    if not DRY_RUN:
        logger.info("Sending Slack notification...")
        try:
            send_summary(report)
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
    logger.info("Neu angelegt: %d", len(report.contacts_created))
    for cr in report.contacts_created:
        fields_info = f" [Apollo: {', '.join(cr.enriched_fields)}]" if cr.apollo_enriched else ""
        logger.info("  + %s (%s) – %s%s", cr.name, cr.email or "keine Email", ", ".join(cr.group_labels) if cr.group_labels else "Kein Merkmal", fields_info)
    if report.errors:
        logger.info("Fehler: %d", len(report.errors))
        for err in report.errors:
            logger.info("  ! %s: %s", err.email, err.error)
    logger.info("=" * 60)


if __name__ == "__main__":
    run_pipeline()
