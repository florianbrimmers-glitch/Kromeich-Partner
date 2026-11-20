from __future__ import annotations

import base64
import logging
import math
import os
import re
from email.utils import parseaddr

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from . import problems
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


def _list_message_ids(service, query: str, limit: int) -> tuple[list[str], bool]:
    """Alle Treffer der Suche, seitenweise (Gmail liefert höchstens 100 je Seite).
    Rückgabe: (IDs, abgeschnitten) – abgeschnitten, wenn es mehr als `limit` gibt."""
    ids: list[str] = []
    page_token = None
    while True:
        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=min(100, limit - len(ids)), pageToken=page_token)
            .execute()
        )
        ids.extend(m["id"] for m in results.get("messages", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            return ids, False
        if len(ids) >= limit:
            return ids, True


def _fetch_emails_for_account(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    account_label: str,
    hours: int = 48,
    limit: int = 300,
) -> list[EmailData]:
    service = _get_gmail_service(refresh_token, client_id, client_secret)
    # Gmail-Suche unterstützt nur ganze Tage (d), keine Stunden – aufrunden, nie abrunden.
    # Selbst gesendete Mails sind nie ein neuer Kontakt; sie zählten bisher aber in die
    # Obergrenze (19.11.2026: ein Postfach mit 50 von 50, der Rest fiel still weg).
    days = max(1, math.ceil(hours / 24))
    query = f"newer_than:{days}d -in:sent"

    # Die Obergrenze wächst mit dem Fenster (Nachhol-Lauf über 168 h): Gmail liefert die
    # neuesten zuerst – mit fester Grenze fielen genau die alten Mails weg, um die es geht.
    limit = max(limit, 150 * days)
    message_ids, abgeschnitten = _list_message_ids(service, query, limit)
    if not message_ids:
        logger.info("[%s] No emails found in the last %d hours", account_label, hours)
        return []
    if abgeschnitten:
        problems.melde("Postfach über der Obergrenze", f"{account_label}: mehr als {limit} Mails im Fenster, der Rest wurde nicht gelesen")

    logger.info("[%s] Found %d emails in the last %d hours", account_label, len(message_ids), hours)
    emails: list[EmailData] = []
    nicht_lesbar = 0

    for message_id in message_ids:
        # Eine einzelne nicht lesbare Mail darf nicht das ganze Postfach kosten
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
        except Exception as e:
            if getattr(getattr(e, "resp", None), "status", None) == 404:
                # Zwischen Liste und Abruf verschwunden (gelöscht, Entwurf gesendet) – kein Fehler
                logger.info("[%s] Mail %s gibt es nicht mehr – übersprungen", account_label, message_id)
                continue
            nicht_lesbar += 1
            logger.warning("[%s] Mail %s nicht lesbar: %s", account_label, message_id, e)
            continue

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
                message_id=message_id,
                sender=sender,
                sender_email=sender_email.lower(),
                subject=subject,
                body=body,
                date=date_str,
            )
        )

    if nicht_lesbar:
        problems.melde("Mails nicht lesbar", f"{account_label}: {nicht_lesbar} von {len(message_ids)}")
    logger.info("[%s] Returning %d emails after filtering", account_label, len(emails))
    return emails


def search_recent_emails(hours: int = 48, limit: int = 300) -> list[EmailData]:
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
                # z. B. abgelaufenes Refresh-Token: Das Postfach fehlt dann ganz – das
                # darf nicht nur eine Logzeile in einem grünen Lauf sein.
                problems.melde("Postfach nicht lesbar", f"{label}: {e}")

    if account_count == 0:
        problems.melde("Kein Postfach konfiguriert", "kein GOOGLE_REFRESH_TOKEN gesetzt")

    logger.info("Total: %d emails from %d account(s)", len(all_emails), account_count)
    return all_emails
