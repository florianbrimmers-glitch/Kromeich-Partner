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


def _status_id(raw: dict) -> int | None:
    """Objekt-Status der Einheit. Die Suche liefert ihn als property_status {id, name, …}
    (geprüft am 19.11.2026); fehlt er, hat die Einheit keinen Status."""
    status = raw.get("property_status")
    if isinstance(status, dict) and isinstance(status.get("id"), int):
        return status["id"]
    status_id = _scalar(raw.get("property_status_id"))
    return status_id if isinstance(status_id, int) else None


def _to_unit(raw: dict) -> Unit:
    broker = raw.get("broker") or {}
    house_number = _scalar(raw.get("house_number"))
    archived = _scalar(raw.get("archived"))
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
        status_id=_status_id(raw),
        archived=archived if isinstance(archived, bool) else None,
    )


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


def fetch_open_review_units(broker_id: int, titel_praefix: str) -> dict[int, int]:
    """Einheiten, zu denen beim Review-Sitz schon eine offene Review-Aufgabe liegt.

    GET /activities?item_type=reminder&broker_id=… – jede Zeile trägt title, done und
    property_ids (geprüft am 19.11.2026; rund 560 Aufgaben = 3 Seiten à 200).
    activatable_id ist die Task-ID, id die der Aktivität. Rückgabe: Unit-ID → Task-ID
    der ältesten offenen Aufgabe. Fehler werden geworfen – der Aufrufer entscheidet,
    wie er ohne diese Liste weitermacht."""
    per_page = 200
    aelteste: dict[int, tuple[str, int]] = {}  # Unit-ID -> (angelegt, Task-ID)
    page = 1
    while True:
        response = _request(
            "GET", "/activities",
            key=config.propstack_key_tasks(),
            params={
                "item_type": "reminder", "broker_id": broker_id,
                "sort_by": "updated_at", "order": "desc",
                "per": per_page, "page": page,
            },
        )
        data = response.json()
        rows = data if isinstance(data, list) else (data or {}).get("data", [])
        for row in rows:
            if not isinstance(row, dict) or _scalar(row.get("done")):
                continue
            title = _scalar(row.get("title")) or ""
            if not isinstance(title, str) or not title.startswith(titel_praefix):
                continue
            task_id = row.get("activatable_id") or row.get("id")
            angelegt = str(row.get("original_created_at") or "")
            for unit_id in row.get("property_ids") or []:
                if not isinstance(unit_id, int):
                    continue
                bisher = aelteste.get(unit_id)
                if bisher is None or angelegt < bisher[0]:
                    aelteste[unit_id] = (angelegt, task_id)
        if len(rows) < per_page:
            break
        page += 1
        time.sleep(1)
    logger.info("Offene Review-Aufgaben bei %s: %d Einheiten abgedeckt", broker_id, len(aelteste))
    return {unit_id: task_id for unit_id, (_, task_id) in aelteste.items()}


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
