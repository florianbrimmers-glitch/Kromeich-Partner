"""Parsing der Propstack-Antworten: Custom-Field-Objekte, beide Antwortformen,
und der clientseitige Fensterschnitt, den der tagesgenaue Serverfilter offen lässt."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tests.weekly_report import fixtures
from weekly_report import propstack

BERLIN = ZoneInfo("Europe/Berlin")


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def test_custom_field_dicts_unwrapped():
    unit = propstack._to_unit(fixtures.UNITS_RESPONSE["data"][0])
    assert unit.title == "Lagerhalle in (89) Giengen an der Benz"
    assert unit.city == "Giengen an der Brenz"
    assert unit.property_space_value == 10197.0
    assert unit.project_id is None


def test_plain_scalars_pass_through():
    unit = propstack._to_unit(fixtures.UNITS_RESPONSE["data"][2])
    assert unit.title == "Logistikflächen in (41) Kaarst – Halle B"
    assert unit.project_id == 570215


def test_rows_accepts_both_response_shapes():
    assert len(propstack._rows(fixtures.UNITS_RESPONSE)) == 4
    assert len(propstack._rows(fixtures.PROJECTS_RESPONSE)) == 2


def test_rows_skips_entries_without_id():
    assert propstack._rows({"data": [{"title": "kaputt"}, "nicht mal ein dict"]}) == []


def test_float_tolerates_comma_and_none():
    assert propstack._float(None) is None
    assert propstack._float("") is None
    assert propstack._float({"label": "Fläche", "value": "4200.5"}) == 4200.5
    # Propstack schneidet Komma-Dezimalzahlen selbst ab; hier darf nichts crashen.
    assert propstack._float("7,25") is None


def test_fetch_new_units_filters_window_clientside(monkeypatch):
    """Der Serverfilter created_at_from/to ist nur tagesgenau – die Einheit vom
    12.08. 23:59 muss clientseitig rausfallen."""
    monkeypatch.setattr(propstack.config, "propstack_key_objekte", lambda: "k")
    monkeypatch.setattr(
        propstack, "_paginate", lambda *a, **kw: iter(fixtures.UNITS_RESPONSE["data"])
    )

    units = propstack.fetch_new_units(
        _dt("2026-08-13T19:00:00+02:00"), _dt("2026-08-20T19:00:00+02:00")
    )

    assert [u.id for u in units] == [5814044, 5813977, 5802066]  # neueste zuerst
    assert 5700001 not in [u.id for u in units]


def test_fetch_pruef_tasks_stops_at_window_edge(monkeypatch):
    """updated_at_from wird vom Server ignoriert; absteigend lesen und abbrechen,
    sobald wir aus dem Fenster laufen – die alte Aufgabe darf nicht mitkommen."""
    monkeypatch.setattr(propstack.config, "propstack_key_tasks", lambda: "k")
    monkeypatch.setattr(
        propstack, "_paginate", lambda *a, **kw: iter(fixtures.ACTIVITIES_RESPONSE["data"])
    )

    tasks = propstack.fetch_pruef_tasks(
        _dt("2026-08-13T19:00:00+02:00"), _dt("2026-08-20T19:00:00+02:00"), [254958]
    )

    assert [t.id for t in tasks] == [447177220, 447177233, 447177999]
    assert tasks[0].done is True
    assert tasks[0].property_names == ["Panattoni Park Friedewald"]


def test_fetch_pruef_tasks_queries_every_broker(monkeypatch):
    gesehen = []

    def fake_paginate(path, *, key, params):
        gesehen.append(params["broker_id"])
        return iter([])

    monkeypatch.setattr(propstack.config, "propstack_key_tasks", lambda: "k")
    monkeypatch.setattr(propstack, "_paginate", fake_paginate)

    propstack.fetch_pruef_tasks(
        _dt("2026-08-13T19:00:00+02:00"), _dt("2026-08-20T19:00:00+02:00"), [254958, 387451]
    )
    assert gesehen == [254958, 387451]


def test_projects_index_keyed_by_id(monkeypatch):
    monkeypatch.setattr(propstack.config, "propstack_key_objekte", lambda: "k")
    monkeypatch.setattr(propstack, "_paginate", lambda *a, **kw: iter(fixtures.PROJECTS_RESPONSE))

    index = propstack.fetch_projects_index()
    assert set(index) == {570215, 554679}
    assert index[570215].label() == "Logistikflächen in (41) Kaarst"


def test_project_label_falls_back_to_id():
    from weekly_report.models import ProjectInfo

    assert ProjectInfo(id=99).label() == "Projekt 99"
