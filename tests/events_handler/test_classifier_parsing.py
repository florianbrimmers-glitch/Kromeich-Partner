import json

import pytest
from pydantic import ValidationError

from events_handler.classifier import _parse_extraction_json, html_to_text
from events_handler.models import Event, EventExtraction


def test_plain_json_list():
    raw = _parse_extraction_json(
        '{"events": [{"ist_event": true, "datum": "04.10.2026", "event_name": "Netzwerkevent", "confidence": 0.9}]}'
    )
    ex = EventExtraction.model_validate(raw)
    assert len(ex.events) == 1
    assert ex.events[0].ist_event is True
    assert ex.events[0].datum == "04.10.2026"


def test_fenced_json():
    text = '```json\n{"events": [{"ist_event": false, "confidence": 0.2, "begruendung": "Werbung"}]}\n```'
    ex = EventExtraction.model_validate(_parse_extraction_json(text))
    assert ex.events[0].ist_event is False


def test_prose_around_json():
    text = 'Analyse:\n{"events": [{"ist_event": true, "ort": "Köln", "confidence": 0.8}]}\nFertig.'
    ex = EventExtraction.model_validate(_parse_extraction_json(text))
    assert ex.events[0].ort == "Köln"


def test_empty_events():
    ex = EventExtraction.model_validate(_parse_extraction_json('{"events": []}'))
    assert ex.events == []


def test_broken_json_raises():
    with pytest.raises(json.JSONDecodeError):
        _parse_extraction_json("kein json")


def test_missing_ist_event_defaults_false():
    # ist_event hat Default False -> Nicht-Event, wird ignoriert
    ev = Event.model_validate({"event_name": "X", "confidence": 0.5})
    assert ev.ist_event is False


def test_extra_fields_ignored():
    ev = Event.model_validate({"ist_event": True, "foo": "bar", "confidence": 0.9})
    assert ev.ist_event is True


def test_html_to_text_strips_tags_and_scripts():
    html = """<html><head><style>.a{color:red}</style></head>
    <body><script>var x=1;</script><h1>Netzwerkevent</h1>
    <p>am <b>04.10.2026</b> in&nbsp;Köln</p></body></html>"""
    text = html_to_text(html)
    assert "Netzwerkevent" in text
    assert "04.10.2026" in text
    assert "Köln" in text
    assert "color:red" not in text
    assert "var x=1" not in text
    assert "<" not in text and ">" not in text


def test_html_to_text_empty():
    assert html_to_text("") == ""
