from __future__ import annotations

import os

OBJEKTE_CHANNEL = "C07GH7AN80J"
CLAUDE_MODEL = "claude-sonnet-4-6"

BROKER_MAREK = 387451
BROKER_OGUZHAN = 254958  # Fallback + Empfänger für fehlt_in_ps

# Absagegrund "Fläche nicht mehr verfügbar" (Standard für Fremdvermietung)
RESERVATION_REASON_ABSAGE = 256998

CHECK_EMOJI = "white_check_mark"
CONFIDENCE_THRESHOLD = 0.8


def _env_bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() in ("true", "1", "yes")


def dry_run() -> bool:
    """Woche-1-Regel: Default true – alles läuft als Stufe B."""
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
    return os.environ.get("DECISION_LOG_PATH", "objekte_decisions.jsonl")


def slack_bot_token() -> str:
    return os.environ["SLACK_BOT_TOKEN"]


def anthropic_api_key() -> str:
    return os.environ["ANTHROPIC_API_KEY"]


def propstack_key_objekte() -> str:
    """Standard: der bestehende PROPSTACK_API_KEY; PROPSTACK_KEY_OBJEKTE als optionaler Override."""
    return os.environ.get("PROPSTACK_KEY_OBJEKTE") or os.environ["PROPSTACK_API_KEY"]


def propstack_key_tasks() -> str:
    """Standard: der bestehende PROPSTACK_API_KEY; PROPSTACK_KEY_TASKS als optionaler Override."""
    return os.environ.get("PROPSTACK_KEY_TASKS") or os.environ["PROPSTACK_API_KEY"]
