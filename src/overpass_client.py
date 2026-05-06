from __future__ import annotations

import logging
import os

import httpx

from .geo_utils import polygon_area_sqm, polygon_centroid
from .models import WarehouseCandidate

logger = logging.getLogger(__name__)

OVERPASS_URL_PRIMARY = "https://overpass-api.de/api/interpreter"
OVERPASS_URL_FALLBACK = "https://overpass.kumi.systems/api/interpreter"

# Logistik-relevante Schlüsselwörter im name/operator-Feld, falls building-Tag fehlt.
_LOGISTICS_KEYWORDS = (
    "logistik",
    "logistics",
    "spedition",
    "transport",
    "fracht",
    "freight",
    "kontraktlogistik",
    "warehous",
    "lager",
    "distribution",
    "fulfilment",
    "fulfillment",
    "kühlhaus",
    "kuehlhaus",
    "umschlag",
)


def _build_query(lat: float, lon: float, radius_m: int) -> str:
    return f"""
[out:json][timeout:90];
(
  way(around:{radius_m},{lat},{lon})["building"~"warehouse|industrial"];
  relation(around:{radius_m},{lat},{lon})["building"~"warehouse|industrial"];
);
out body geom tags;
""".strip()


def _post(url: str, query: str) -> dict | None:
    try:
        response = httpx.post(
            url,
            data={"data": query},
            timeout=120.0,
            headers={"User-Agent": "Kromeich-Partner-LogisticsSearch/1.0"},
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.error("Overpass request to %s failed: %s", url, e)
        return None


def query_warehouses(lat: float, lon: float, radius_m: int) -> list[dict]:
    query = _build_query(lat, lon, radius_m)
    logger.info("Querying Overpass: center=(%.4f,%.4f) radius=%dm", lat, lon, radius_m)

    data = _post(OVERPASS_URL_PRIMARY, query)
    if data is None:
        logger.warning("Primary Overpass failed, trying fallback endpoint")
        data = _post(OVERPASS_URL_FALLBACK, query)
    if data is None:
        return []

    elements = data.get("elements") or []
    logger.info("Overpass returned %d raw elements", len(elements))
    return elements


def _is_logistics_candidate(tags: dict) -> bool:
    building = (tags.get("building") or "").lower()
    if building == "warehouse":
        return True
    haystack = " ".join(
        [
            tags.get("name") or "",
            tags.get("operator") or "",
            tags.get("industrial") or "",
            tags.get("amenity") or "",
        ]
    ).lower()
    if any(kw in haystack for kw in _LOGISTICS_KEYWORDS):
        return True
    return False


def _coords_from_geometry(geometry: list[dict]) -> list[tuple[float, float]]:
    return [(pt["lon"], pt["lat"]) for pt in geometry if "lon" in pt and "lat" in pt]


def _coords_from_relation(members: list[dict]) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []
    for m in members:
        if m.get("role") not in (None, "outer", ""):
            continue
        geom = m.get("geometry") or []
        coords.extend(_coords_from_geometry(geom))
    return coords


def parse_candidates(
    elements: list[dict],
    min_area_sqm: float,
    require_logistics_hint: bool = True,
) -> list[WarehouseCandidate]:
    candidates: list[WarehouseCandidate] = []

    for el in elements:
        tags = el.get("tags") or {}

        if require_logistics_hint and not _is_logistics_candidate(tags):
            continue

        if el.get("type") == "way":
            coords = _coords_from_geometry(el.get("geometry") or [])
        elif el.get("type") == "relation":
            coords = _coords_from_relation(el.get("members") or [])
        else:
            continue

        if len(coords) < 3:
            continue

        area = polygon_area_sqm(coords)
        if area < min_area_sqm:
            continue

        lat, lon = polygon_centroid(coords)

        candidate = WarehouseCandidate(
            osm_type=el["type"],
            osm_id=int(el["id"]),
            name=tags.get("name"),
            operator=tags.get("operator"),
            area_sqm=round(area, 1),
            lat=round(lat, 6),
            lon=round(lon, 6),
            street=tags.get("addr:street"),
            house_number=tags.get("addr:housenumber"),
            zip_code=tags.get("addr:postcode"),
            city=tags.get("addr:city"),
            website=tags.get("website") or tags.get("contact:website"),
            phone=tags.get("phone") or tags.get("contact:phone"),
            email=tags.get("email") or tags.get("contact:email"),
            building=tags.get("building"),
            landuse=tags.get("landuse"),
        )
        candidates.append(candidate)

    candidates.sort(key=lambda c: c.area_sqm, reverse=True)
    return candidates
