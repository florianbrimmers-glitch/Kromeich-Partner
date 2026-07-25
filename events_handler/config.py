from __future__ import annotations

import os

# #events – Kanal mit weitergeleiteten Event-Einladungen (HTML-Anhänge)
EVENTS_CHANNEL = "C07N95AQRB2"
CLAUDE_MODEL = "claude-opus-4-8"

# Ziel: Asana-Projekt "Marketing", bestehender Abschnitt "Events"
# (mit Marlene abgestimmt – die Events-Liste zieht von Google Sheets nach Asana um).
MARKETING_PROJECT_ID = "1211638618946856"
EVENTS_SECTION_ID = "1211803155426815"

CHECK_EMOJI = "white_check_mark"
CONFIDENCE_THRESHOLD = 0.6


def _env_bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() in ("true", "1", "yes")


def dry_run() -> bool:
    """Default true (sicher). Cron setzt explizit false, sobald scharf."""
    return _env_bool("DRY_RUN", "true")


def no_write() -> bool:
    """Reiner Lese-/Loglauf: keine Asana-Writes, keine Reactions/Replies."""
    return _env_bool("NO_WRITE", "false")


def scan_hours() -> int:
    return int(os.environ.get("SCAN_HOURS", "27"))


def scan_latest_hours() -> int:
    return int(os.environ.get("SCAN_LATEST_HOURS", "0"))


def decision_log_path() -> str:
    return os.environ.get("DECISION_LOG_PATH", "events_decisions.jsonl")


def slack_bot_token() -> str:
    return os.environ["SLACK_BOT_TOKEN"]


def anthropic_api_key() -> str:
    return os.environ["ANTHROPIC_API_KEY"]


# --- Asana-Ziel: Token als GitHub-Actions-Secret, Projekt/Abschnitt per Env überschreibbar ---
def asana_token() -> str:
    return os.environ["ASANA_ACCESS_TOKEN"]


def project_id() -> str:
    return os.environ.get("ASANA_PROJECT_ID") or MARKETING_PROJECT_ID


def section_id() -> str:
    """Ziel-Abschnitt; per ASANA_SECTION_ID überschreibbar (z.B. Test-Abschnitt)."""
    return os.environ.get("ASANA_SECTION_ID") or EVENTS_SECTION_ID
