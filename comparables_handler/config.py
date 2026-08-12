from __future__ import annotations

import os

CLAUDE_MODEL = "claude-opus-4-8"

# --- Google-Drive-Datenbasis -------------------------------------------------
# Gefunden am 12.08.2026 per Drive-Suche. Zwei "03. Leasing"-Ordner (eigenes
# Shared Drive + ein von felix.kern geteilter) und zwei "Mietangebote"-Ordner.
# Die Ordner-IDs sind nur SAATGUT für die Rekursion – der Titel-Scan
# ("Mietangebot" im Dateinamen) findet zusätzlich alles, was woanders liegt.
SEED_FOLDER_IDS = (
    "1oHcqgQVhMu2_54p8PxH2vEWfWHgXbwD2",  # 03. Leasing (Shared Drive)
    "13fQQg1EbnE58iHREJKgIK_esIT7HFVdh",  # 03. Leasing (geteilt, felix.kern)
    "15BorjO7bV8DLOC_lQkL57LelcYvGBYV6",  # Mietangebote
    "1ykTBz0p_EhVSND2apNhp8BPvrfvgFRgP",  # Mietangebote
)

# Titel-Suchbegriffe (Drive-Suche ist case-insensitive)
TITLE_TERMS = ("Mietangebot",)

# Wie tief die Ordner-Rekursion läuft (Schutz gegen Endlos-Bäume)
MAX_FOLDER_DEPTH = 6

# Drive-MIME-Typen, aus denen wir Konditionen lesen können
MIME_PDF = "application/pdf"
MIME_FOLDER = "application/vnd.google-apps.folder"
MIME_SHORTCUT = "application/vnd.google-apps.shortcut"
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_GDOC = "application/vnd.google-apps.document"
MIME_GSLIDES = "application/vnd.google-apps.presentation"
MIME_GSHEET = "application/vnd.google-apps.spreadsheet"

SUPPORTED_MIMETYPES = (
    MIME_PDF, MIME_DOCX, MIME_PPTX, MIME_XLSX,
    MIME_GDOC, MIME_GSLIDES, MIME_GSHEET,
)

# Claude nimmt PDFs direkt als Dokument-Block (auch Scans). Limit der API: 32 MB.
MAX_PDF_BYTES = 30_000_000
MAX_TEXT_CHARS = 60_000

# --- Ausschlussregeln (Task-Vorgabe) ---------------------------------------
# Eigene Vorlagen: Dateiname enthält einen dieser Begriffe.
VORLAGE_MARKER = ("vorlage", "muster", "template", "blanko", "entwurf leer")
# Kromeich-Büromiete: die eigene Büromiete ist kein Marktangebot.
# Trifft z.B. "Mietangebot-Kromeich GmbH-2025-06_V1.pdf" (monatliche Rechnung).
EIGENMIETE_MARKER = ("kromeich gmbh",)
# Anlagen-/Beiblatt-Dateien tragen keine eigenen Konditionen.
ANLAGEN_MARKER = ("anlage", "anlagen", "beiblatt")

# Anbieter-Namen, die ein EIGENES (von K&P versandtes) Angebot markieren
EIGENE_ANBIETER_MARKER = ("kromeich", "k&p", "kromeich & partner")

# --- Plausibilität (Ausreißer fliegen mit Grund raus) ----------------------
KALTMIETE_MIN_EUR_QM = 1.0
KALTMIETE_MAX_EUR_QM = 25.0
NEBENKOSTEN_MIN_EUR_QM = 0.1
NEBENKOSTEN_MAX_EUR_QM = 6.0
FLAECHE_MIN_QM = 100.0
FLAECHE_MAX_QM = 500_000.0
LAUFZEIT_MIN_MONATE = 6
LAUFZEIT_MAX_MONATE = 360

CONFIDENCE_THRESHOLD = 0.5

# Ab wie vielen Datenpunkten eine Leitregion (2-stellige PLZ) eigenständig
# ausgewiesen wird. Darunter zählt sie nur in die Postleitzone (1-stellig).
MIN_N_LEITREGION = 3

# --- Slack ------------------------------------------------------------------
# Kein eigener Leasing-/Comparables-Kanal vorhanden (Stand 12.08.2026), daher
# #objekte als Ziel – dort läuft die operative Objekt-Kommunikation und der
# Bot ist bereits Mitglied. Per COMPARABLES_CHANNEL umstellbar.
DEFAULT_CHANNEL = "C07GH7AN80J"  # #objekte


def _env_bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() in ("true", "1", "yes")


def dry_run() -> bool:
    """Default true (sicher): Report wird gebaut und geloggt, aber nicht gepostet."""
    return _env_bool("DRY_RUN", "true")


def no_write() -> bool:
    """Reiner Lese-/Loglauf: kein Slack-Post, keine Dateien nach außen."""
    return _env_bool("NO_WRITE", "false")


def slack_channel() -> str:
    return os.environ.get("COMPARABLES_CHANNEL") or DEFAULT_CHANNEL


def slack_bot_token() -> str:
    return os.environ["SLACK_BOT_TOKEN"]


def anthropic_api_key() -> str:
    return os.environ["ANTHROPIC_API_KEY"]


def decision_log_path() -> str:
    return os.environ.get("DECISION_LOG_PATH", "comparables_decisions.jsonl")


def dataset_path() -> str:
    """Flache Comparables-Tabelle des Laufs (CSV, als Actions-Artefakt)."""
    return os.environ.get("DATASET_PATH", "comparables_dataset.csv")


def cache_path() -> str:
    """Extraktions-Cache: fileId+modifiedTime -> Extraktion.

    Spart LLM-Calls über Monate hinweg; unveränderte Dokumente werden nicht
    erneut an Claude geschickt. Leerer Wert schaltet den Cache ab.
    """
    return os.environ.get("EXTRACTION_CACHE_PATH", "comparables_cache.jsonl")


def pdf_path() -> str:
    return os.environ.get("PDF_PATH", "comparables_report.pdf")


def make_pdf() -> bool:
    """K&P-PDF erzeugen (Task: 'auf Abruf für Kundengespräche')."""
    return _env_bool("MAKE_PDF", "false")


def max_documents() -> int:
    """Obergrenze extrahierter Dokumente pro Lauf (0 = unbegrenzt).

    Nur als Kostenbremse/Testhilfe – im Normalbetrieb 0, damit nie still
    ein Teil der Datenbasis wegfällt.
    """
    return int(os.environ.get("MAX_DOCUMENTS", "0"))


def kp_design_dir() -> str:
    """Verzeichnis des kp-design-Skills (Schriften für das PDF).

    Fehlt es, fällt das PDF auf reportlab-Standardschriften zurück.
    """
    return os.environ.get(
        "KP_DESIGN_DIR",
        os.path.expanduser("~/.claude/skills/synced/kp-design"),
    )


# --- Google-Drive-Zugang ----------------------------------------------------
# Muster wie src/gmail_client.py: Client-ID/Secret + Refresh-Token.
# ACHTUNG: Die bestehenden GOOGLE_REFRESH_TOKEN* sind auf gmail.readonly
# ausgestellt und reichen für Drive NICHT. Deshalb zuerst ein eigenes
# Drive-Token, dann Fallback (funktioniert nur, wenn dieses Token den
# drive.readonly-Scope mitträgt).
DRIVE_SCOPES = ("https://www.googleapis.com/auth/drive.readonly",)

DRIVE_REFRESH_TOKEN_ENV_NAMES = (
    "GOOGLE_REFRESH_TOKEN_DRIVE",
    "GOOGLE_DRIVE_REFRESH_TOKEN",
    "GOOGLE_REFRESH_TOKEN",
)


def drive_refresh_token_env_name() -> str | None:
    for name in DRIVE_REFRESH_TOKEN_ENV_NAMES:
        if os.environ.get(name, "").strip():
            return name
    return None


def drive_refresh_token() -> str:
    name = drive_refresh_token_env_name()
    if not name:
        raise RuntimeError(
            "Kein Google-Refresh-Token für Drive gefunden. Eines dieser Secrets "
            f"füllen ({', '.join(DRIVE_REFRESH_TOKEN_ENV_NAMES)}) – das Token muss "
            "den Scope drive.readonly tragen (siehe comparables_handler/README.md)."
        )
    return os.environ[name].strip()


def google_client_id() -> str:
    return os.environ["GOOGLE_CLIENT_ID"]


def google_client_secret() -> str:
    return os.environ["GOOGLE_CLIENT_SECRET"]
