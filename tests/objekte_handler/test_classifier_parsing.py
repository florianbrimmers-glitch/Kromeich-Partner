import json

import pytest
from pydantic import ValidationError

from objekte_handler.classifier import _parse_classification_json
from objekte_handler.models import Classification


def test_plain_json():
    raw = _parse_classification_json('{"typ": "ignorieren", "confidence": 0.9}')
    assert raw["typ"] == "ignorieren"


def test_fenced_json():
    text = '```json\n{"typ": "status_anweisung", "aktion": "vermietet", "confidence": 0.95}\n```'
    raw = _parse_classification_json(text)
    assert raw["aktion"] == "vermietet"


def test_prose_around_json():
    text = 'Hier meine Analyse:\n{"typ": "fehlt_in_ps", "objekt_name": "Landau von Nvelop", "confidence": 0.9}\nFertig.'
    raw = _parse_classification_json(text)
    assert raw["objekt_name"] == "Landau von Nvelop"


def test_nested_json():
    text = 'Analyse: {"typ": "ignorieren", "meta": {"x": 1}, "confidence": 0.5}'
    raw = _parse_classification_json(text)
    # erste { bis letzte } – verschachtelte Objekte bleiben intakt
    assert raw["typ"] == "ignorieren"
    assert raw["meta"] == {"x": 1}


def test_broken_json_raises():
    with pytest.raises(json.JSONDecodeError):
        _parse_classification_json("kein json hier")


def test_unknown_typ_fails_validation():
    raw = _parse_classification_json('{"typ": "quatsch", "confidence": 0.9}')
    with pytest.raises(ValidationError):
        Classification.model_validate(raw)


def test_valid_classification_model():
    raw = _parse_classification_json(
        '{"typ": "status_anweisung", "aktion": "vermietet", "strasse": "Hamburgring",'
        ' "hausnummer": "48", "stadt": "Mönchengladbach", "confidence": 0.97, "begruendung": "klar"}'
    )
    cls = Classification.model_validate(raw)
    assert cls.hausnummer == "48"
    assert cls.confidence == 0.97
