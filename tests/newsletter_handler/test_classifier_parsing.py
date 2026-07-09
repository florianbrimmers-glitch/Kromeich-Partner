import json

import pytest
from pydantic import ValidationError

from newsletter_handler.classifier import _parse_extraction_json
from newsletter_handler.models import Deal, DealTyp, NewsletterExtraction


def test_plain_json_list():
    raw = _parse_extraction_json('{"deals": [{"deal_typ": "vermietung", "ist_vermietung": true, "confidence": 0.9}]}')
    ex = NewsletterExtraction.model_validate(raw)
    assert len(ex.deals) == 1
    assert ex.deals[0].deal_typ == DealTyp.VERMIETUNG
    assert ex.deals[0].ist_vermietung is True


def test_fenced_json():
    text = '```json\n{"deals": [{"deal_typ": "transaktion", "ist_vermietung": false, "confidence": 0.8}]}\n```'
    raw = _parse_extraction_json(text)
    ex = NewsletterExtraction.model_validate(raw)
    assert ex.deals[0].deal_typ == DealTyp.TRANSAKTION


def test_prose_around_json():
    text = 'Analyse:\n{"deals": [{"deal_typ": "neubau", "ist_vermietung": false, "stadt": "Köln", "confidence": 0.7}]}\nFertig.'
    raw = _parse_extraction_json(text)
    ex = NewsletterExtraction.model_validate(raw)
    assert ex.deals[0].stadt == "Köln"


def test_empty_deals():
    raw = _parse_extraction_json('{"deals": []}')
    ex = NewsletterExtraction.model_validate(raw)
    assert ex.deals == []


def test_broken_json_raises():
    with pytest.raises(json.JSONDecodeError):
        _parse_extraction_json("kein json hier")


def test_unknown_deal_typ_fails_validation():
    raw = _parse_extraction_json('{"deals": [{"deal_typ": "quatsch", "confidence": 0.9}]}')
    with pytest.raises(ValidationError):
        NewsletterExtraction.model_validate(raw)


def test_deal_field_mapping():
    deal = Deal.model_validate({
        "deal_typ": "vermietung", "ist_vermietung": True, "stadt": "Dortmund",
        "objekt_name": "CityLink Dortmund", "groessen_hinweis": "6000",
        "mieter": "LAMPAG GmbH", "vermieter": "REALOGIS", "confidence": 0.85,
    })
    assert deal.mieter == "LAMPAG GmbH"
    assert deal.groessen_hinweis == "6000"
    assert deal.confidence == 0.85
