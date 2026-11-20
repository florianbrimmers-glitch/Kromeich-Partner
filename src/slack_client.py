from __future__ import annotations

import logging
import os

import httpx

from .models import ContactResult, GroupCategory, GROUP_ID_MAP, PipelineReport

logger = logging.getLogger(__name__)

SLACK_POST_URL = "https://slack.com/api/chat.postMessage"
CHANNEL_ID = "C07SJMXQWEA"

GROUP_LABEL_MAP: dict[str, str] = {v: k.value for k, v in GROUP_ID_MAP.items()}


MAX_FEHLERZEILEN = 8


def _format_contact_line(result: ContactResult, quelle: str = "Email-Signatur") -> str:
    parts = [f"*{result.name}*"]

    details = []
    if result.company:
        details.append(result.company)
    if result.group_labels:
        details.append(", ".join(result.group_labels))

    if details:
        parts.append(" – ")
        parts.append(", ".join(details))

    source = f"via {quelle}"
    if result.apollo_enriched:
        source += " + Apollo"
    parts.append(f" — _{source}_")

    return "• " + "".join(parts)


def send_summary(report: PipelineReport, quelle: str = "Email-Signatur") -> None:
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        logger.warning("SLACK_BOT_TOKEN not set, skipping Slack notification")
        return

    if not report.contacts_created and not report.errors:
        logger.info("No new contacts created, skipping Slack notification")
        return

    # Die Kopfzeile bleibt in beiden Fällen gleich: An „KI-Scan“ + „Neue Kontakte“
    # erkennt der Visitenkarten-Import die eigene Zusammenfassung wieder.
    lines = [f":card_index: *KI-Scan – Neue Kontakte vom {report.run_date}*", ""]
    if report.contacts_created:
        lines.append(f"{len(report.contacts_created)} neue Kontakte in Propstack angelegt:")
        lines.append("")
        for result in report.contacts_created:
            lines.append(_format_contact_line(result, quelle))
        lines.append("")
    else:
        lines.append("Keine neuen Kontakte angelegt.")
        lines.append("")

    skipped = len(report.contacts_skipped_duplicate)
    if skipped > 0:
        lines.append(f"{skipped} Kontakte übersprungen (bereits in Propstack vorhanden).")

    if report.errors:
        # Fehler gehören dorthin, wo jemand hinsieht – nicht nur ins Actions-Log.
        lines.append("")
        lines.append(f":warning: *{len(report.errors)} Problem(e) in diesem Lauf* (Details im Actions-Log):")
        for fehler in report.errors[:MAX_FEHLERZEILEN]:
            wer = "" if fehler.email == "Lauf" else f"{fehler.name or fehler.email}: "
            lines.append(f"• {wer}{fehler.error}")
        if len(report.errors) > MAX_FEHLERZEILEN:
            lines.append(f"• … und {len(report.errors) - MAX_FEHLERZEILEN} weitere")

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
