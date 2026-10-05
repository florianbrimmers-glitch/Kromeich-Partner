from __future__ import annotations

import os

# #personalkarussel-logistik – privater Kanal, der Bot muss eingeladen sein
PERSONALKARUSSELL_CHANNEL = "C090NSRC36U"
CLAUDE_MODEL = "claude-sonnet-4-6"

# Sammelpostfach für Review-Aufgaben (derselbe Sitz wie beim #objekte-Handler).
# Aktueller Inhaber laut GET /v1/brokers: Lena Klinnert.
BROKER_REVIEW_FALLBACK = 254958
BROKER_REVIEW_FALLBACK_NAME = "Lena Klinnert"

CHECK_EMOJI = "white_check_mark"
CONFIDENCE_THRESHOLD = 0.8


def _env_bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() in ("true", "1", "yes")


def dry_run() -> bool:
    """Default true (sicher für lokale Läufe) – alles läuft als Stufe B."""
    return _env_bool("DRY_RUN", "true")


def no_write() -> bool:
    """Reiner Lese-/Loglauf: keine Propstack-Writes, keine Reactions/Replies."""
    return _env_bool("NO_WRITE", "false")


def scan_hours() -> int:
    return int(os.environ.get("SCAN_HOURS", "26"))


def scan_latest_hours() -> int:
    return int(os.environ.get("SCAN_LATEST_HOURS", "0"))


def thread_lookback_hours() -> int:
    return int(os.environ.get("THREAD_LOOKBACK_HOURS", "96"))


def decision_log_path() -> str:
    return os.environ.get("DECISION_LOG_PATH", "personalkarussell_decisions.jsonl")


def slack_bot_token() -> str:
    return os.environ["SLACK_BOT_TOKEN"]


def anthropic_api_key() -> str:
    return os.environ["ANTHROPIC_API_KEY"]


def propstack_key_v1() -> str:
    """Kontakte lesen/ändern, Aufgaben anlegen – dasselbe Secret wie die Kontakt-Pipelines."""
    return os.environ["PROPSTACK_API_KEY"]


def propstack_key_v2() -> str:
    """Firmen-Verknüpfungen (V2 /relationships) – dasselbe Secret wie die Kontakt-Pipeline."""
    return os.environ["PROPSTACK_API_V2_CONTACTS"]
