"""Propstack-Rohobjekte, wie die API sie liefert – inkl. Custom-Field-Objekten."""
from __future__ import annotations


def unit(**overrides) -> dict:
    basis = {
        "id": 1000,
        "name": "Musterhalle",
        "title": "Logistikhalle mit Rampe",
        "street": "Musterstraße",
        "house_number": "12",
        "zip_code": "49076",
        "city": "Osnabrück",
        "lat": 52.28,
        "lng": 8.05,
        "property_space_value": 5000,
        "marketing_type": "RENT",
        "rs_category": "HALL",
        "rs_type": "INDUSTRY",
        "object_type": "COMMERCIAL",
        "ramp": False,
        "crane_runway": False,
        "hall_height": None,
        "rented": False,
        "broker": {"id": 254958, "name": "Oguzhan"},
        "public_expose_url": "https://expose.example/1000",
    }
    basis.update(overrides)
    return basis


# Bestand mit realistischer Streuung: Osnabrück, Münster, Hamburg, München
BESTAND = [
    unit(id=1, city="Osnabrück", zip_code="49076", lat=52.28, lng=8.05, property_space_value=5000),
    unit(id=2, city="Osnabrück", zip_code="49084", lat=52.26, lng=8.09, property_space_value=1200),
    unit(id=3, city="Münster", zip_code="48155", lat=51.96, lng=7.63, property_space_value=9000),
    unit(id=4, city="Hamburg", zip_code="20537", lat=53.55, lng=9.99, property_space_value=4000),
    unit(id=5, city="München", zip_code="80939", lat=48.14, lng=11.58, property_space_value=6000),
]
