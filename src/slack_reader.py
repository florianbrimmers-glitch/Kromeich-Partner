from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

SLACK_API_URL = "https://slack.com/api"
VISITENKARTEN_CHANNEL = "C07SJMXQWEA"


def _bot_token() -> str:
    return os.environ["SLACK_BOT_TOKEN"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_bot_token()}"}


def fetch_recent_messages(hours: int = 24) -> list[dict]:
    """Liest Nachrichten der letzten `hours` Stunden aus #visitenkarten."""
    oldest = datetime.now(timezone.utc) - timedelta(hours=hours)
    oldest_ts = str(oldest.timestamp())

    messages: list[dict] = []
    cursor = None

    while True:
        params: dict = {
            "channel": VISITENKARTEN_CHANNEL,
            "oldest": oldest_ts,
            "limit": 100,
        }
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
                if msg.get("subtype") in ("channel_join", "channel_leave", "bot_message"):
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

    # Skip messages from our own bot (KI-Scan summaries)
    filtered = [m for m in messages if not _is_bot_summary(m)]
    logger.info("Fetched %d messages from #visitenkarten (last %dh)", len(filtered), hours)
    return filtered


def _is_bot_summary(msg: dict) -> bool:
    text = msg.get("text", "")
    return "KI-Scan" in text and "Neue Kontakte" in text


def get_message_images(msg: dict) -> list[bytes]:
    """Lädt Bilder aus einer Slack-Nachricht herunter."""
    images: list[bytes] = []
    files = msg.get("files", [])

    for f in files:
        mimetype = f.get("mimetype", "")
        if not mimetype.startswith("image/"):
            continue

        url = f.get("url_private_download") or f.get("url_private")
        if not url:
            continue

        try:
            response = httpx.get(
                url,
                headers=_headers(),
                timeout=60.0,
                follow_redirects=True,
            )
            if response.status_code == 200:
                images.append(response.content)
                logger.info("Image downloaded: %s (%d bytes)", f.get("name", "unknown"), len(response.content))
            else:
                logger.warning("Failed to download image %s: HTTP %s", f.get("name"), response.status_code)
        except httpx.HTTPError as e:
            logger.error("Image download failed: %s", e)

    return images


def has_images(msg: dict) -> bool:
    files = msg.get("files", [])
    return any(f.get("mimetype", "").startswith("image/") for f in files)


def get_message_text(msg: dict) -> str:
    return msg.get("text", "").strip()
