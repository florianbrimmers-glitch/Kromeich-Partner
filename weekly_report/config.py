from __future__ import annotations

import os

# Oguzhan Sahin – Empfänger der Wochenreport-DM
REPORT_RECIPIENT = "U087H2UMREF"

# Broker, dessen Aufgaben als "Prüfaufgaben" gelten. 254958 ist die ID, auf der die
# Prüfaufgaben tatsächlich gepflegt werden (317 Aufgaben, davon 25 abgeschlossen);
# 387451 (Marek) trägt nur einen Bruchteil. Bewusst neutral benannt: der Kommentar in
# objekte_handler/config.py nennt 254958 "Oguzhan", GET /v1/brokers liefert dafür
# "Lena Klinnert" – der Widerspruch soll sich hier nicht fortschreiben.
DEFAULT_PRUEFER_BROKER_IDS = "254958"

# Deep-Links in der Slack-Nachricht (Host abgeleitet aus public_expose_url).
PROPSTACK_APP_BASE = "https://crm.propstack.de/app/portfolio"

# Propstack liefert für Projekte keinen Zeitstempel. Ein Projekt gilt als neu, wenn
# seine früheste Einheit im Berichtsfenster liegt.
BERLIN_TZ = "Europe/Berlin"

# Pro Block maximal so viele Detailzeilen, danach "… und N weitere".
MAX_DETAIL_LINES = 10


def _env_bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() in ("true", "1", "yes")


def dry_run() -> bool:
    """Default true (sicher für lokale Läufe) – der Cron setzt explizit false."""
    return _env_bool("DRY_RUN", "true")


def include_touched() -> bool:
    """Zusätzlicher Block "bearbeitet, aber offen" (updated_at > original_created_at).

    Aus, weil der User ausdrücklich nur abgeschlossene Prüfaufgaben wollte. Anschalten,
    falls sich der done-Block als zu dünn erweist – reine Env-Variable, kein Code-Umbau."""
    return _env_bool("REPORT_INCLUDE_TOUCHED", "false")


def _env_str(name: str, default: str) -> str:
    """Wie os.environ.get, behandelt aber einen leeren Wert wie "nicht gesetzt".

    Nötig, weil GitHub Actions nicht belegte workflow_dispatch-Inputs als leeren
    String durchreicht – bei Cron-Läufen ist REPORT_RECIPIENT genau das."""
    return os.environ.get(name, "").strip() or default


def report_hours() -> int:
    """Berichtsfenster in Stunden zurück (Default 7 Tage)."""
    return int(_env_str("REPORT_HOURS", "168"))


def run_hour_berlin() -> int | None:
    """Stunde (Europe/Berlin), zu der der Lauf durchgehen darf – None = Guard aus.

    GitHub-Actions-Cron kennt nur UTC. Der Workflow feuert deshalb zweimal (17:03 und
    18:03 UTC); dieser Guard lässt je nach Sommer-/Winterzeit genau einen Lauf durch,
    damit der Report ganzjährig um 19 Uhr Ortszeit ankommt."""
    raw = os.environ.get("RUN_HOUR_BERLIN", "19").strip()
    return int(raw) if raw else None


def pruefer_broker_ids() -> list[int]:
    raw = _env_str("PRUEFER_BROKER_IDS", DEFAULT_PRUEFER_BROKER_IDS)
    return [int(part) for part in raw.replace(";", ",").split(",") if part.strip()]


def report_recipient() -> str:
    return _env_str("REPORT_RECIPIENT", REPORT_RECIPIENT)


def report_log_path() -> str:
    return _env_str("REPORT_LOG_PATH", "weekly_report.jsonl")


def slack_bot_token() -> str:
    return os.environ["SLACK_BOT_TOKEN"]


def propstack_key_objekte() -> str:
    """Projekte/Einheiten: PROPSTACK_API_KEY, PROPSTACK_KEY_OBJEKTE als Override."""
    return os.environ.get("PROPSTACK_KEY_OBJEKTE") or os.environ["PROPSTACK_API_KEY"]


def propstack_key_tasks() -> str:
    """Aufgaben/Aktivitäten brauchen den Tasks-Key – der Objekt-Key hat dort keine Rechte."""
    return os.environ.get("PROPSTACK_KEY_TASKS") or os.environ["PROPSTACK_API_KEY"]
