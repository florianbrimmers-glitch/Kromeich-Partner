from __future__ import annotations

import logging
import re
import time

import httpx

from . import config

logger = logging.getLogger(__name__)


def _request(path: str, params: dict) -> httpx.Response:
    """GET mit Retry (Backoff 2**attempt) bei 429/5xx/Netzfehlern.

    Bewusst dieselbe Fehlerbehandlung wie objekte_handler/propstack.py – der
    Handler ist eigenständig, das Verhalten gegenüber Propstack aber gleich.
    """
    headers = {"X-API-KEY": config.propstack_key(), "Accept": "application/json"}
    last_error: Exception | None = None

    for attempt in range(config.PROPSTACK_MAX_ATTEMPTS):
        if attempt:
            time.sleep(2**attempt)
        try:
            response = httpx.get(
                f"{config.PROPSTACK_BASE_URL}{path}",
                headers=headers, params=params, timeout=60.0,
            )
            if response.status_code == 429 or response.status_code >= 500:
                logger.warning(
                    "Propstack GET %s: HTTP %s (Versuch %d/%d)",
                    path, response.status_code, attempt + 1, config.PROPSTACK_MAX_ATTEMPTS,
                )
                last_error = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}", request=response.request, response=response
                )
                continue
            if response.status_code >= 400:
                logger.error(
                    "Propstack GET %s fehlgeschlagen: HTTP %s – %s",
                    path, response.status_code, response.text[:500],
                )
                response.raise_for_status()
            return response
        except httpx.HTTPStatusError:
            raise
        except httpx.HTTPError as e:
            logger.warning(
                "Propstack GET %s: %s (Versuch %d/%d)",
                path, e, attempt + 1, config.PROPSTACK_MAX_ATTEMPTS,
            )
            last_error = e

    raise last_error if last_error else RuntimeError(f"Propstack GET {path} fehlgeschlagen")


def _entpacke(data) -> list[dict]:
    """Propstack antwortet je Endpoint als Liste oder als {"data": [...]}."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("data", "units", "properties"):
            werte = data.get(key)
            if isinstance(werte, list):
                return [x for x in werte if isinstance(x, dict)]
    return []


def fetch_units(nur_miete: bool = True) -> list[dict]:
    """Alle Einheiten paginiert laden.

    Sendet `per_page` UND `per`: der Listen-Endpoint respektiert `per_page`
    (so macht es der propstack-pipeline-report-Skill), während der bestehende
    objekte_handler `per` schickt und dadurch vermutlich immer nur die ersten
    20 Einheiten sah – der offene Nebenbefund aus der Asana-Aufgabe.
    """
    units: list[dict] = []
    gesehen: set[int] = set()

    for page in range(1, config.PROPSTACK_MAX_PAGES + 1):
        params = {
            "page": page,
            "per_page": config.PROPSTACK_PER_PAGE,
            "per": config.PROPSTACK_PER_PAGE,
            "expand": 1,
        }
        if nur_miete:
            params["marketing_type"] = "RENT"

        seite = _entpacke(_request("/units", params).json())
        if not seite:
            break

        neu = 0
        for unit in seite:
            uid = unit.get("id")
            if uid is None or uid in gesehen:
                continue
            gesehen.add(uid)
            units.append(unit)
            neu += 1

        logger.info("Propstack /units Seite %d: %d Einträge (%d neu)", page, len(seite), neu)

        # Keine neuen IDs = der Endpoint ignoriert `page` und liefert immer
        # dieselbe Seite. Weiterlaufen wäre eine Endlosschleife.
        if neu == 0:
            logger.warning(
                "Seite %d brachte keine neuen IDs – Paginierung endet hier "
                "(Endpoint ignoriert vermutlich 'page')", page,
            )
            break
        if len(seite) < config.PROPSTACK_PER_PAGE:
            break
    else:
        logger.warning(
            "MAX_PAGES=%d erreicht – möglicherweise nicht alle Einheiten geladen",
            config.PROPSTACK_MAX_PAGES,
        )

    logger.info("Propstack: %d Einheiten geladen", len(units))
    return units


def skalar(value):
    """Custom-Field-Objekte {"label":…, "value":…} auf den Wert reduzieren."""
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


_ZAHL_RE = re.compile(r"-?\d[\d.,\s ]*\d|-?\d")


def zu_zahl(value) -> float | None:
    """'4,58 €/m²' -> 4.58 · '22.900,00 €' -> 22900.0 · 'auf Anfrage' -> None.

    Mieten stehen in Custom Fields häufig als Text mit Einheit. Deutsches und
    englisches Dezimalformat müssen beide funktionieren, weil Propstack je
    nach Feld das eine oder das andere liefert.
    """
    value = skalar(value)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    treffer = _ZAHL_RE.search(text)
    if not treffer:
        return None
    zahl = re.sub(r"[\s ]", "", treffer.group(0))

    if "," in zahl:
        # Deutsches Format: Punkt ist Tausender-, Komma Dezimaltrenner
        zahl = zahl.replace(".", "").replace(",", ".")
    elif "." in zahl:
        # Nur Punkte: Tausendertrennung nur annehmen, wenn ALLE Gruppen nach
        # dem ersten Punkt dreistellig sind ("1.234.567", "4.500"). Sonst ist
        # es ein Dezimalpunkt ("4.58") – der früher als 4 gelesen wurde.
        teile = zahl.lstrip("-").split(".")
        if len(teile[0]) <= 3 and all(len(teil) == 3 for teil in teile[1:]):
            zahl = zahl.replace(".", "")
    try:
        return float(zahl)
    except ValueError:
        return None


def custom_fields(unit: dict) -> dict:
    felder = unit.get("custom_fields")
    return felder if isinstance(felder, dict) else {}


def hole_betrag(unit: dict, felder: tuple[str, ...]) -> tuple[float | None, str | None]:
    """Ersten gefüllten Betrag aus einer EXPLIZITEN Feldliste.

    Bewusst keine Namens-Heuristik: ein Teilstring-Match auf "miete" würde
    `stellplatzmiete` (20-70 € pro Stellplatz) mitnehmen und den €/m²-Median
    zerstören. Gesucht wird nur, was in config.FLAECHENARTEN steht.

    Rückgabe: (Wert, Feldname) – der Feldname wandert in den Datensatz, damit
    nachvollziehbar bleibt, WOHER eine Miete kommt.
    """
    cf = custom_fields(unit)
    for feld in felder:
        # Custom Fields zuerst: dort pflegt K&P die Mieten.
        wert = zu_zahl(cf.get(feld)) if feld in cf else zu_zahl(unit.get(feld))
        if wert is not None and wert > 0:
            quelle = f"custom_fields.{feld}" if feld in cf else feld
            return wert, quelle
    return None, None


def hole_flaeche(unit: dict, felder: tuple[str, ...] = ()) -> tuple[float | None, str | None]:
    """Fläche der Flächenart, sonst die Gesamtfläche der Einheit.

    Die Fläche dient nur der Einordnung (Größenklasse) – die Mieten stehen
    bereits als €/m² und werden NICHT über die Fläche gerechnet.
    """
    wert, feld = hole_betrag(unit, felder)
    if wert is not None:
        return wert, feld
    for feld in config.FLAECHE_FELDER:
        wert = zu_zahl(unit.get(feld))
        if wert is not None and wert > 0:
            return wert, feld
    return None, None


def ist_mietobjekt(unit: dict) -> bool:
    if skalar(unit.get("for_rent")) is True:
        return True
    marketing = str(skalar(unit.get("marketing_type")) or "").upper()
    return marketing in config.MARKETING_TYPES_MIETE


def preis_auf_anfrage(unit: dict) -> bool:
    """`price_on_inquiry` – im GET verschachtelt unter `furnishings`.

    Der Exposé-Workflow setzt das Flag bewusst, wenn die Miete unbekannt ist;
    solche Einheiten sind also legitim ohne Preis und kein Datenfehler.
    """
    if skalar(unit.get("price_on_inquiry")) is True:
        return True
    moebel = unit.get("furnishings")
    if isinstance(moebel, dict):
        return skalar(moebel.get("price_on_inquiry")) is True
    return False
