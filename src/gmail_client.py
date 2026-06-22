from __future__ import annotations

import base64
import logging
import os
import re
from email.utils import parseaddr

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .models import EmailData

logger = logging.getLogger(__name__)

SKIP_DOMAINS = {"kromeichpartner.de"}
SKIP_PREFIXES = {
    "noreply",
    "no-reply",
    "mailer-daemon",
    "notifications",
    "notification",
    "postmaster",
    "bounce",
    "auto-confirm",
    "donotreply",
    "do-not-reply",
    "support",
    "system",
    "info",
    "service",
    "team",
    "veranstaltung",
    "newsletter",
    "marketing",
    "hello",
    "kontakt",
    "contact",
    "office",
    "admin",
    "billing",
    "invoices",
    "feedback",
    "booking",
    "reservierung",
    "buchung",
    "orders",
    "sales",
    "accounts",
    "myscout",
    "notify",
    "notice",
    "rueckgabe",
    "belegerinnerungen",
    "hallo",
    "event",
    "coaching",
}
SKIP_SUBJECT_PATTERNS = [
    re.compile(r"newsletter", re.IGNORECASE),
    re.compile(r"abmelden|unsubscribe", re.IGNORECASE),
    re.compile(r"automatische.*(antwort|benachrichtigung)", re.IGNORECASE),
    re.compile(r"out of office|abwesenheit", re.IGNORECASE),
    re.compile(r"delivery.*failed|undeliverable", re.IGNORECASE),
]


def _build_credentials(refresh_token: str, client_id: str, client_secret: str) -> Credentials:
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    creds.refresh(Request())
    return creds


def _get_gmail_service(refresh_token: str, client_id: str, client_secret: str):
    creds = _build_credentials(refresh_token, client_id, client_secret)
    return build("gmail", "v1", credentials=creds)


def _is_skip_sender(email_address: str) -> tuple[bool, str]:
    _, addr = parseaddr(email_address)
    addr = addr.lower().strip()
    if not addr:
        return True, "invalid_email"

    local, domain = addr.rsplit("@", 1) if "@" in addr else (addr, "")

    if domain in SKIP_DOMAINS:
        return True, "internal"

    if any(local.startswith(prefix) for prefix in SKIP_PREFIXES):
        return True, "auto"

    return False, ""


def _is_skip_subject(subject: str) -> bool:
    return any(p.search(subject) for p in SKIP_SUBJECT_PATTERNS)


def _decode_body(payload: dict) -> str:
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    parts = payload.get("parts", [])
    for part in parts:
        mime = part.get("mimeType", "")
        if mime == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")

    for part in parts:
        mime = part.get("mimeType", "")
        if mime == "text/html" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")

    for part in parts:
        if part.get("parts"):
            result = _decode_body(part)
            if result:
                return result

    return ""


def _fetch_emails_for_account(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    account_label: str,
    hours: int = 24,
    limit: int = 50,
) -> list[EmailData]:
    service = _get_gmail_service(refresh_token, client_id, client_secret)
    # Gmail-Suche unterstützt nur ganze Tage (d), keine Stunden
    days = max(1, hours // 24)
    query = f"newer_than:{days}d"

    results = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=limit)
        .execute()
    )

    messages = results.get("messages", [])
    if not messages:
        logger.info("[%s] No emails found in the last %d hours", account_label, hours)
        return []

    logger.info("[%s] Found %d emails in the last %d hours", account_label, len(messages), hours)
    emails: list[EmailData] = []

    for msg_ref in messages:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_ref["id"], format="full")
            .execute()
        )

        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        sender = headers.get("from", "")
        subject = headers.get("subject", "")
        date_str = headers.get("date", "")

        _, sender_email = parseaddr(sender)

        skip, reason = _is_skip_sender(sender)
        if skip:
            logger.info("[%s] Skipping email from %s (reason: %s)", account_label, sender_email, reason)
            continue

        if _is_skip_subject(subject):
            logger.info("[%s] Skipping email with subject '%s' (auto/newsletter)", account_label, subject)
            continue

        body = _decode_body(msg.get("payload", {}))

        emails.append(
            EmailData(
                message_id=msg_ref["id"],
                sender=sender,
                sender_email=sender_email.lower(),
                subject=subject,
                body=body,
                date=date_str,
            )
        )

    logger.info("[%s] Returning %d emails after filtering", account_label, len(emails))
    return emails


def search_recent_emails(hours: int = 24, limit: int = 50) -> list[EmailData]:
    all_emails: list[EmailData] = []
    account_count = 0

    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    accounts = [
        ("GOOGLE_REFRESH_TOKEN", "Florian Brimmers"),
        ("GOOGLE_REFRESH_TOKEN_2", "Denise Kromeich"),
        ("GOOGLE_REFRESH_TOKEN_3", "Marek Zimmermann"),
        ("GOOGLE_REFRESH_TOKEN_4", "Lena Klinnert"),
        ("GOOGLE_REFRESH_TOKEN_5", "Oguzhan Sahin"),
    ]

    for env_key, label in accounts:
        token = os.environ.get(env_key)
        if token:
            account_count += 1
            try:
                all_emails.extend(_fetch_emails_for_account(token, client_id, client_secret, label, hours, limit))
            except Exception as e:
                logger.error("[%s] Fehler beim Abrufen: %s – überspringe Account", label, e)

    logger.info("Total: %d emails from %d account(s)", len(all_emails), account_count)
    return all_emails
