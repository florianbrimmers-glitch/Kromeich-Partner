from __future__ import annotations

import logging
import re
import threading
import time

from . import config, propstack
from .models import HallCard

logger = logging.getLogger(__name__)

# Die Propstack-Enums des Bestands (Stand des Diagnoselaufs, hallentinder.diagnose):
# object_type COMMERCIAL/LIVING, rs_type INDUSTRY/APARTMENT/TRADE_SITE/OFFICE/…,
# rs_category HALL (1433), None (688), OFFICE_SPACE, TRADE_SITE, STORAGE_HALL, …
AUSSCHLUSS_OBJECT_TYPE = {"LIVING"}
AUSSCHLUSS_RS_TYPE = {"APARTMENT"}
# Gewerbe, aber keine Halle – gehört nicht in einen Hallentinder
AUSSCHLUSS_RS_CATEGORY = {
    "OFFICE", "OFFICE_SPACE", "OFFICE_BUILDING", "OFFICE_FLOOR", "OFFICE_CENTRE",
    "RETAIL_SPACE", "SALES_AREA", "SHOP", "STORE", "SHOWROOM", "KIOSK",
    "GASTRONOMY", "RESTAURANT", "HOTEL", "PRACTICE", "PRACTICE_FLOOR", "PRACTICE_HOUSE",
    "ROOF_STOREY", "LIVING_AND_COMMERCIAL_BUILDING", "MAISONETTE",
}
# Kategorien mit eindeutigem Hallen-/Lagerbezug (für HALLENTINDER_STRICT_HALLE)
HALLE_RS_CATEGORY = {
    "HALL", "STORAGE_HALL", "INDUSTRY_HALL", "STORAGE_AREA", "HIGH_LIFT_WAREHOUSE",
    "INDUSTRY_AREA", "PRODUCTION_HALL", "SERVICE_AREA", "TRADE_SITE", "REPAIR_SHOP",
}
# Zusätzliche Textkeywords – greifen nur, wenn die Enums nichts hergeben
AUSSCHLUSS_KEYWORDS = (
    "wohnung", "appartement", "einfamilien", "mehrfamilien",
    "penthouse", "villa", "reihenhaus", "doppelhaus",
)
# Vermarktungsarten, die nur Kauf bedeuten
KAUF_KEYWORDS = ("buy", "kauf", "sale", "verkauf")


def _scalar(value):
    """Propstack liefert manche Felder als Custom-Field-Objekt {"label":…, "value":…}.
    Diese auf den reinen Wert reduzieren; Skalare unverändert durchreichen."""
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _text(value) -> str | None:
    value = _scalar(value)
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return text or None


def _zahl(value) -> float | None:
    """Zahl robust lesen – auch deutsch formatierte Strings.

    "3.500" ist eine Tausender-, "8.5" eine Dezimaltrennung; wer hier nur
    Punkte durch Kommas ersetzt, macht aus 3.500 m² dreieinhalb."""
    value = _scalar(value)
    if isinstance(value, bool) or value is None or isinstance(value, (dict, list)):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None
    if "," in text and "." in text:
        # letztes Trennzeichen ist das Dezimalzeichen
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", text):
        text = text.replace(".", "")

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _enum(raw: dict, feld: str) -> str:
    """Enum-Wert normalisiert (Großbuchstaben, ohne Custom-Field-Hülle)."""
    wert = _scalar(raw.get(feld))
    if isinstance(wert, dict):
        wert = wert.get("name") or wert.get("label")
    return str(wert).strip().upper() if wert else ""


def _flag(value) -> bool:
    """Ausstattungsmerkmal als Ja/Nein. Propstack liefert hier Booleans;
    Strings und Zahlen werden trotzdem toleriert."""
    wert = _scalar(value)
    if isinstance(wert, bool):
        return wert
    if isinstance(wert, (int, float)):
        return wert > 0
    if isinstance(wert, str):
        return wert.strip().lower() in ("true", "ja", "yes", "1", "vorhanden")
    return False


def _kategorie_text(raw: dict) -> str:
    felder = [
        raw.get("rs_category"), raw.get("rs_type"), raw.get("object_type"),
        raw.get("name"), raw.get("title"),
    ]
    teile = []
    for feld in felder:
        wert = _scalar(feld)
        if isinstance(wert, dict):
            wert = wert.get("name") or wert.get("label")
        if wert:
            teile.append(str(wert))
    return " ".join(teile).lower()


def ist_verfuegbare_halle(raw: dict) -> bool:
    """Nur vermietbare Hallen ins Deck.

    Die Kategoriefelder sind im Bestand uneinheitlich gepflegt: eindeutige
    Nicht-Hallen fliegen raus, unklare Fälle bleiben drin (per
    HALLENTINDER_STRICT_HALLE umkehrbar)."""
    if _scalar(raw.get("rented")):
        return False

    vermarktung = str(_text(raw.get("marketing_type")) or "").lower()
    if vermarktung and any(k in vermarktung for k in KAUF_KEYWORDS):
        if not any(k in vermarktung for k in ("rent", "miet", "lease")):
            return False

    # Wohnimmobilien: zwei unabhängige Felder, die das sauber ausdrücken
    if _enum(raw, "object_type") in AUSSCHLUSS_OBJECT_TYPE:
        return False
    if _enum(raw, "rs_type") in AUSSCHLUSS_RS_TYPE:
        return False

    rs_category = _enum(raw, "rs_category")
    if rs_category in AUSSCHLUSS_RS_CATEGORY:
        return False
    if any(k in _kategorie_text(raw) for k in AUSSCHLUSS_KEYWORDS):
        return False

    if config.strict_halle():
        hat_hallen_signal = (
            rs_category in HALLE_RS_CATEGORY
            or _zahl(raw.get("hall_height")) is not None
            or _zahl(raw.get("industrial_area")) is not None
        )
        if not hat_hallen_signal:
            return False
    return True


def _bild_url(raw: dict) -> str | None:
    """Bild-URL aus den in Propstack üblichen Formen ziehen; None ist erlaubt."""
    for key in ("title_picture", "picture", "image"):
        wert = raw.get(key)
        if isinstance(wert, dict):
            for url_key in ("big_url", "original_url", "url", "medium_url"):
                if wert.get(url_key):
                    return str(wert[url_key])
        elif isinstance(wert, str) and wert.startswith("http"):
            return wert

    bilder = raw.get("images") or raw.get("pictures")
    if isinstance(bilder, list):
        for bild in bilder:
            if isinstance(bild, dict):
                for url_key in ("big_url", "original_url", "url", "medium_url"):
                    if bild.get(url_key):
                        return str(bild[url_key])
            elif isinstance(bild, str) and bild.startswith("http"):
                return bild
    return None


def _strasse(raw: dict) -> str | None:
    teile = [t for t in (_text(raw.get("street")), _text(raw.get("house_number"))) if t]
    return " ".join(teile) or None


def _flaeche(raw: dict) -> float | None:
    """Erste belastbare Flächenangabe – Reihenfolge nach Aussagekraft für Hallen."""
    for key in ("property_space_value", "industrial_area", "usable_floor_space",
                "net_floor_space", "total_floor_space"):
        wert = _zahl(raw.get(key))
        if wert and wert > 0:
            return wert
    return None


def to_card(raw: dict) -> HallCard:
    """Rohobjekt → Karte. Alles, was hier nicht auftaucht, verlässt den Server nicht."""
    titel = _text(raw.get("title")) or _text(raw.get("name")) or f"Objekt {raw.get('id')}"
    baujahr = _zahl(raw.get("construction_year"))
    return HallCard(
        id=int(raw["id"]),
        titel=titel,
        stadt=_text(raw.get("city")),
        plz=_text(raw.get("zip_code")),
        strasse=_strasse(raw),
        lat=_zahl(raw.get("lat")),
        lng=_zahl(raw.get("lng")),
        flaeche=_flaeche(raw),
        hallenhoehe=_zahl(raw.get("hall_height")),
        rampe=_flag(raw.get("ramp")),
        kranbahn=_flag(raw.get("crane_runway")),
        baujahr=int(baujahr) if baujahr else None,
        expose_url=_text(raw.get("public_expose_url")),
        bild_url=_bild_url(raw),
    )


def build_cards(rohdaten: list[dict]) -> list[HallCard]:
    karten: list[HallCard] = []
    for raw in rohdaten:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        if not ist_verfuegbare_halle(raw):
            continue
        try:
            karten.append(to_card(raw))
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("Objekt %s übersprungen: %s", raw.get("id"), e)
    return karten


class _Cache:
    """Bestand im Prozess halten – kein Propstack-Call pro Swipe.

    Der volle Abruf dauert bei ~2200 Objekten rund zwei Minuten (23 Seiten).
    Deshalb blockiert nur der allererste Aufruf: ist der Cache abgelaufen,
    wird der veraltete Stand sofort ausgeliefert und im Hintergrund erneuert."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._karten: list[HallCard] = []
        self._geladen_um: float = 0.0
        self._laedt = False

    def _laden(self) -> list[HallCard]:
        karten = build_cards(propstack.list_units())
        with self._lock:
            self._karten = karten
            self._geladen_um = time.time()
        logger.info("Bestand im Cache: %d vermietbare Hallen", len(karten))
        return karten

    def _hintergrund_erneuern(self) -> None:
        try:
            self._laden()
        except Exception as e:
            logger.error("Hintergrund-Aktualisierung des Bestands fehlgeschlagen: %s", e)
        finally:
            with self._lock:
                self._laedt = False

    def get(self, force: bool = False) -> list[HallCard]:
        with self._lock:
            vorhanden = list(self._karten)
            veraltet = (time.time() - self._geladen_um) >= config.cache_ttl()
            if vorhanden and not veraltet and not force:
                return vorhanden
            starte_hintergrund = bool(vorhanden) and not self._laedt
            if starte_hintergrund:
                self._laedt = True

        if vorhanden:
            if starte_hintergrund:
                threading.Thread(target=self._hintergrund_erneuern, daemon=True).start()
            return vorhanden

        try:
            return self._laden()
        except Exception as e:  # Bestand darf nie die ganze App killen
            logger.error("Bestandsabruf fehlgeschlagen: %s", e)
            raise

    def vorwaermen(self) -> None:
        """Beim Start anstoßen, damit der erste Besucher nicht wartet."""
        threading.Thread(target=self._sicher_laden, daemon=True).start()

    def _sicher_laden(self) -> None:
        try:
            self._laden()
        except Exception as e:
            logger.error("Vorwärmen des Bestands fehlgeschlagen: %s", e)

    def stand(self) -> tuple[int, float]:
        with self._lock:
            return len(self._karten), self._geladen_um


_cache = _Cache()


def cards(force: bool = False) -> list[HallCard]:
    return _cache.get(force=force)


def stand() -> tuple[int, float]:
    return _cache.stand()


def vorwaermen() -> None:
    _cache.vorwaermen()
