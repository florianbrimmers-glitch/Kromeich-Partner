from __future__ import annotations

import os

# #events – Kanal mit weitergeleiteten Event-Einladungen (HTML-Anhänge)
EVENTS_CHANNEL = "C07N95AQRB2"
CLAUDE_MODEL = "claude-opus-4-8"

# Ziel-Tabelle "Messen & Events" (Drive: 01. Allgemein / 02. Marketing / 04. Events)
SHEET_ID = "1ppUJOOduq4Bdjw4mpxokfLlUHFuRWmRfCqf9xCHIbKw"
SHEET_TAB = "Tabellenblatt1"

CHECK_EMOJI = "white_check_mark"
CONFIDENCE_THRESHOLD = 0.6

# Spaltenreihenfolge der Zieltabelle – "Funktion KP" und "Spannend für" bleiben leer (Mensch)
SHEET_COLUMNS = ["Datum", "Event", "Branche", "Ort", "Kosten (nur Ticket)",
                 "Funktion KP", "Spannend für", "Notiz / Link"]
GOOGLE_SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


def _env_bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() in ("true", "1", "yes")


def dry_run() -> bool:
    """Default true (sicher). Cron setzt explizit false, sobald scharf."""
    return _env_bool("DRY_RUN", "true")


def no_write() -> bool:
    """Reiner Lese-/Loglauf: keine Sheet-Writes, keine Reactions/Replies."""
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


# --- Google-Sheets-Auth: Service-Account bevorzugt, sonst OAuth-Refresh-Token ---
def google_service_account_json() -> str | None:
    return os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or None


def google_client_id() -> str:
    return os.environ.get("GOOGLE_CLIENT_ID", "")


def google_client_secret() -> str:
    return os.environ.get("GOOGLE_CLIENT_SECRET", "")


def google_sheets_refresh_token() -> str | None:
    return os.environ.get("GOOGLE_SHEETS_REFRESH_TOKEN") or None
