import json

import pytest
from pydantic import ValidationError

from personalkarussell_handler.classifier import _parse_classification_json, build_thread_context
from personalkarussell_handler.models import Classification, MessageType


def test_fenced_json_mit_zwei_wechseln():
    text = (
        '```json\n{"typ": "wechsel", "wechsel": ['
        '{"vorname": "Moritz", "nachname": "Kalisch", "alte_firma": null, "neue_firma": "Marq logistik"},'
        '{"vorname": "Patrick", "nachname": "Frank", "alte_firma": null, "neue_firma": "Marq logistik"}'
        '], "confidence": 0.9, "begruendung": "zwei Personen"}\n```'
    )
    cls = Classification.model_validate(_parse_classification_json(text))
    assert cls.typ == MessageType.WECHSEL
    assert [w.name() for w in cls.wechsel] == ["Moritz Kalisch", "Patrick Frank"]


def test_abgang_ohne_neue_firma():
    cls = Classification.model_validate(_parse_classification_json(
        'Analyse: {"typ": "abgang", "wechsel": [{"vorname": "Marco", "nachname": "Vajas",'
        ' "alte_firma": "CTXL", "neue_firma": null}], "confidence": 0.9}'
    ))
    assert cls.wechsel[0].neue_firma is None


def test_linkedin_ohne_wechsel_liste():
    cls = Classification.model_validate(_parse_classification_json('{"typ": "linkedin", "confidence": 0.95}'))
    assert cls.wechsel == []


def test_unbekannter_typ_scheitert():
    with pytest.raises(ValidationError):
        Classification.model_validate(_parse_classification_json('{"typ": "quatsch"}'))


def test_kaputtes_json():
    with pytest.raises(json.JSONDecodeError):
        _parse_classification_json("kein json")


def test_thread_kontext_gekuerzt():
    ctx = build_thread_context("x" * 900, ["a", "b", "c", "d", "e", "f", "g"])
    assert ctx.startswith("Ursprungsnachricht: " + "x" * 500)
    assert "Antwort: a" not in ctx and "Antwort: g" in ctx  # nur die letzten 5
