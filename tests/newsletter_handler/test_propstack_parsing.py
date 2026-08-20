"""_to_unit muss Propstack-Custom-Field-Objekte {"label":..., "value":...} tolerieren.

Regression zum NO_WRITE-Testlauf 09.07.2026: manche Units liefern title/rented
als {label, value}-Dict statt als Skalar."""
from newsletter_handler.propstack import _to_unit


def test_scalar_fields_plain():
    unit = _to_unit({
        "id": 1, "title": "Halle A", "street": "Musterweg", "house_number": 12,
        "city": "Dortmund", "rented": False, "property_space_value": 6000.0,
    })
    assert unit.title == "Halle A"
    assert unit.house_number == "12"
    assert unit.rented is False


def test_custom_field_dicts_unwrapped():
    unit = _to_unit({
        "id": 2,
        "title": {"label": "Überschrift", "value": "Halle in (HB) Bremerhaven"},
        "rented": {"label": "Vermietet", "value": False},
        "city": {"label": "Stadt", "value": "Bremerhaven"},
        "house_number": {"label": "Nr", "value": 7},
    })
    assert unit.title == "Halle in (HB) Bremerhaven"
    assert unit.rented is False
    assert unit.city == "Bremerhaven"
    assert unit.house_number == "7"


def test_broker_nested_object():
    unit = _to_unit({"id": 3, "broker": {"id": 254958, "name": "Lena Klinnert"}})
    assert unit.broker_id == 254958
    assert unit.broker_name == "Lena Klinnert"
