from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone

import httpx

from . import problems

logger = logging.getLogger(__name__)

SLACK_API_URL = "https://slack.com/api"
VISITENKARTEN_CHANNEL = "C07SJMXQWEA"


def _bot_token() -> str:
    return os.environ["SLACK_BOT_TOKEN"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_bot_token()}"}


def fetch_recent_messages(hours: int = 24, latest_hours: int = 0) -> list[dict]:
    """Liest Nachrichten aus #visitenkarten in einem Zeitfenster.

    hours: untere Grenze (wie weit zurück, in Stunden ab jetzt)
    latest_hours: obere Grenze (bis wie nah an jetzt; 0 = bis jetzt)
    Beispiel: hours=3600, latest_hours=2880 → das 5.-letzte 30-Tage-Fenster.
    """
    now = datetime.now(timezone.utc)
    oldest_ts = str((now - timedelta(hours=hours)).timestamp())
    latest_ts = str((now - timedelta(hours=latest_hours)).timestamp()) if latest_hours else None

    messages: list[dict] = []
    cursor = None

    while True:
        params: dict = {
            "channel": VISITENKARTEN_CHANNEL,
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
                # z. B. not_in_channel oder ratelimited: sonst sähe ein Lauf ohne
                # gelesene Nachrichten aus wie ein ruhiger Tag
                problems.melde("Slack #visitenkarten nicht lesbar", str(data.get("error")))
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
        except (httpx.HTTPError, ValueError) as e:
            problems.melde("Slack #visitenkarten nicht lesbar", type(e).__name__)
            break

    # Skip messages from our own bot (KI-Scan summaries)
    filtered = [m for m in messages if not _is_bot_summary(m)]
    berichte = [m for m in filtered if ist_bericht(m)]
    if berichte:
        logger.info("%d Bericht(e) aus Claude-Sitzungen übersprungen (Signatur „Gesendet mit Claude“)", len(berichte))
        filtered = [m for m in filtered if not ist_bericht(m)]
    logger.info("Fetched %d messages from #visitenkarten (last %dh)", len(filtered), hours)
    return filtered


def _is_bot_summary(msg: dict) -> bool:
    text = msg.get("text", "")
    return "KI-Scan" in text and "Neue Kontakte" in text


# Slack-Formatierung (*fett*, _kursiv_, ~durch~, `code`, > Zitat) für den Vergleich entfernen.
# Gespiegelt aus objekte_handler/vollzug.py – die Pakete teilen bewusst keinen Code.
_FORMAT = re.compile(r"[*_~`>]")
_CLAUDE_SIGNATUR = re.compile(r"gesendet\s+mit\s+claude", re.IGNORECASE)


def ist_bericht(msg: dict) -> bool:
    """Ein Bericht aus einer Claude-Sitzung – keine neue Visitenkarte.

    Die Routine „Email-Kontakt-Scan“ postet jeden Morgen, welche Kontakte sie schon in
    Propstack angelegt hat, mit Signatur „Gesendet mit Claude“. Der Import las diese
    Berichte als Visitenkarten: Bei einem Kontakt kostete das nur einen KI-Aufruf und eine
    Dublettenprüfung, bei zweien (21.11.2026) lieferte die KI zwei JSON-Objekte, die
    Antwort galt als unlesbar und der Lauf wurde rot.

    Stand 21.11.2026 (nur gelesen, #visitenkarten 25.06.–21.11.2026): 9 von 9 Nachrichten
    mit dieser Signatur waren solche Berichte. Grenze wie beim #objekte-Handler: Wer eine
    Karte über Claude postet, lässt die Signatur weg.
    """
    return bool(_CLAUDE_SIGNATUR.search(_FORMAT.sub("", msg.get("text") or "")))


# Bildformate, die die Claude-API annimmt, und die Größe, bis zu der wir das Original schicken
_API_BILDTYPEN = ("image/jpeg", "image/png", "image/gif", "image/webp")
_MAX_BILD_BYTES = 4_500_000
# Vorschaubilder, die Slack zu jedem Bild erzeugt – größte zuerst
_VORSCHAUEN = ("thumb_1024", "thumb_960", "thumb_800", "thumb_720", "thumb_480", "thumb_360")


def _bildquelle(f: dict) -> tuple[str | None, str]:
    """(URL, Mimetype) des Bildes, das an die KI geht.

    Normal das Original. Bei einem Format, das die Claude-API nicht annimmt (HEIC vom
    iPhone), oder einem sehr großen Foto die größte Vorschau, die Slack erzeugt hat."""
    mimetype = f.get("mimetype", "")
    original = f.get("url_private_download") or f.get("url_private")
    passt = mimetype in _API_BILDTYPEN or mimetype == "image/jpg"
    if passt and (f.get("size") or 0) <= _MAX_BILD_BYTES:
        return original, mimetype
    for key in _VORSCHAUEN:
        if f.get(key):
            return f[key], ""  # Typ steht erst in der Antwort
    return original, mimetype


def get_message_images(msg: dict) -> list[tuple[bytes, str]]:
    """Lädt Bilder aus einer Slack-Nachricht herunter: je Bild (Inhalt, Mimetype)."""
    images: list[tuple[bytes, str]] = []
    files = msg.get("files", [])

    for f in files:
        if not f.get("mimetype", "").startswith("image/"):
            continue

        url, mimetype = _bildquelle(f)
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
                if not mimetype:
                    mimetype = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                images.append((response.content, mimetype))
                logger.info("Image downloaded: %s (%d bytes, %s)", f.get("name", "unknown"), len(response.content), mimetype)
            else:
                problems.melde("Visitenkarte nicht ladbar", f"HTTP {response.status_code}")
        except httpx.HTTPError as e:
            problems.melde("Visitenkarte nicht ladbar", type(e).__name__)

    return images


# --- Verarbeitungsmarker ---------------------------------------------------------------
# Der Lauf liest 48 h zurück, damit ein verspäteter oder ausgefallener Lauf keine Karte
# kostet. Ohne Marker ginge jede Karte zweimal durch die Bild-KI – liest sie am zweiten
# Tag ein Zeichen anders, entstünde ein zweiter Kontakt. Deshalb wie in den Handlern:
# eigenes ✅ an der Nachricht = verarbeitet.

CHECK_EMOJI = "white_check_mark"


def get_bot_user_id() -> str | None:
    """Eigene Bot-User-ID (auth.test). None, wenn Slack sie nicht liefert."""
    try:
        data = httpx.post(f"{SLACK_API_URL}/auth.test", headers=_headers(), timeout=30.0).json()
    except (httpx.HTTPError, ValueError) as e:
        problems.melde("Slack auth.test fehlgeschlagen", type(e).__name__)
        return None
    if not data.get("ok"):
        problems.melde("Slack auth.test fehlgeschlagen", str(data.get("error")))
        return None
    return data.get("user_id")


def ist_verarbeitet(msg: dict, bot_user_id: str | None) -> bool:
    """Trägt die Nachricht schon das eigene ✅? Fremde ✅ zählen nicht."""
    if not bot_user_id:
        return False
    for reaction in msg.get("reactions", []):
        if reaction.get("name") == CHECK_EMOJI and bot_user_id in (reaction.get("users") or []):
            return True
    return False


def markiere_verarbeitet(ts: str) -> bool:
    try:
        data = httpx.post(
            f"{SLACK_API_URL}/reactions.add",
            headers=_headers(),
            json={"channel": VISITENKARTEN_CHANNEL, "timestamp": ts, "name": CHECK_EMOJI},
            timeout=30.0,
        ).json()
    except (httpx.HTTPError, ValueError) as e:
        problems.melde("Verarbeitungsmarker nicht setzbar", type(e).__name__)
        return False
    if data.get("ok") or data.get("error") == "already_reacted":
        return True
    problems.melde("Verarbeitungsmarker nicht setzbar", str(data.get("error")))
    return False


def has_images(msg: dict) -> bool:
    files = msg.get("files", [])
    return any(f.get("mimetype", "").startswith("image/") for f in files)


def get_message_text(msg: dict) -> str:
    return msg.get("text", "").strip()
