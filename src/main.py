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
from .gmail_client import search_recent_emails
from .contact_extractor import extract_contact, categorize_contact
from .apollo_client import enrich_contact, apply_enrichment
from .propstack_client import check_duplicate, create_contact
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

    if DRY_RUN:
        logger.info("=== DRY RUN MODE – keine Kontakte werden angelegt ===")

    # Step 1: Search emails
    logger.info("Step 1: Searching Gmail for recent emails...")
    try:
        emails = search_recent_emails(hours=24, limit=50)
    except Exception as e:
        logger.error("Failed to search emails: %s", e)
        return report

    report.emails_searched = len(emails)
    logger.info("Found %d emails after initial filtering", len(emails))

    # Step 2-8: Process each email
    for i, email_data in enumerate(emails, 1):
        logger.info("--- Processing email %d/%d: %s ---", i, len(emails), email_data.sender_email)

        try:
            # Step 3: Extract contact from signature
            contact = extract_contact(email_data)
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

            # Step 6: Session deduplication
            if contact.email in processed_emails:
                logger.info("Session duplicate: %s", contact.email)
                report.contacts_skipped_session_duplicate += 1
                continue
            processed_emails.add(contact.email)

            name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or contact.email

            # Step 4: Apollo enrichment if fields are missing
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
                time.sleep(1.5)

            # Step 5: Categorize contact
            group_ids = categorize_contact(contact, email_data.subject, email_data.body[:2000])
            group_labels = [GROUP_LABEL_MAP.get(gid, str(gid)) for gid in group_ids]
            time.sleep(1.5)

            # Step 7: Propstack duplicate check
            if check_duplicate(contact.email):
                result = ContactResult(
                    email=contact.email,
                    name=name,
                    company=contact.company,
                    status=ContactStatus.SKIPPED_DUPLICATE,
                    group_ids=group_ids,
                    group_labels=group_labels,
                )
                report.contacts_skipped_duplicate.append(result)
                logger.info("Übersprungen (existiert bereits in Propstack): %s", contact.email)
                continue

            # Step 8: Create contact in Propstack
            if DRY_RUN:
                logger.info("[DRY RUN] Would create contact: %s (%s) groups=%s", name, contact.email, group_labels)
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
            logger.info("Kontakt angelegt: %s (%s) – Merkmale: %s", name, contact.email, group_labels)

            time.sleep(1.5)

        except Exception as e:
            logger.error("Error processing email from %s: %s", email_data.sender_email, e, exc_info=True)
            report.errors.append(
                ContactResult(
                    email=email_data.sender_email,
                    status=ContactStatus.ERROR,
                    error=str(e),
                )
            )

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
    logger.info("Neu angelegt: %d", len(report.contacts_created))

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
    run_pipeline()
