from __future__ import annotations

import os

# #newsletter – täglicher "Logistik-Deal Radar" (Marktnews-Digest)
NEWSLETTER_CHANNEL = "C07NL0KET40"
CLAUDE_MODEL = "claude-opus-4-8"

BROKER_MAREK = 387451    # Empfänger der Newsletter-Review-Aufgaben (Stufe B)

# Absagegrund "Fläche nicht mehr verfügbar" (Standard für Fremdvermietung)
RESERVATION_REASON_ABSAGE = 256998

CHECK_EMOJI = "white_check_mark"
CONFIDENCE_THRESHOLD = 0.8

# Domänenwissen für alle KI-Schritte (Extraktion, Query-Vorschlag, Objekt-Auswahl).
# Kromeich & Partner ist Makler für Gewerbe-/Logistikimmobilien in Deutschland.
DOMAIN_CONTEXT = """Domänen-Kontext: Kromeich & Partner ist ein Makler für Gewerbe- und Logistikimmobilien in Deutschland. In Logistik-Marktmeldungen genannte Firmen haben typische Rollen – nutze dein Branchenwissen, um sie richtig einzuordnen:
- EIGENTÜMER / ENTWICKLER / INVESTOREN der Immobilien (sie besitzen/bauen/vermieten die Flächen): u.a. Verdion, Garbe (Garbe Industrial), Panattoni, Prologis, Logicor, VGP, SEGRO, GLP, P3, Four Parx, Realterm, Hillwood, Nuveen, CTP, Aurelis, Frasers, Mileway, Dietz, Ixocon, Feldberg, Sunrise Real Estate.
- MIETER / NUTZER (mieten Fläche an): das jeweils genannte Unternehmen, z.B. Brabus, DHL, Alstom, Metro/GVS.
- MAKLER / BERATER: z.B. CBRE, BNP Paribas Real Estate, JLL, Colliers, Logivest, Realogis.
Ein Projekt-/Parkname trägt meist den Eigentümer/Entwickler (z.B. „Verdion PremierPark" → Eigentümer/Entwickler Verdion). Objekte im eigenen CRM sind oft nach ihrer Adresse benannt, nicht nach dem Projektnamen."""


def _env_bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() in ("true", "1", "yes")


def dry_run() -> bool:
    """Default true (sicher für lokale Läufe) – der Cron setzt explizit false, sobald scharf."""
    return _env_bool("DRY_RUN", "true")


def no_write() -> bool:
    """Reiner Lese-/Loglauf: keine Propstack-Writes, keine Reactions/Replies."""
    return _env_bool("NO_WRITE", "false")


def scan_hours() -> int:
    """Standard 27h: deckt den ~22:18-CEST-Digest des Vortags plus Überlappung ab."""
    return int(os.environ.get("SCAN_HOURS", "27"))


def scan_latest_hours() -> int:
    return int(os.environ.get("SCAN_LATEST_HOURS", "0"))


def decision_log_path() -> str:
    return os.environ.get("DECISION_LOG_PATH", "newsletter_decisions.jsonl")


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
