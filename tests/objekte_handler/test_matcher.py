import pytest

from objekte_handler import matcher
from objekte_handler.matcher import (
    filter_by_address,
    find_unit,
    normalize_street,
    pick_by_size_hint,
)
from objekte_handler.models import Classification, MatchStatus, MessageType, Unit

from .fixtures import HAMBURGRING_UNITS, VIERSEN_UNITS


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hamburgring", "hamburgring"),
        ("Hauptstr.", "hauptstraße"),
        ("Musterstrasse", "musterstraße"),
        ("  Industrie-Ring  ", "industrie ring"),
        ("Hauptstraße", "hauptstraße"),
    ],
)
def test_normalize_street(raw, expected):
    assert normalize_street(raw) == expected


def _cls(**kwargs) -> Classification:
    defaults = {"typ": MessageType.STATUS_ANWEISUNG, "aktion": "vermietet", "confidence": 0.95}
    defaults.update(kwargs)
    return Classification(**defaults)


def test_hamburgring_hausnummer_filtert_altdatensaetze():
    cls = _cls(strasse="Hamburgring", hausnummer="48", stadt="Mönchengladbach")
    result = filter_by_address(HAMBURGRING_UNITS, cls)
    assert {u.id for u in result} == {5263216, 5263218}


def test_hamburgring_ohne_hausnummer_bleibt_mehrdeutig():
    cls = _cls(strasse="Hamburgring", stadt="Mönchengladbach")
    result = filter_by_address(HAMBURGRING_UNITS, cls)
    assert len(result) == 5


def test_hausnummer_normalisierung():
    cls = _cls(strasse="Hamburgring", hausnummer="4 8")
    units = [Unit(id=1, street="Hamburgring", house_number="48")]
    assert filter_by_address(units, cls) == units


def test_unit_ohne_hausnummer_faellt_raus():
    cls = _cls(strasse="Hamburgring", hausnummer="48")
    units = [Unit(id=1, street="Hamburgring", house_number=None)]
    assert filter_by_address(units, cls) == []


def test_pick_by_size_hint_kleinste():
    unit = pick_by_size_hint(VIERSEN_UNITS, "kleinste")
    assert unit is not None and unit.id == 5050165


def test_pick_by_size_hint_groesste():
    unit = pick_by_size_hint(VIERSEN_UNITS, "groesste")
    assert unit is not None and unit.id == 5050166


def test_pick_by_size_hint_qm_zahl():
    unit = pick_by_size_hint(VIERSEN_UNITS, "7.600 qm")
    assert unit is not None and unit.id == 5050165


def test_pick_by_size_hint_fehlende_flaechen():
    units = [Unit(id=1, property_space_value=None), Unit(id=2, property_space_value=100.0)]
    assert pick_by_size_hint(units, "kleinste") is None


def test_find_unit_hamburgring_ganzes_objekt(monkeypatch):
    monkeypatch.setattr(matcher, "search_units", lambda q: HAMBURGRING_UNITS)
    cls = _cls(strasse="Hamburgring", hausnummer="48", stadt="Mönchengladbach")
    result = find_unit(cls)
    assert result.status == MatchStatus.UNIQUE
    assert {u.id for u in result.units} == {5263216, 5263218}


def test_find_unit_viersen_kleine_einheit(monkeypatch):
    monkeypatch.setattr(matcher, "search_units", lambda q: VIERSEN_UNITS)
    cls = _cls(objekt_name="Viersen Aconlog", groessen_hinweis="kleinste")
    result = find_unit(cls)
    assert result.status == MatchStatus.UNIQUE
    assert [u.id for u in result.units] == [5050165]


def test_find_unit_ambiguous_ohne_hausnummer(monkeypatch):
    monkeypatch.setattr(matcher, "search_units", lambda q: HAMBURGRING_UNITS)
    cls = _cls(strasse="Hamburgring")
    result = find_unit(cls)
    assert result.status == MatchStatus.AMBIGUOUS


def test_find_unit_keine_treffer(monkeypatch):
    monkeypatch.setattr(matcher, "search_units", lambda q: [])
    cls = _cls(strasse="Gibtsnichtweg", hausnummer="1")
    result = find_unit(cls)
    assert result.status == MatchStatus.NONE


def test_find_unit_ohne_adresse():
    result = find_unit(_cls())
    assert result.status == MatchStatus.NONE
