import types

from newsletter_handler import match_ai
from newsletter_handler.models import Deal, DealTyp, MatchStatus, Unit

CANDIDATES = [
    Unit(id=9001, name="Verdion PremierPark – DC5", city="Ludwigsfelde", property_space_value=9158.0),
    Unit(id=9002, name="Lagerhalle Berlin-Spandau", city="Berlin"),
]


def _deal() -> Deal:
    return Deal(deal_typ=DealTyp.VERMIETUNG, ist_vermietung=True,
                objekt_name="Verdion PremierPark Berlin", vermieter="Verdion",
                mieter="Brabus Automotive", stadt="Berlin", confidence=0.9)


def _fake_client(text: str):
    """Minimaler Anthropic-Client-Stub: messages.create(...).content[0].text == text."""
    msg = types.SimpleNamespace(content=[types.SimpleNamespace(text=text)])
    messages = types.SimpleNamespace(create=lambda **kw: msg)
    return types.SimpleNamespace(messages=messages)


def _patch(monkeypatch, text: str):
    monkeypatch.setattr(match_ai, "_get_client", lambda: _fake_client(text))


def test_no_candidates_no_api_call():
    res = match_ai.select_match(_deal(), [])
    assert res.status == MatchStatus.NONE


def test_high_confidence_unique(monkeypatch):
    _patch(monkeypatch, '{"unit_id": 9001, "confidence": 0.95, "begruendung": "Projektname + Entwickler passen"}')
    res = match_ai.select_match(_deal(), CANDIDATES)
    assert res.status == MatchStatus.UNIQUE
    assert [u.id for u in res.units] == [9001]


def test_low_confidence_becomes_ambiguous(monkeypatch):
    _patch(monkeypatch, '{"unit_id": 9001, "confidence": 0.4, "begruendung": "unsicher"}')
    res = match_ai.select_match(_deal(), CANDIDATES)
    assert res.status == MatchStatus.AMBIGUOUS
    assert res.units[0].id == 9001   # Kandidat bleibt sichtbar für Review


def test_null_choice_is_none(monkeypatch):
    _patch(monkeypatch, '{"unit_id": null, "confidence": 0.0, "begruendung": "kein Bezug"}')
    res = match_ai.select_match(_deal(), CANDIDATES)
    assert res.status == MatchStatus.NONE


def test_unknown_id_is_ambiguous(monkeypatch):
    _patch(monkeypatch, '{"unit_id": 12345, "confidence": 0.9, "begruendung": "halluziniert"}')
    res = match_ai.select_match(_deal(), CANDIDATES)
    assert res.status == MatchStatus.AMBIGUOUS


def test_fenced_json_is_parsed(monkeypatch):
    _patch(monkeypatch, '```json\n{"unit_id": 9001, "confidence": 0.9, "begruendung": "ok"}\n```')
    res = match_ai.select_match(_deal(), CANDIDATES)
    assert res.status == MatchStatus.UNIQUE
