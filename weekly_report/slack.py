from __future__ import annotations

import logging
import time

import httpx

from . import config

logger = logging.getLogger(__name__)

SLACK_API_URL = "https://slack.com/api"

MAX_ATTEMPTS = 3


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.slack_bot_token()}"}


def send_dm(user_id: str, text: str) -> bool:
    """Direktnachricht an einen User.

    chat.postMessage akzeptiert eine User-ID als channel und öffnet die DM selbst;
    der Bot hat die dafür nötigen Scopes chat:write und im:write.
    unfurl_links=False, damit die Propstack-Deep-Links die Nachricht nicht zerreißen."""
    payload = {
        "channel": user_id,
        "text": text,
        "unfurl_links": False,
        "unfurl_media": False,
    }
    last_error: str | None = None

    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            time.sleep(2**attempt)
        try:
            response = httpx.post(
                f"{SLACK_API_URL}/chat.postMessage",
                headers=_headers(),
                json=payload,
                timeout=30.0,
            )
            data = response.json()
            if data.get("ok"):
                logger.info("Wochenreport an %s gesendet (ts=%s)", user_id, data.get("ts"))
                return True
            last_error = str(data.get("error"))
            # Konfigurationsfehler wiederholen sich beim Retry identisch.
            if last_error not in ("ratelimited", "service_unavailable", "internal_error"):
                logger.error("chat.postMessage an %s fehlgeschlagen: %s", user_id, last_error)
                return False
            logger.warning(
                "chat.postMessage an %s: %s (Versuch %d/%d)", user_id, last_error, attempt + 1, MAX_ATTEMPTS
            )
        except httpx.HTTPError as e:
            last_error = str(e)
            logger.warning("chat.postMessage an %s: %s (Versuch %d/%d)", user_id, e, attempt + 1, MAX_ATTEMPTS)

    logger.error("chat.postMessage an %s endgültig fehlgeschlagen: %s", user_id, last_error)
    return False
