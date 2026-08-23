from __future__ import annotations

import httpx
import pytest

from hallentinder import propstack
from hallentinder.models import LeadPayload


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def test_items_akzeptiert_liste_und_data_wrapper():
    assert propstack._items([{"id": 1}]) == [{"id": 1}]
    assert propstack._items({"data": [{"id": 2}]}) == [{"id": 2}]
    assert propstack._items({}) == []
    assert propstack._items([{"id": 1}, "müll"]) == [{"id": 1}]


def test_list_units_paginiert_bis_zur_letzten_seite(monkeypatch):
    seiten = {1: [{"id": i} for i in range(1, 101)], 2: [{"id": 101}]}
    aufrufe = []

    def fake_request(method, path, *, key, params=None, json=None):
        aufrufe.append(params["page"])
        return FakeResponse(seiten.get(params["page"], []))

    monkeypatch.setattr(propstack, "_request", fake_request)
    monkeypatch.setattr(propstack.time, "sleep", lambda s: None)
    monkeypatch.setenv("PROPSTACK_API_KEY", "test")

    units = propstack.list_units()

    assert len(units) == 101
    assert aufrufe == [1, 2]


def test_list_units_verwirft_doppelt_gelieferte_objekte(monkeypatch):
    """Der Abruf dauert ~2 Minuten; driftet die Seitenabfrage, kommen Objekte
    doppelt – im Deck stünde dieselbe Halle dann zweimal."""
    seiten = {
        1: [{"id": i} for i in range(1, 101)],
        2: [{"id": i} for i in range(95, 195)],   # 6 Überschneidungen durch Drift
        3: [{"id": 195}],
    }
    monkeypatch.setattr(propstack, "_request",
                        lambda *a, **k: FakeResponse(seiten.get(k["params"]["page"], [])))
    monkeypatch.setattr(propstack.time, "sleep", lambda s: None)
    monkeypatch.setenv("PROPSTACK_API_KEY", "test")

    units = propstack.list_units()
    ids = [u["id"] for u in units]

    assert len(ids) == len(set(ids)), "keine Duplikate im Ergebnis"
    assert ids == sorted(ids) and ids[0] == 1 and ids[-1] == 195


def test_list_units_sortiert_stabil(monkeypatch):
    """Ohne feste Sortierung wandern Objekte während des Durchlaufs zwischen den Seiten."""
    gesendet = []
    monkeypatch.setattr(propstack, "_request",
                        lambda *a, **k: gesendet.append(k["params"]) or FakeResponse([]))
    monkeypatch.setenv("PROPSTACK_API_KEY", "test")

    propstack.list_units()

    assert gesendet[0]["sort_by"] == "id"
    assert gesendet[0]["order"] == "asc"


def test_dublettencheck_prueft_die_adresse_lokal(monkeypatch):
    """Die Volltextsuche trifft auch Teilstrings – nur exakte Adressen zählen."""
    monkeypatch.setenv("PROPSTACK_API_KEY", "test")
    monkeypatch.setattr(propstack, "_request", lambda *a, **k: FakeResponse(
        [{"id": 1, "email": "andere@example.com"}, {"id": 2, "email": "Max@Example.com "}]
    ))
    assert propstack.find_contact_by_email("max@example.com") == 2


def test_dublettencheck_ohne_treffer(monkeypatch):
    monkeypatch.setenv("PROPSTACK_API_KEY", "test")
    monkeypatch.setattr(propstack, "_request", lambda *a, **k: FakeResponse([{"id": 1, "email": "x@y.de"}]))
    assert propstack.find_contact_by_email("max@example.com") is None


def test_no_write_verhindert_kontakt_und_deal(monkeypatch):
    monkeypatch.setenv("NO_WRITE", "true")
    monkeypatch.setattr(propstack, "_request", lambda *a, **k: pytest.fail("kein Write erlaubt"))
    lead = LeadPayload(token="x" * 12, nachname="Muster", email="max@example.com", einwilligung=True)
    assert propstack.create_contact(lead) is None
    assert propstack.create_deal(1, 2) is None


def test_create_deal_payload(monkeypatch):
    monkeypatch.setenv("NO_WRITE", "false")
    monkeypatch.setenv("PROPSTACK_API_KEY", "test")
    gesendet = {}

    def fake_request(method, path, *, key, params=None, json=None):
        gesendet.update({"method": method, "path": path, "json": json})
        return FakeResponse({"id": 99})

    monkeypatch.setattr(propstack, "_request", fake_request)
    assert propstack.create_deal(7, 8, "Notiz") == 99
    assert gesendet["method"] == "POST"
    assert gesendet["path"] == "/client_properties"
    assert gesendet["json"] == {"client_property": {"client_id": 7, "property_id": 8, "note": "Notiz"}}


def test_retry_bei_serverfehler(monkeypatch):
    versuche = []

    def fake_httpx_request(method, url, **kwargs):
        versuche.append(1)
        request = httpx.Request(method, url)
        status = 500 if len(versuche) < 3 else 200
        return httpx.Response(status, json=[], request=request)

    monkeypatch.setattr(propstack.httpx, "request", fake_httpx_request)
    monkeypatch.setattr(propstack.time, "sleep", lambda s: None)

    antwort = propstack._request("GET", "/units", key="test")

    assert antwort.status_code == 200
    assert len(versuche) == 3


def test_client_fehler_wird_sofort_geraist(monkeypatch):
    def fake_httpx_request(method, url, **kwargs):
        return httpx.Response(422, json={"error": "kaputt"}, request=httpx.Request(method, url))

    monkeypatch.setattr(propstack.httpx, "request", fake_httpx_request)
    with pytest.raises(httpx.HTTPStatusError):
        propstack._request("POST", "/client_properties", key="test", json={})
