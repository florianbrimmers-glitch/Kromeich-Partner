from __future__ import annotations

import logging
import os

import httpx

from . import problems
from .models import ContactData, EnrichmentResult

logger = logging.getLogger(__name__)

# Apollo verlangt den Schlüssel im Header x-api-key (docs.apollo.io/reference/authentication).
# Bis 19.11.2026 stand er im JSON-Body und die Adresse war /v1/people/match: Apollo wies
# jeden Aufruf mit 401 ab, die Anreicherung war still aus.
APOLLO_MATCH_URL = "https://api.apollo.io/api/v1/people/match"


def enrich_contact(contact: ContactData) -> EnrichmentResult | None:
    if not contact.email:
        logger.info("No email for contact, skipping Apollo enrichment")
        return None

    api_key = os.environ.get("APOLLO_API_KEY")
    if not api_key:
        logger.warning("APOLLO_API_KEY not set, skipping enrichment")
        return None

    try:
        response = httpx.post(
            APOLLO_MATCH_URL,
            json={"email": contact.email},
            headers={
                "x-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Cache-Control": "no-cache",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as e:
        # Ohne Adresse im Text: gleiche Ursache soll in der Zusammenfassung gezählt werden
        problems.melde("Apollo-Anreicherung fehlgeschlagen", f"HTTP {e.response.status_code}")
        return None
    except (httpx.HTTPError, ValueError) as e:
        problems.melde("Apollo-Anreicherung fehlgeschlagen", type(e).__name__)
        return None

    person = data.get("person")
    if not person:
        logger.info("Apollo: no match for %s", contact.email)
        return None

    org = person.get("organization") or {}
    enriched_fields: list[str] = []

    phone = None
    mobile = None
    for entry in person.get("phone_numbers") or []:
        number = entry.get("sanitized_number") or entry.get("raw_number")
        if not number:
            continue
        if "mobile" in (entry.get("type") or "").lower():
            mobile = mobile or number
        else:
            phone = phone or number
    if not phone:
        org_phone = org.get("phone")
        if org_phone:
            phone = org_phone

    company = org.get("name")
    position = person.get("title")
    street = org.get("street_address")
    city = org.get("city")
    zip_code = org.get("postal_code")

    house_number = None
    if street:
        parts = street.rsplit(" ", 1)
        if len(parts) == 2 and any(c.isdigit() for c in parts[1]):
            street = parts[0]
            house_number = parts[1]

    result = EnrichmentResult()

    if phone and not contact.phone:
        result.phone = phone
        enriched_fields.append("phone")
    if mobile and not contact.mobile:
        result.mobile = mobile
        enriched_fields.append("mobile")
    if company and not contact.company:
        result.company = company
        enriched_fields.append("company")
    if position and not contact.position:
        result.position = position
        enriched_fields.append("position")
    # Adresse nur als Ganzes übernehmen – und nur, wenn die Signatur gar keine nennt.
    # Feldweises Auffüllen mischt zwei Orte: Signatur "Hamburg" + Apollo-Hauptsitz
    # ergab "Leopoldstraße 4, 80802 Hamburg".
    if not (contact.street or contact.zip_code or contact.city):
        if street:
            result.street = street
            enriched_fields.append("street")
        if street and house_number:
            result.house_number = house_number
            enriched_fields.append("house_number")
        if zip_code:
            result.zip_code = zip_code
            enriched_fields.append("zip_code")
        if city:
            result.city = city
            enriched_fields.append("city")

    result.enriched_fields = enriched_fields

    if enriched_fields:
        logger.info("Apollo enriched %s: %s", contact.email, enriched_fields)
    else:
        logger.info("Apollo matched %s but no new fields to enrich", contact.email)

    return result if enriched_fields else None


def apply_enrichment(contact: ContactData, enrichment: EnrichmentResult) -> ContactData:
    if enrichment.phone:
        contact.phone = enrichment.phone
    if enrichment.mobile:
        contact.mobile = enrichment.mobile
    if enrichment.company:
        contact.company = enrichment.company
    if enrichment.position:
        contact.position = enrichment.position
    if enrichment.street:
        contact.street = enrichment.street
    if enrichment.house_number:
        contact.house_number = enrichment.house_number
    if enrichment.zip_code:
        contact.zip_code = enrichment.zip_code
    if enrichment.city:
        contact.city = enrichment.city
    return contact
