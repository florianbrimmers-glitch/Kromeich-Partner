from __future__ import annotations

import logging
import os
from datetime import date

import httpx

from .models import ContactData

logger = logging.getLogger(__name__)

PROPSTACK_BASE_URL = "https://api.propstack.de/v1"


def _api_key() -> str:
    return os.environ["PROPSTACK_API_KEY"]


def check_duplicate(email: str) -> bool:
    try:
        response = httpx.get(
            f"{PROPSTACK_BASE_URL}/contacts",
            params={"api_key": _api_key(), "email": email},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        exists = isinstance(data, list) and len(data) > 0
        if exists:
            logger.info("Propstack duplicate found for %s", email)
        return exists
    except (httpx.HTTPError, ValueError) as e:
        logger.error("Propstack duplicate check failed for %s: %s", email, e)
        return False


def create_contact(contact: ContactData, group_ids: list[str] | None = None) -> dict | None:
    client_data: dict = {}

    if contact.first_name:
        client_data["first_name"] = contact.first_name
    if contact.last_name:
        client_data["last_name"] = contact.last_name

    client_data["email"] = contact.email

    if contact.phone:
        client_data["office_phone"] = contact.phone
    if contact.company:
        client_data["company"] = contact.company
    if contact.position:
        client_data["position"] = contact.position
    if contact.street:
        client_data["office_street"] = contact.street
    if contact.house_number:
        client_data["office_house_number"] = contact.house_number
    if contact.zip_code:
        client_data["office_zip_code"] = contact.zip_code
    if contact.city:
        client_data["office_city"] = contact.city
    if contact.country:
        client_data["office_country"] = contact.country

    if group_ids:
        client_data["mailchimp_interest_ids"] = group_ids

    client_data["description"] = f"KI-Scan (GitHub Actions) vom {date.today().isoformat()} aus Email-Signatur"

    payload = {"client": client_data}

    try:
        response = httpx.post(
            f"{PROPSTACK_BASE_URL}/contacts",
            params={"api_key": _api_key()},
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=30.0,
        )
        response.raise_for_status()
        result = response.json()
        name = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
        logger.info("Created contact in Propstack: %s (%s)", name, contact.email)
        return result
    except httpx.HTTPStatusError as e:
        logger.error(
            "Propstack create contact failed for %s: %s - %s",
            contact.email,
            e.response.status_code,
            e.response.text,
        )
        return None
    except (httpx.HTTPError, ValueError) as e:
        logger.error("Propstack create contact failed for %s: %s", contact.email, e)
        return None
