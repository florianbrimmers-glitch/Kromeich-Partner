from __future__ import annotations

import os
import secrets
from pathlib import Path

# Vorgangsnummern für Menschen am Telefon: KP-2026-0001
NUMMER_PRAEFIX = "KP"

# Grenzen für Uploads. Ein Grundbuchauszug ist ein PDF von wenigen Seiten,
# Objektfotos sind Handybilder – alles darüber ist ein Fehler oder ein Angriff.
MAX_NACHWEIS_BYTES = 10 * 1024 * 1024
MAX_BILD_BYTES = 10 * 1024 * 1024
MAX_BILDER = 10

NACHWEIS_TYPEN = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
BILD_TYPEN = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

# Nach dieser Frist erinnert die Prüfansicht an unerledigte Vorgänge
PRUEFFRIST_TAGE = 3


def daten_verzeichnis() -> Path:
    """Ablage für Datenbank und hochgeladene Dateien.

    Bewusst NICHT unter static/: hier liegen Grundbuchauszüge, die niemals
    über einen statischen Pfad erreichbar sein dürfen."""
    pfad = Path(os.environ.get("EIGENTUEMER_DATEN", "eigentuemer_daten")).resolve()
    pfad.mkdir(parents=True, exist_ok=True)
    return pfad


def datenbank() -> Path:
    return daten_verzeichnis() / "einreichungen.sqlite3"


def basis_url() -> str:
    """Absolute Adresse für Links in E-Mails."""
    gesetzt = os.environ.get("EIGENTUEMER_BASIS_URL", "").strip().rstrip("/")
    return gesetzt or f"http://localhost:{port()}"


# --- E-Mail ------------------------------------------------------------------

def smtp_host() -> str:
    return os.environ.get("EIGENTUEMER_SMTP_HOST", "").strip()


def smtp_port() -> int:
    return int(os.environ.get("EIGENTUEMER_SMTP_PORT", "587"))


def smtp_benutzer() -> str:
    return os.environ.get("EIGENTUEMER_SMTP_BENUTZER", "").strip()


def smtp_passwort() -> str:
    return os.environ.get("EIGENTUEMER_SMTP_PASSWORT", "")


def absender() -> str:
    return os.environ.get("EIGENTUEMER_ABSENDER", "").strip() or "noreply@kromeichpartner.de"


def intern_empfaenger() -> list[str]:
    """Wer intern über neue und erneut zu prüfende Vorgänge informiert wird."""
    roh = os.environ.get("EIGENTUEMER_INTERN_AN", "").strip()
    return [a.strip() for a in roh.split(",") if a.strip()]


def mail_aktiv() -> bool:
    """Ohne SMTP-Konfiguration wird keine Mail verschickt, sondern geloggt.

    Derselbe Gedanke wie NO_WRITE beim Hallentinder: Der sichere Zustand ist
    der Ausgangszustand. Wer testet, verschickt nichts an echte Adressen."""
    return bool(smtp_host())


def host() -> str:
    return os.environ.get("EIGENTUEMER_HOST", "0.0.0.0")


def port() -> int:
    return int(os.environ.get("EIGENTUEMER_PORT", "8090"))


_erzeugtes_passwort: str | None = None


def pruef_passwort() -> str:
    """Zugang zur internen Prüfansicht.

    Ohne gesetztes Passwort wird beim Start eines erzeugt und ins Log
    geschrieben – so ist die Ansicht nie versehentlich offen, und für einen
    Prototyp muss trotzdem niemand vorher etwas konfigurieren."""
    global _erzeugtes_passwort
    gesetzt = os.environ.get("EIGENTUEMER_PRUEF_PASSWORT", "").strip()
    if gesetzt:
        return gesetzt
    if _erzeugtes_passwort is None:
        _erzeugtes_passwort = secrets.token_urlsafe(9)
    return _erzeugtes_passwort


def passwort_wurde_erzeugt() -> bool:
    return not os.environ.get("EIGENTUEMER_PRUEF_PASSWORT", "").strip()
