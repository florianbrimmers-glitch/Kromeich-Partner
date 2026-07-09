import pytest

from newsletter_handler import matcher
from newsletter_handler.matcher import find_unit, normalize_street, pick_by_size_hint
from newsletter_handler.models import Deal, DealTyp, MatchStatus

from .fixtures import CITYLINK_UNITS, INDUSTRIERING_UNITS


def _deal(**kwargs) -> Deal:
    defaults = {"deal_typ": DealTyp.VERMIETUNG, "ist_vermietung": True, "confidence": 0.9}
    defaults.update(kwargs)
    return Deal(**defaults)


@pytest.mark.parametrize("raw,expected", [
    ("Hamburgring", "hamburgring"),
    ("Musterstr.", "musterstraße"),
    ("Muster Str", "muster straße"),
    ("Industrie-Ring", "industrie ring"),
])
def test_normalize_street(raw, expected):
    assert normalize_street(raw) == expected


def test_find_unit_by_objekt_name_unique(monkeypatch):
    monkeypatch.setattr(matcher, "search_units", lambda q: CITYLINK_UNITS)
    match = find_unit(_deal(objekt_name="CityLink Dortmund", stadt="Dortmund"))
    assert match.status == MatchStatus.UNIQUE
    assert match.units[0].id == 6100001


def test_find_unit_no_match(monkeypatch):
    monkeypatch.setattr(matcher, "search_units", lambda q: [])
    match = find_unit(_deal(objekt_name="Prologis Bönen", stadt="Bönen"))
    assert match.status == MatchStatus.NONE


def test_find_unit_same_address_ohne_hinweis_alle(monkeypatch):
    monkeypatch.setattr(matcher, "search_units", lambda q: INDUSTRIERING_UNITS)
    match = find_unit(_deal(strasse="Industriering", hausnummer="21", stadt="Viersen"))
    assert match.status == MatchStatus.UNIQUE
    assert {u.id for u in match.units} == {6200001, 6200002}


def test_find_unit_size_hint_waehlt_einheit(monkeypatch):
    monkeypatch.setattr(matcher, "search_units", lambda q: INDUSTRIERING_UNITS)
    match = find_unit(_deal(strasse="Industriering", hausnummer="21", stadt="Viersen", groessen_hinweis="9024"))
    assert match.status == MatchStatus.UNIQUE
    assert len(match.units) == 1
    assert match.units[0].id == 6200002


def test_pick_by_size_hint_number():
    unit = pick_by_size_hint(INDUSTRIERING_UNITS, "7600")
    assert unit.id == 6200001
