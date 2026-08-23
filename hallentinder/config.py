from __future__ import annotations

import os

# Absender-Kennung, die am erzeugten Propstack-Kontakt hinterlegt wird
QUELLE = "Hallentinder"

# Session-Token: Lebensdauer und Obergrenze des In-Memory-Stores
SESSION_TTL_SECONDS = 2 * 60 * 60
MAX_SESSIONS = 5000

# Wie viele Karten pro Abruf ans Frontend gehen
CARD_PAGE_SIZE = 10

# Unter dieser Trefferzahl wird der Suchradius stufenweise erweitert
MIN_CARDS_BEFORE_EXPANSION = 5
MAX_RADIUS_KM = 400


def _env_bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() in ("true", "1", "yes")


def no_write() -> bool:
    """Reiner Lese-/Loglauf: keine Propstack-Writes (Kontakte, Deals)."""
    return _env_bool("NO_WRITE", "false")


def propstack_key() -> str:
    return os.environ["PROPSTACK_API_KEY"]


def propstack_key_objekte() -> str:
    """Optionaler Lese-Key; sonst der allgemeine Key (wie in den Handlern)."""
    return os.environ.get("PROPSTACK_KEY_OBJEKTE") or propstack_key()


def port() -> int:
    return int(os.environ.get("HALLENTINDER_PORT", "8080"))


def host() -> str:
    return os.environ.get("HALLENTINDER_HOST", "0.0.0.0")


def cache_ttl() -> int:
    """1 h: der volle Bestandsabruf dauert rund zwei Minuten, deshalb selten
    und im Hintergrund (siehe catalog._Cache)."""
    return int(os.environ.get("HALLENTINDER_CACHE_TTL", "3600"))


def default_radius_km() -> int:
    return int(os.environ.get("HALLENTINDER_RADIUS_KM", "50"))


def allowed_origins() -> list[str]:
    raw = os.environ.get("HALLENTINDER_ALLOWED_ORIGINS", "").strip()
    return [o.strip() for o in raw.split(",") if o.strip()]


def strict_halle() -> bool:
    """true = nur Objekte mit erkennbarem Hallen-/Logistik-Merkmal aufnehmen.
    Default false, weil die Kategoriefelder im Bestand uneinheitlich gepflegt sind."""
    return _env_bool("HALLENTINDER_STRICT_HALLE", "false")


def rate_limit_per_hour() -> int:
    return int(os.environ.get("HALLENTINDER_RATE_LIMIT", "60"))
