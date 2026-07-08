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


def _to_unit(raw: dict) -> Unit:
    broker = raw.get("broker") or {}
    return Unit(
        id=raw["id"],
        name=raw.get("name"),
        title=raw.get("title"),
        street=raw.get("street"),
        house_number=str(raw["house_number"]) if raw.get("house_number") is not None else None,
        zip_code=raw.get("zip_code"),
        city=raw.get("city"),
        property_space_value=raw.get("property_space_value"),
        broker_id=broker.get("id") if isinstance(broker, dict) else None,
        broker_name=broker.get("name") if isinstance(broker, dict) else None,
        rented=raw.get("rented"),
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
