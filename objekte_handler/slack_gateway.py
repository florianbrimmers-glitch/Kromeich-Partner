from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from . import config

logger = logging.getLogger(__name__)

SLACK_API_URL = "https://slack.com/api"

_SKIP_SUBTYPES = ("channel_join", "channel_leave", "bot_message")


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.slack_bot_token()}"}


def get_bot_user_id() -> str:
    """auth.test – liefert die eigene Bot-User-ID (Pflicht für den ✅-Dedup)."""
    response = httpx.post(f"{SLACK_API_URL}/auth.test", headers=_headers(), timeout=30.0)
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack auth.test fehlgeschlagen: {data.get('error')}")
    return data["user_id"]


def fetch_channel_messages(hours: int, latest_hours: int = 0) -> list[dict]:
    """Liest Nachrichten (nur Thread-Parents) aus #objekte in einem Zeitfenster."""
    now = datetime.now(timezone.utc)
    oldest_ts = str((now - timedelta(hours=hours)).timestamp())
    latest_ts = str((now - timedelta(hours=latest_hours)).timestamp()) if latest_hours else None

    messages: list[dict] = []
    cursor = None

    while True:
        params: dict = {
            "channel": config.OBJEKTE_CHANNEL,
            "oldest": oldest_ts,
            "limit": 100,
        }
        if latest_ts:
            params["latest"] = latest_ts
        if cursor:
            params["cursor"] = cursor

        try:
            response = httpx.get(
                f"{SLACK_API_URL}/conversations.history",
                headers=_headers(),
                params=params,
                timeout=30.0,
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

    logger.info("%d Nachrichten aus #objekte gelesen (letzte %dh)", len(messages), hours)
    return messages


def fetch_thread_replies(thread_ts: str) -> list[dict]:
    """conversations.replies – Antworten eines Threads, ohne den Parent selbst."""
    replies: list[dict] = []
    cursor = None

    while True:
        params: dict = {
            "channel": config.OBJEKTE_CHANNEL,
            "ts": thread_ts,
            "limit": 100,
        }
        if cursor:
            params["cursor"] = cursor

        try:
            response = httpx.get(
                f"{SLACK_API_URL}/conversations.replies",
                headers=_headers(),
                params=params,
                timeout=30.0,
            )
            data = response.json()
            if not data.get("ok"):
                logger.error("Slack conversations.replies error: %s", data.get("error"))
                break

            for msg in data.get("messages", []):
                if msg.get("ts") == thread_ts:
                    continue  # Parent verwerfen
                if msg.get("subtype") in _SKIP_SUBTYPES:
                    continue
                replies.append(msg)

            if data.get("has_more") and data.get("response_metadata", {}).get("next_cursor"):
                cursor = data["response_metadata"]["next_cursor"]
                time.sleep(1)
            else:
                break
        except httpx.HTTPError as e:
            logger.error("Slack API error (replies): %s", e)
            break

    return replies


def has_bot_checkmark(msg: dict, bot_user_id: str) -> bool:
    """Prüft, ob die Nachricht bereits das eigene ✅ trägt (Verarbeitungsmarker).

    Menschliche ✅ zählen nicht. Slack kann die users-Liste einer Reaction kürzen –
    dann per reactions.get nachschlagen."""
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
            params={"channel": config.OBJEKTE_CHANNEL, "timestamp": ts, "full": "true"},
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
    """✅-Reaction als Verarbeitungsmarker setzen."""
    if config.no_write():
        logger.info("[NO_WRITE] Würde ✅ setzen an %s", ts)
        return True
    try:
        response = httpx.post(
            f"{SLACK_API_URL}/reactions.add",
            headers=_headers(),
            json={"channel": config.OBJEKTE_CHANNEL, "timestamp": ts, "name": config.CHECK_EMOJI},
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
    """Antwort immer als Thread-Reply, nie als neue Kanal-Nachricht."""
    if config.no_write():
        logger.info("[NO_WRITE] Würde Thread-Reply an %s posten: %s", thread_ts, text)
        return True
    try:
        response = httpx.post(
            f"{SLACK_API_URL}/chat.postMessage",
            headers=_headers(),
            json={"channel": config.OBJEKTE_CHANNEL, "thread_ts": thread_ts, "text": text},
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
            params={"channel": config.OBJEKTE_CHANNEL, "message_ts": ts},
            timeout=30.0,
        )
        data = response.json()
        if data.get("ok"):
            return data.get("permalink")
        logger.warning("chat.getPermalink fehlgeschlagen für %s: %s", ts, data.get("error"))
    except httpx.HTTPError as e:
        logger.error("chat.getPermalink error für %s: %s", ts, e)
    # Fallback-URL: ts "1751900000.123456" -> "p1751900000123456"
    return f"https://app.slack.com/archives/{config.OBJEKTE_CHANNEL}/p{ts.replace('.', '')}"
