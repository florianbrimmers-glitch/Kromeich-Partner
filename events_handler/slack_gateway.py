from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from . import config

logger = logging.getLogger(__name__)

SLACK_API_URL = "https://slack.com/api"

# Bewusst OHNE "bot_message": im #events-Kanal posten auch Slackbot/Integrationen
# die Einladungen, die wir verarbeiten wollen.
_SKIP_SUBTYPES = ("channel_join", "channel_leave")

# Datei-Typen, aus denen wir Text ziehen (weitergeleitete Mails sind meist text/html)
_TEXT_MIMETYPES = ("text/html", "text/plain")
MAX_FILE_BYTES = 5_000_000


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.slack_bot_token()}"}


def get_bot_user_id() -> str:
    """auth.test – eigene Bot-User-ID (für den ✅-Dedup und Eigen-Nachricht-Filter)."""
    response = httpx.post(f"{SLACK_API_URL}/auth.test", headers=_headers(), timeout=30.0)
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack auth.test fehlgeschlagen: {data.get('error')}")
    return data["user_id"]


def fetch_channel_messages(hours: int, latest_hours: int = 0) -> list[dict]:
    """Liest Nachrichten aus #events in einem Zeitfenster (nur Kanal-Parents)."""
    now = datetime.now(timezone.utc)
    oldest_ts = str((now - timedelta(hours=hours)).timestamp())
    latest_ts = str((now - timedelta(hours=latest_hours)).timestamp()) if latest_hours else None

    messages: list[dict] = []
    cursor = None

    while True:
        params: dict = {"channel": config.EVENTS_CHANNEL, "oldest": oldest_ts, "limit": 100}
        if latest_ts:
            params["latest"] = latest_ts
        if cursor:
            params["cursor"] = cursor

        try:
            response = httpx.get(
                f"{SLACK_API_URL}/conversations.history",
                headers=_headers(), params=params, timeout=30.0,
            )
            data = response.json()
            if not data.get("ok"):
                logger.error("Slack conversations.history error: %s", data.get("error"))
                break

            for msg in data.get("messages", []):
                if msg.get("subtype") in _SKIP_SUBTYPES:
                    continue
                messages.append(msg)

            if data.get("has_more") and data.get("response_metadata", {}).get("next_cursor"):
                cursor = data["response_metadata"]["next_cursor"]
                time.sleep(1)
            else:
                break
        except httpx.HTTPError as e:
            logger.error("Slack API error: %s", e)
            break

    logger.info("%d Nachrichten aus #events gelesen (letzte %dh)", len(messages), hours)
    return messages


def fetch_file_text(file: dict) -> str | None:
    """Lädt eine text/html- bzw. text/plain-Slack-Datei und gibt den Rohtext zurück.

    Muster analog src/slack_reader.get_message_images (Download mit Bearer-Token)."""
    mimetype = file.get("mimetype", "")
    if not any(mimetype.startswith(t) for t in _TEXT_MIMETYPES):
        return None
    url = file.get("url_private_download") or file.get("url_private")
    if not url:
        return None
    try:
        response = httpx.get(url, headers=_headers(), timeout=60.0, follow_redirects=True)
        if response.status_code != 200:
            logger.warning("Datei-Download fehlgeschlagen %s: HTTP %s", file.get("name"), response.status_code)
            return None
        content = response.content[:MAX_FILE_BYTES]
        logger.info("Datei geladen: %s (%d bytes)", file.get("name", "?"), len(content))
        return content.decode("utf-8", errors="replace")
    except httpx.HTTPError as e:
        logger.error("Datei-Download error %s: %s", file.get("name"), e)
        return None


def has_bot_checkmark(msg: dict, bot_user_id: str) -> bool:
    """Prüft, ob die Nachricht bereits das eigene ✅ trägt (Verarbeitungsmarker)."""
    for reaction in msg.get("reactions", []):
        if reaction.get("name") != config.CHECK_EMOJI:
            continue
        users = reaction.get("users", [])
        if bot_user_id in users:
            return True
        if reaction.get("count", 0) > len(users):
            return _checkmark_via_reactions_get(msg.get("ts", ""), bot_user_id)
    return False


def _checkmark_via_reactions_get(ts: str, bot_user_id: str) -> bool:
    try:
        response = httpx.get(
            f"{SLACK_API_URL}/reactions.get",
            headers=_headers(),
            params={"channel": config.EVENTS_CHANNEL, "timestamp": ts, "full": "true"},
            timeout=30.0,
        )
        data = response.json()
        if not data.get("ok"):
            logger.warning("reactions.get fehlgeschlagen für %s: %s", ts, data.get("error"))
            return False
        for reaction in data.get("message", {}).get("reactions", []):
            if reaction.get("name") == config.CHECK_EMOJI and bot_user_id in reaction.get("users", []):
                return True
        return False
    except httpx.HTTPError as e:
        logger.error("reactions.get error für %s: %s", ts, e)
        return False


def add_checkmark(ts: str) -> bool:
    """Setzt den Verarbeitungsmarker ✅.

    Bewusst AUCH im DRY_RUN unterdrückt: sonst gilt die Nachricht als erledigt,
    obwohl noch keine Asana-Aufgabe existiert – sie würde im scharfen Betrieb
    übersprungen und das Event nie in der Liste landen."""
    if config.no_write() or config.dry_run():
        logger.info("[%s] Würde ✅ setzen an %s",
                    "NO_WRITE" if config.no_write() else "DRY_RUN", ts)
        return True
    try:
        response = httpx.post(
            f"{SLACK_API_URL}/reactions.add",
            headers=_headers(),
            json={"channel": config.EVENTS_CHANNEL, "timestamp": ts, "name": config.CHECK_EMOJI},
            timeout=30.0,
        )
        data = response.json()
        if data.get("ok") or data.get("error") == "already_reacted":
            return True
        logger.error("reactions.add fehlgeschlagen für %s: %s", ts, data.get("error"))
        return False
    except httpx.HTTPError as e:
        logger.error("reactions.add error für %s: %s", ts, e)
        return False


def post_thread_reply(thread_ts: str, text: str) -> bool:
    """Antwortet im Thread des Posts.

    Im DRY_RUN unterdrückt – ohne ✅ würde derselbe Post sonst in jedem
    nächtlichen Lauf erneut kommentiert werden."""
    if config.no_write() or config.dry_run():
        logger.info("[%s] Würde Thread-Reply an %s posten: %s",
                    "NO_WRITE" if config.no_write() else "DRY_RUN", thread_ts, text)
        return True
    try:
        response = httpx.post(
            f"{SLACK_API_URL}/chat.postMessage",
            headers=_headers(),
            json={"channel": config.EVENTS_CHANNEL, "thread_ts": thread_ts, "text": text},
            timeout=30.0,
        )
        data = response.json()
        if not data.get("ok"):
            logger.error("chat.postMessage fehlgeschlagen für %s: %s", thread_ts, data.get("error"))
            return False
        return True
    except httpx.HTTPError as e:
        logger.error("chat.postMessage error für %s: %s", thread_ts, e)
        return False


def get_permalink(ts: str) -> str | None:
    try:
        response = httpx.get(
            f"{SLACK_API_URL}/chat.getPermalink",
            headers=_headers(),
            params={"channel": config.EVENTS_CHANNEL, "message_ts": ts},
            timeout=30.0,
        )
        data = response.json()
        if data.get("ok"):
            return data.get("permalink")
        logger.warning("chat.getPermalink fehlgeschlagen für %s: %s", ts, data.get("error"))
    except httpx.HTTPError as e:
        logger.error("chat.getPermalink error für %s: %s", ts, e)
    return f"https://app.slack.com/archives/{config.EVENTS_CHANNEL}/p{ts.replace('.', '')}"
