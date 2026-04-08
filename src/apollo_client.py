from __future__ import annotations

import logging
import os

import httpx

from .models import ContactData, EnrichmentResult

logger = logging.getLogger(__name__)

APOLLO_MATCH_URL = "https://api.apollo.io/v1/people/match"


def enrich_contact(contact: ContactData) -> EnrichmentResult | None:
    api_key = os.environ.get("APOLLO_API_KEY")
    if not api_key:
        logger.warning("APOLLO_API_KEY not set, skipping enrichment")
        return None

    try:
        response = httpx.post(
            APOLLO_MATCH_URL,
            json={"api_key": api_key, "email": contact.email},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.error("Apollo API error for %s: %s", contact.email, e)
        return None

    person = data.get("person")
    if not person:
        logger.info("Apollo: no match for %s", contact.email)
        return None

    org = person.get("organization") or {}
    enriched_fields: list[str] = []

    phone = None
    phone_numbers = person.get("phone_numbers") or []
    if phone_numbers:
        phone = phone_numbers[0].get("sanitized_number") or phone_numbers[0].get("raw_number")
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
    if company and not contact.company:
        result.company = company
        enriched_fields.append("company")
    if position and not contact.position:
        result.position = position
        enriched_fields.append("position")
    if street and not contact.street:
        result.street = street
        enriched_fields.append("street")
    if house_number and not contact.house_number:
        result.house_number = house_number
        enriched_fields.append("house_number")
    if zip_code and not contact.zip_code:
        result.zip_code = zip_code
        enriched_fields.append("zip_code")
    if city and not contact.city:
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
