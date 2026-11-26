from __future__ import annotations

import os

OBJEKTE_CHANNEL = "C07GH7AN80J"
CLAUDE_MODEL = "claude-sonnet-4-6"

BROKER_MAREK = 387451
# Sammelpostfach für Review-Aufgaben ohne eindeutigen Objekt-Verantwortlichen
# (Fallback + Empfänger für fehlt_in_ps). Der Sitz lief früher auf Oguzhan Sahin und ist
# inzwischen auf Lena Klinnert umgestellt – deshalb kein Personenname im Konstantennamen.
# Aktueller Inhaber laut GET /v1/brokers: Lena Klinnert.
BROKER_REVIEW_FALLBACK = 254958
BROKER_REVIEW_FALLBACK_NAME = "Lena Klinnert"

# Absagegrund "Fläche nicht mehr verfügbar" (Standard für Fremdvermietung)
RESERVATION_REASON_ABSAGE = 256998

# Abgesagt werden nur Deals der Vermietung: Pipelines, deren Name so beginnt
# ("300 Mieter", "300 Leverkusen", "300 Sontra"), und Deals ohne Pipeline. Deals der
# Verkaufs-Pipelines ("200 …", "Kaltenkirchen") an derselben Einheit bleiben offen –
# eine Vermietung beendet keinen Verkaufsprozess (19.11.2026: 321 solche Deals).
VERMIETUNGS_PIPELINE_PRAEFIX = "300"

CHECK_EMOJI = "white_check_mark"

# Slack-Nutzer → Propstack-Nutzer (Betreuer neuer Objekte). Gebraucht, solange der Bot den Slack-Scope
# users:read nicht hat (26.11.2026: users.info → missing_scope, Marek wäre sonst unter Lena gelaufen).
# Stand der IDs: GET /v1/brokers und Slack, 26.11.2026. Oguzhan hat keinen eigenen Propstack-Nutzer
# und schreibt wie im Connector unter Lena.
SLACK_ZU_PROPSTACK = {
    "U08E7PCGQHX": 347158,   # Florian Brimmers
    "U092XRXSY3X": 387451,   # Marek Zimmermann
    "U0806EX3EFL": 259613,   # Denise Kromeich
    "U0AJNQEMLRW": 254958,   # Lena Klinnert
    "U0A75JTEQRX": 254960,   # Marlene Jung
    "U087H2UMREF": 254958,   # Oguzhan Sahin → Lena Klinnert
}

# Objekt-Anlage über den Propstack-Connector (objekte_handler/anlage.py)
ANLAGE_MODELL = "claude-opus-5-5"
MCP_BETA = "mcp-client-2025-11-20"
MCP_URL_STANDARD = "https://propstack-mcp.kromeichpartner.workers.dev/mcp"
CONFIDENCE_THRESHOLD = 0.8


def _env_bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() in ("true", "1", "yes")


def dry_run() -> bool:
    """Default true (sicher für lokale Läufe) – der Cron setzt explizit false."""
    return _env_bool("DRY_RUN", "true")


def no_write() -> bool:
    """Reiner Lese-/Loglauf: keine Propstack-Writes, keine Reactions/Replies."""
    return _env_bool("NO_WRITE", "false")


def objekt_anlage() -> bool:
    """Exposés und „bitte anlegen“ über den Connector anlegen statt eine Aufgabe zu schreiben.
    Aus (Standard), bis der Connector das Service-Token kennt; im Dry-Run nie."""
    return _env_bool("OBJEKT_ANLAGE", "false") and not dry_run()


def mcp_url() -> str:
    return os.environ.get("PROPSTACK_MCP_URL") or MCP_URL_STANDARD


def mcp_service_secret() -> str:
    return os.environ.get("PROPSTACK_MCP_SERVICE_SECRET", "")


def nur_ts() -> str:
    """Probelauf: nur diese eine Nachricht verarbeiten (Slack-ts)."""
    return os.environ.get("NUR_TS", "").strip()


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
