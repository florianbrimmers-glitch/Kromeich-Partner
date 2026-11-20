"""Ablauf einer Nachricht im #events-Handler (ohne Netz).

Befund vom 19.11.2026: Scheiterte die Anlage in Asana (Token abgelaufen, ungültige
Fälligkeit), bekam die Nachricht trotzdem ✅ und die Antwort „… angelegt“ – das Event
kam nie in der Liste an, der Lauf blieb grün.
"""
from __future__ import annotations

import pytest

from events_handler import main
from events_handler.models import Event, EventExtraction, RunReport


def _event(name, datum_iso="2027-03-24"):
    return Event(ist_event=True, event_name=name, datum="24.03.2027", datum_iso=datum_iso)


@pytest.fixture
def welt(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("NO_WRITE", "false")
    zustand = {"haken": [], "antworten": [], "angelegt": [], "kaputt": set()}

    def create_event_task(name, notes, due_on=None):
        if name in zustand["kaputt"]:
            raise RuntimeError("401 Not Authorized")
        zustand["angelegt"].append((name, due_on))
        return f"https://app.asana.com/0/1/{len(zustand['angelegt'])}"

    monkeypatch.setattr(main, "_gather_source", lambda msg: ("Einladung", "Text"))
    monkeypatch.setattr(main, "get_permalink", lambda ts: "https://example.invalid/p1")
    monkeypatch.setattr(main, "build_task", lambda event, permalink: (event.event_name, "Notiz"))
    monkeypatch.setattr(main, "find_duplicate", lambda event, existing: (None, ""))
    monkeypatch.setattr(main, "create_event_task", create_event_task)
    monkeypatch.setattr(main, "add_checkmark", lambda ts: zustand["haken"].append(ts) or True)
    monkeypatch.setattr(main, "post_thread_reply", lambda ts, text: zustand["antworten"].append(text) or True)
    monkeypatch.setattr(main, "append_record", lambda record: None)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    return zustand


def _lauf(monkeypatch, events):
    monkeypatch.setattr(main, "extract_events", lambda title, content: EventExtraction(events=events))
    report = RunReport()
    main._process_message({"ts": "1.1"}, "run", report, [])
    return report


def test_alles_angelegt_haken_und_echte_zahl(welt, monkeypatch):
    report = _lauf(monkeypatch, [_event("LogiMAT"), _event("transport logistic")])
    assert welt["haken"] == ["1.1"]
    assert welt["antworten"][0].startswith("2 Event(s) als Aufgabe")
    assert report.fehler == []


def test_asana_scheitert_kein_haken_keine_erfolgsmeldung(welt, monkeypatch):
    welt["kaputt"].add("transport logistic")
    report = _lauf(monkeypatch, [_event("LogiMAT"), _event("transport logistic")])

    assert welt["haken"] == [] and welt["antworten"] == []
    assert len(report.fehler) == 1 and "transport logistic" in report.fehler[0]
    assert [name for name, _ in welt["angelegt"]] == ["LogiMAT"]   # beim Nachholen schützt der Dublettencheck


def test_schon_vorhandenes_event_wird_nicht_als_angelegt_gemeldet(welt, monkeypatch):
    monkeypatch.setattr(main, "find_duplicate",
                        lambda event, existing: ("123", "gleiches Event") if event.event_name == "LogiMAT" else (None, ""))
    _lauf(monkeypatch, [_event("LogiMAT"), _event("transport logistic")])
    assert welt["antworten"][0] == "1 Event(s) als Aufgabe im Marketing-Projekt (Abschnitt „Events\") angelegt. 1 stand(en) schon in der Liste."


@pytest.mark.parametrize("datum_iso,erwartet", [
    ("2027-03-24", "2027-03-24"), ("2027-06-16/17", None), ("24.03.2027", None), ("", None), (None, None),
])
def test_nur_ein_echtes_datum_geht_als_faelligkeit_an_asana(datum_iso, erwartet):
    assert main._gueltiges_datum(datum_iso) == erwartet


def test_ungueltiges_datum_aufgabe_ohne_faelligkeit_statt_gar_nicht(welt, monkeypatch):
    report = _lauf(monkeypatch, [_event("Sommerfest", datum_iso="2027-06-16/17")])
    assert welt["angelegt"] == [("Sommerfest", None)]
    assert report.fehler == [] and welt["haken"] == ["1.1"]
