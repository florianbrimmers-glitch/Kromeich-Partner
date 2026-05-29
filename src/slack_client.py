from __future__ import annotations

import logging
import os

import httpx

from .models import ContactResult, GroupCategory, GROUP_ID_MAP, PipelineReport

logger = logging.getLogger(__name__)

SLACK_POST_URL = "https://slack.com/api/chat.postMessage"
CHANNEL_ID = "C07SJMXQWEA"

GROUP_LABEL_MAP: dict[str, str] = {v: k.value for k, v in GROUP_ID_MAP.items()}


def _format_contact_line(result: ContactResult) -> str:
    parts = [f"*{result.name}*"]

    details = []
    if result.company:
        details.append(result.company)
    if result.group_labels:
        details.append(", ".join(result.group_labels))

    if details:
        parts.append(" – ")
        parts.append(", ".join(details))

    source = "via Email-Signatur"
    if result.apollo_enriched:
        source += " + Apollo"
    parts.append(f" — _{source}_")

    return "• " + "".join(parts)


def send_summary(report: PipelineReport) -> None:
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        logger.warning("SLACK_BOT_TOKEN not set, skipping Slack notification")
        return

    if not report.contacts_created:
        logger.info("No new contacts created, skipping Slack notification")
        return

    lines = [f":card_index: *KI-Scan – Neue Kontakte vom {report.run_date}*", ""]
    lines.append(f"{len(report.contacts_created)} neue Kontakte in Propstack angelegt:")
    lines.append("")

    for result in report.contacts_created:
        lines.append(_format_contact_line(result))

    lines.append("")
    skipped = len(report.contacts_skipped_duplicate)
    if skipped > 0:
        lines.append(f"{skipped} Kontakte übersprungen (bereits in Propstack vorhanden).")

    message = "\n".join(lines)

    try:
        response = httpx.post(
            SLACK_POST_URL,
            json={"channel": CHANNEL_ID, "text": message},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            logger.error("Slack API error: %s", data.get("error", "unknown"))
        else:
            logger.info("Slack notification sent to #visitenkarten")
    except (httpx.HTTPError, ValueError) as e:
        logger.error("Slack notification failed: %s", e)
