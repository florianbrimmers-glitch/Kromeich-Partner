from __future__ import annotations

import logging
import time

import httpx
from pydantic import BaseModel

from . import config
from .models import Unit

logger = logging.getLogger(__name__)

PROPSTACK_BASE_URL = "https://api.propstack.de/v1"

MAX_ATTEMPTS = 4


class TaskPayload(BaseModel):
    title: str
    body: str  # HTML
    broker_id: int | None = None
    is_reminder: bool = False
    due_date: str | None = None  # ISO
    client_ids: list[int] | None = None
    property_ids: list[int] | None = None
    reservation_reason_id: int | None = None


def _request(method: str, path: str, *, key: str, params: dict | None = None, json: dict | None = None) -> httpx.Response:
    """Request mit Retry (Backoff 2**attempt) bei 429/5xx/Netzfehlern.

    Andere 4xx werden sofort mit Status+Body geloggt und geraist."""
    headers = {"X-API-KEY": key, "Content-Type": "application/json", "Accept": "application/json"}
    last_error: Exception | None = None

    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            time.sleep(2**attempt)
        try:
            response = httpx.request(
                method,
                f"{PROPSTACK_BASE_URL}{path}",
                headers=headers,
                params=params,
                json=json,
                timeout=30.0,
            )
            if response.status_code == 429 or response.status_code >= 500:
                logger.warning(
                    "Propstack %s %s: HTTP %s (Versuch %d/%d)",
                    method, path, response.status_code, attempt + 1, MAX_ATTEMPTS,
                )
                last_error = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}", request=response.request, response=response
                )
                continue
            if response.status_code >= 400:
                logger.error(
                    "Propstack %s %s fehlgeschlagen: HTTP %s – %s",
                    method, path, response.status_code, response.text,
                )
                response.raise_for_status()
            return response
        except httpx.HTTPStatusError:
            raise
        except httpx.HTTPError as e:
            logger.warning("Propstack %s %s: %s (Versuch %d/%d)", method, path, e, attempt + 1, MAX_ATTEMPTS)
            last_error = e

    raise last_error if last_error else RuntimeError(f"Propstack {method} {path} fehlgeschlagen")


def _scalar(value):
    """Propstack liefert manche Felder als Custom-Field-Objekt {"label":..., "value":...}.
    Diese auf den reinen Wert reduzieren; Skalare unverändert durchreichen."""
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _custom_fields(raw: dict) -> dict:
    """Custom Fields aus `expand=1` einsammeln.

    Der Kanal liefert sie je nach Endpoint als Dict (name -> Wert) oder als
    Liste von {"name":..., "value":...}. Beide Formen kommen vor, deshalb hier
    auf eine reduziert."""
    cf = raw.get("custom_fields")
    if isinstance(cf, dict):
        return {k: _scalar(v) for k, v in cf.items()}
    if isinstance(cf, list):
        return {
            entry["name"]: _scalar(entry.get("value"))
            for entry in cf
            if isinstance(entry, dict) and entry.get("name")
        }
    return {}


def _to_unit(raw: dict) -> Unit:
    broker = raw.get("broker") or {}
    status = raw.get("status") or {}
    cf = _custom_fields(raw)
    house_number = _scalar(raw.get("house_number"))
    return Unit(
        id=raw["id"],
        name=_scalar(raw.get("name")),
        title=_scalar(raw.get("title")),
        street=_scalar(raw.get("street")),
        house_number=str(house_number) if house_number is not None else None,
        zip_code=_scalar(raw.get("zip_code")),
        city=_scalar(raw.get("city")),
        property_space_value=_scalar(raw.get("property_space_value")),
        broker_id=broker.get("id") if isinstance(broker, dict) else None,
        broker_name=broker.get("name") if isinstance(broker, dict) else None,
        rented=_scalar(raw.get("rented")),
        project_id=_scalar(raw.get("project_id")),
        # Ab hier die Felder, die eine Entscheidung überhaupt erst tragen. Ohne
        # sie sieht ein Matcher nur Straße + Stadt und kann einen leeren
        # Datensatz nicht von einem echten unterscheiden (Fall Mackenstein 48).
        status_id=status.get("id") if isinstance(status, dict) else None,
        status_name=status.get("name") if isinstance(status, dict) else None,
        free_from=_scalar(raw.get("free_from")),
        hall_area=cf.get("lagerflache"),
        rs_type=_scalar(raw.get("rs_type")),
    )


def search_contacts(q: str) -> list[dict]:
    """GET /contacts?q=... – Volltextsuche über Kontakte.

    Rohdicts, weil hier nur id/name/company/is_company gebraucht werden und
    ein eigenes Modell keinen Mehrwert brächte."""
    response = _request(
        "GET", "/contacts",
        key=config.propstack_key_objekte(),
        params={"q": q, "per": 100},
    )
    data = response.json()
    raw = data if isinstance(data, list) else data.get("data", [])
    contacts = [c for c in raw if isinstance(c, dict) and c.get("id")]
    logger.info("Kontaktsuche '%s': %d Treffer", q, len(contacts))
    return contacts


_relationships_cache: list[dict] | None = None


def all_relationships(*, force: bool = False) -> list[dict]:
    """GET /relationships – vollständig paginiert.

    ⚠️ Der Endpoint ignoriert seine Filterparameter (`project_id`,
    `property_id`, `client_id`): wer filtert, bekommt trotzdem alles. Deshalb
    einmal komplett holen und clientseitig filtern.

    Das Ergebnis wird für die Laufzeit des Prozesses gecacht – ein Lauf
    verarbeitet mehrere Nachrichten und würde die Liste sonst je Nachricht neu
    paginieren."""
    global _relationships_cache
    if _relationships_cache is not None and not force:
        return _relationships_cache

    alle: list[dict] = []
    page = 1
    while True:
        response = _request(
            "GET", "/relationships",
            key=config.propstack_key_objekte(),
            params={"page": page, "per": 100},
        )
        data = response.json()
        raw = data if isinstance(data, list) else data.get("data", [])
        if not raw:
            break
        alle.extend(r for r in raw if isinstance(r, dict))
        if len(raw) < 100:
            break
        page += 1
        time.sleep(1)

    logger.info("Relationships geladen: %d", len(alle))
    _relationships_cache = alle
    return alle


def units_by_ids(unit_ids: list[int]) -> list[Unit]:
    """GET /units?property_ids[]=... – mehrere Einheiten in einem Call.

    `expand=1` ist Pflicht: ohne kommt `rs_type` als null und die Custom Fields
    fehlen ganz."""
    if not unit_ids:
        return []

    units: list[Unit] = []
    # 100 pro Call, sonst schneidet die Seitengröße das Ergebnis ab.
    for start in range(0, len(unit_ids), 100):
        batch = unit_ids[start : start + 100]
        response = _request(
            "GET", "/units",
            key=config.propstack_key_objekte(),
            params=[("expand", 1), ("per", 100), *(("property_ids[]", i) for i in batch)],
        )
        data = response.json()
        raw = data if isinstance(data, list) else data.get("data", [])
        units.extend(_to_unit(u) for u in raw if isinstance(u, dict) and u.get("id"))
        if start + 100 < len(unit_ids):
            time.sleep(1)

    logger.info("%d Einheiten per ID geladen (%d angefragt)", len(units), len(unit_ids))
    return units


def search_units(q: str) -> list[Unit]:
    """GET /units?q=... – Volltextsuche, Ergebnis muss lokal nachgefiltert werden."""
    response = _request(
        "GET", "/units",
        key=config.propstack_key_objekte(),
        params={"q": q, "expand": 1, "per": 100},
    )
    data = response.json()
    raw_units = data if isinstance(data, list) else data.get("data", [])
    units = [_to_unit(u) for u in raw_units if isinstance(u, dict) and u.get("id")]
    logger.info("Propstack-Suche '%s': %d Treffer", q, len(units))
    return units


def set_rented(unit_id: int) -> bool:
    """PUT /units/:id – nur das rented-Flag, der Status-Katalog bleibt unberührt."""
    if config.no_write():
        logger.info("[NO_WRITE] Würde Unit %s auf rented=true setzen", unit_id)
        return True
    _request(
        "PUT", f"/units/{unit_id}",
        key=config.propstack_key_objekte(),
        json={"property": {"rented": True}},
    )
    logger.info("Unit %s auf rented=true gesetzt", unit_id)
    return True


def get_open_deals(property_id: int) -> list[dict]:
    """GET /client_properties?property_id=... – offene Deals einer Unit.

    Der Serverfilter ist unzuverlässig: property_id im Ergebnis client-seitig
    gegenprüfen; bereits verlorene/gewonnene Deals ausfiltern."""
    deals: list[dict] = []
    page = 1
    while True:
        response = _request(
            "GET", "/client_properties",
            key=config.propstack_key_objekte(),
            params={"property_id": property_id, "page": page, "per": 100},
        )
        data = response.json()
        raw = data if isinstance(data, list) else data.get("data", [])
        if not raw:
            break
        deals.extend(d for d in raw if isinstance(d, dict))
        if len(raw) < 100:
            break
        page += 1
        time.sleep(1)

    open_deals = [
        d for d in deals
        if d.get("property_id") == property_id and d.get("category") not in ("lost", "won")
    ]
    logger.info("Unit %s: %d Deals gefunden, %d offen", property_id, len(deals), len(open_deals))
    return open_deals


def create_task(payload: TaskPayload) -> int | None:
    """POST /tasks – Aufgabe/Notiz/Absage (reservation_reason_id macht sie zur Absage)."""
    task = payload.model_dump(exclude_none=True)
    if config.no_write():
        logger.info("[NO_WRITE] Würde Task anlegen: %s", task)
        return None
    response = _request(
        "POST", "/tasks",
        key=config.propstack_key_tasks(),
        json={"task": task},
    )
    task_id = response.json().get("id")
    logger.info("Task angelegt: '%s' (id=%s)", payload.title, task_id)
    return task_id
