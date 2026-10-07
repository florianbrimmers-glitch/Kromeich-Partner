from __future__ import annotations

import logging
import time

import httpx
from pydantic import BaseModel

from . import config
from .models import Link

logger = logging.getLogger(__name__)

PROPSTACK_V1 = "https://api.propstack.de/v1"
PROPSTACK_V2 = "https://api.propstack.de/v2"

MAX_ATTEMPTS = 4


class TaskPayload(BaseModel):
    title: str
    body: str  # HTML
    broker_id: int | None = None
    is_reminder: bool = False
    due_date: str | None = None  # ISO
    client_ids: list[int] | None = None


def _request(method: str, url: str, *, key: str, params: dict | None = None, json: dict | None = None) -> httpx.Response:
    """Request mit Retry (Backoff 2**attempt) bei 429/5xx/Netzfehlern.

    Andere 4xx werden sofort mit Status+Body geloggt und geraist."""
    headers = {"X-API-KEY": key, "Content-Type": "application/json", "Accept": "application/json"}
    last_error: Exception | None = None

    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            time.sleep(2**attempt)
        try:
            response = httpx.request(method, url, headers=headers, params=params, json=json, timeout=30.0)
            if response.status_code == 429 or response.status_code >= 500:
                logger.warning("Propstack %s %s: HTTP %s (Versuch %d/%d)",
                               method, url, response.status_code, attempt + 1, MAX_ATTEMPTS)
                last_error = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}", request=response.request, response=response
                )
                continue
            if response.status_code >= 400:
                logger.error("Propstack %s %s fehlgeschlagen: HTTP %s – %s",
                             method, url, response.status_code, response.text)
                response.raise_for_status()
            return response
        except httpx.HTTPStatusError:
            raise
        except httpx.HTTPError as e:
            logger.warning("Propstack %s %s: %s (Versuch %d/%d)", method, url, e, attempt + 1, MAX_ATTEMPTS)
            last_error = e

    raise last_error if last_error else RuntimeError(f"Propstack {method} {url} fehlgeschlagen")


def _liste(data) -> list[dict]:
    raw = data if isinstance(data, list) else (data or {}).get("data", [])
    return [d for d in raw if isinstance(d, dict)]


def search_contacts(q: str) -> list[dict]:
    """GET /v1/contacts?q= – Volltextsuche über Personen und Firmen.

    Achtung: der Parameter heißt 'per' (nicht 'per_page'), sonst kommen nur 20 Treffer."""
    response = _request("GET", f"{PROPSTACK_V1}/contacts", key=config.propstack_key_v1(),
                        params={"q": q, "per": 50})
    treffer = _liste(response.json())
    logger.info("Propstack-Suche '%s': %d Treffer", q, len(treffer))
    return treffer


def get_contact(contact_id: int) -> dict:
    return _request("GET", f"{PROPSTACK_V1}/contacts/{contact_id}", key=config.propstack_key_v1()).json()


def get_company_links(person_id: int) -> list[Link]:
    """Firmen-Verknüpfungen einer Person (V2). Liefert standardmäßig nur 10 je Seite."""
    response = _request("GET", f"{PROPSTACK_V2}/relationships", key=config.propstack_key_v2(),
                        params={"client_id": person_id, "per": 100})
    links: list[Link] = []
    for rel in _liste(response.json()):
        if rel.get("client_id") != person_id or not rel.get("related_client_id"):
            continue
        firma = get_contact(rel["related_client_id"])
        if not firma.get("is_company"):
            continue  # Personen-Beziehungen (z.B. Assistenz) nicht anfassen
        links.append(Link(
            relationship_id=rel["id"],
            company_id=rel["related_client_id"],
            company_name=firma.get("company") or firma.get("name") or "",
        ))
    return links


def update_contact(contact_id: int, fields: dict) -> None:
    if config.no_write():
        logger.info("[NO_WRITE] Würde Kontakt %s ändern: %s", contact_id, fields)
        return
    _request("PUT", f"{PROPSTACK_V1}/contacts/{contact_id}", key=config.propstack_key_v1(),
             json={"client": fields})
    logger.info("Kontakt %s geändert: %s", contact_id, sorted(fields))


def link_company(person_id: int, company_id: int) -> None:
    """Verknüpfung 'Firma' anlegen (sichtbar unter 'Verknüpfte Kontakte')."""
    if config.no_write():
        logger.info("[NO_WRITE] Würde %s mit Firma %s verknüpfen", person_id, company_id)
        return
    response = httpx.post(
        f"{PROPSTACK_V2}/relationships",
        headers={"X-API-KEY": config.propstack_key_v2(), "Content-Type": "application/json"},
        json={"internal_name": "associate", "name": "Firma",
              "client_id": person_id, "related_client_id": company_id},
        timeout=30.0,
    )
    if response.status_code not in (200, 201, 204, 422):  # 422 = besteht bereits
        logger.error("Verknüpfung %s -> %s fehlgeschlagen: HTTP %s – %s",
                     person_id, company_id, response.status_code, response.text)
        response.raise_for_status()


def unlink(relationship_id: int) -> None:
    """Verknüpfung entfernen. Propstack führt jede Verknüpfung als zwei Zeilen
    (benannt + Gegenrichtung); das Löschen einer Zeile entfernt beide."""
    if config.no_write():
        logger.info("[NO_WRITE] Würde Verknüpfung %s entfernen", relationship_id)
        return
    _request("DELETE", f"{PROPSTACK_V2}/relationships/{relationship_id}", key=config.propstack_key_v2())


def get_company_name(company_id: int) -> str | None:
    data = _request("GET", f"{PROPSTACK_V1}/contacts/{company_id}", key=config.propstack_key_v1()).json()
    return data.get("company") or data.get("name")


def rename_company(company_id: int, name: str) -> None:
    """Firmennamen setzen (V2: company-Feld, last_name leer – sonst "X (X)")."""
    if config.no_write():
        logger.info("[NO_WRITE] Würde Firma %s in '%s' umbenennen", company_id, name)
        return
    _request("PUT", f"{PROPSTACK_V2}/clients/{company_id}", key=config.propstack_key_v2(),
             json={"company": name, "last_name": None})
    logger.warning("Firma %s auf '%s' zurückbenannt", company_id, name)


def create_task(payload: TaskPayload) -> int | None:
    """POST /v1/tasks – Notiz (is_reminder=false) oder Review-Aufgabe (is_reminder=true)."""
    task = payload.model_dump(exclude_none=True)
    if config.no_write():
        logger.info("[NO_WRITE] Würde Task anlegen: %s", task)
        return None
    response = _request("POST", f"{PROPSTACK_V1}/tasks", key=config.propstack_key_v1(), json={"task": task})
    task_id = response.json().get("id")
    logger.info("Task angelegt: '%s' (id=%s)", payload.title, task_id)
    return task_id
