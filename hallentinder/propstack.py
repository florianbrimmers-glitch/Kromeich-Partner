from __future__ import annotations

import logging
import time
from datetime import date

import httpx

from . import config
from .models import LeadPayload

logger = logging.getLogger(__name__)

PROPSTACK_BASE_URL = "https://api.propstack.de/v1"

MAX_ATTEMPTS = 4
MAX_PAGES = 50


def _request(
    method: str,
    path: str,
    *,
    key: str,
    params: dict | None = None,
    json: dict | None = None,
) -> httpx.Response:
    """Request mit Retry (Backoff 2**attempt) bei 429/5xx/Netzfehlern.

    Andere 4xx werden sofort mit Status+Body geloggt und geraist
    (Muster wie in newsletter_handler/propstack.py)."""
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


def _items(data) -> list[dict]:
    """Propstack antwortet je nach Endpunkt als Liste oder als {"data": [...]}."""
    raw = data if isinstance(data, list) else (data or {}).get("data", [])
    return [item for item in raw if isinstance(item, dict)]


def list_units(per: int = 100) -> list[dict]:
    """GET /units – gesamter Bestand, paginiert. Rohdaten; Filterung/Whitelist in catalog.py."""
    units: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        response = _request(
            "GET", "/units",
            key=config.propstack_key_objekte(),
            params={"expand": 1, "page": page, "per": per},
        )
        batch = _items(response.json())
        units.extend(u for u in batch if u.get("id"))
        if len(batch) < per:
            break
        time.sleep(0.5)
    else:
        logger.warning("Bestandsabruf bei %d Seiten abgebrochen – Bestand evtl. unvollständig", MAX_PAGES)

    logger.info("Propstack-Bestand geladen: %d Objekte", len(units))
    return units


def get_unit(unit_id: int) -> dict | None:
    response = _request(
        "GET", f"/units/{unit_id}",
        key=config.propstack_key_objekte(),
        params={"expand": 1},
    )
    data = response.json()
    return data if isinstance(data, dict) and data.get("id") else None


def find_contact_by_email(email: str) -> int | None:
    """GET /contacts?q=… – Dublettencheck (Muster src/propstack_client.py:44).

    Die Volltextsuche trifft auch Teilstrings, deshalb wird die E-Mail lokal gegengeprüft."""
    response = _request("GET", "/contacts", key=config.propstack_key(), params={"q": email})
    gesucht = email.strip().lower()
    for contact in _items(response.json()):
        kandidat = (contact.get("email") or "").strip().lower()
        if kandidat == gesucht and contact.get("id"):
            return int(contact["id"])
        for eintrag in contact.get("email_addresses") or []:
            if isinstance(eintrag, dict) and (eintrag.get("email") or "").strip().lower() == gesucht:
                return int(contact["id"]) if contact.get("id") else None
    return None


def create_contact(lead: LeadPayload) -> int | None:
    """POST /contacts mit {"client": {...}} (Muster src/propstack_client.py:211)."""
    client_data: dict = {"last_name": lead.nachname.strip()}
    if lead.vorname.strip():
        client_data["first_name"] = lead.vorname.strip()
    if lead.email.strip():
        client_data["email"] = lead.email.strip()
    if lead.telefon.strip():
        client_data["office_phone"] = lead.telefon.strip()
    if lead.firma.strip():
        client_data["company"] = lead.firma.strip()
    client_data["description"] = f"{config.QUELLE} – Selbstauskunft vom {date.today().isoformat()}"

    if config.no_write():
        logger.info("[NO_WRITE] Würde Kontakt anlegen: %s", client_data)
        return None

    response = _request("POST", "/contacts", key=config.propstack_key(), json={"client": client_data})
    contact_id = response.json().get("id")
    logger.info("Kontakt angelegt: %s (id=%s)", lead.nachname, contact_id)
    return int(contact_id) if contact_id else None


def create_deal(client_id: int | None, property_id: int, note: str | None = None) -> int | None:
    """POST /client_properties – verknüpft Interessent und Objekt zu einem Deal.

    Im Repo bisher nur lesend genutzt; das Payload-Schema ist beim ersten
    Schreibtest gegen die Live-API zu verifizieren."""
    deal: dict = {"client_id": client_id, "property_id": property_id}
    if note:
        deal["note"] = note

    if config.no_write():
        vorschau = dict(deal)
        if client_id is None:
            vorschau["client_id"] = "<id des neu anzulegenden Kontakts>"
        logger.info("[NO_WRITE] Würde Deal anlegen: %s", vorschau)
        return None

    if client_id is None:
        raise ValueError("create_deal ohne client_id")

    response = _request(
        "POST", "/client_properties",
        key=config.propstack_key_objekte(),
        json={"client_property": deal},
    )
    deal_id = response.json().get("id")
    logger.info("Deal angelegt: Kontakt %s ↔ Objekt %s (id=%s)", client_id, property_id, deal_id)
    return int(deal_id) if deal_id else None
