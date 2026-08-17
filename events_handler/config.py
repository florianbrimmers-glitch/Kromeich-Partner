from __future__ import annotations

import os

# #events – Kanal mit weitergeleiteten Event-Einladungen (HTML-Anhänge)
EVENTS_CHANNEL = "C07N95AQRB2"
CLAUDE_MODEL = "claude-opus-4-8"

# Ziel: Asana-Projekt "08. (MKT) Maketing" (Schreibweise wie im Projektnamen),
# Abschnitt "Events". Der Handler schrieb zunächst versehentlich in das
# gleichnamige Alt-Projekt "Marketing" – die dort angelegten Aufgaben wurden
# am 17.08. hierher übertragen.
MARKETING_PROJECT_ID = "1212632642056791"
EVENTS_SECTION_ID = "1212657377620278"

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
# Der Token kann unter verschiedenen Secret-Namen hinterlegt sein – der erste
# gefüllte gewinnt. Fehlende Secrets kommen in GitHub Actions als LEERER String
# an, deshalb wird auf Inhalt und nicht auf Existenz geprüft.
ASANA_TOKEN_ENV_NAMES = (
    "ASANA_ACCESS_TOKEN",
    "ASANA_TOKEN",
    "ASANA_PAT",
    "ASANA_API_KEY",
    "ASANA_API_TOKEN",
    "ASANA_PERSONAL_ACCESS_TOKEN",
)


def asana_token_env_name() -> str | None:
    """Name der Env-Variable, die den Token liefert (für Logging/Diagnose)."""
    for name in ASANA_TOKEN_ENV_NAMES:
        if os.environ.get(name, "").strip():
            return name
    return None


def asana_token() -> str:
    """Asana Personal Access Token aus dem erstbesten gefüllten Secret."""
    name = asana_token_env_name()
    if not name:
        raise RuntimeError(
            "Kein Asana-Token gefunden. Eines dieser Repository-Secrets füllen "
            f"({', '.join(ASANA_TOKEN_ENV_NAMES)}) – "
            "Settings -> Secrets and variables -> Actions."
        )
    return os.environ[name].strip()


def project_id() -> str:
    return os.environ.get("ASANA_PROJECT_ID") or MARKETING_PROJECT_ID


def section_id() -> str:
    """Ziel-Abschnitt; per ASANA_SECTION_ID überschreibbar (z.B. Test-Abschnitt)."""
    return os.environ.get("ASANA_SECTION_ID") or EVENTS_SECTION_ID
