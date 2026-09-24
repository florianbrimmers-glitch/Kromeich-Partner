"""Firmen-Suche und -Anlage in src/propstack_client.py.

Regression zum 24.09.2026: Firmen wurden mit last_name == company angelegt,
Propstack zeigte sie als "X (X)" an, find_company() fand sie nicht mehr und
die Pipeline legte bei jedem weiteren Kontakt derselben Firma eine Dublette an
(GS1 Germany GmbH lag dreifach im System)."""
import httpx
import pytest

from src import propstack_client as ps
from src.models import ContactData


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.setenv("PROPSTACK_API_KEY", "v1")
    monkeypatch.setenv("PROPSTACK_API_V2_CONTACTS", "v2")


def _search_returns(monkeypatch, records):
    calls = []

    def fake_get(url, params=None, **kw):
        calls.append(params)
        return _Resp(records)

    monkeypatch.setattr(ps.httpx, "get", fake_get)
    return calls


def test_find_company_matches_legacy_doubled_name(monkeypatch):
    _search_returns(monkeypatch, [
        {"id": 7, "is_company": True, "name": "GS1 Germany GmbH (GS1 Germany GmbH)",
         "company": "GS1 Germany GmbH"},
    ])
    assert ps.find_company("GS1 Germany GmbH") == 7


def test_find_company_ignores_punctuation(monkeypatch):
    _search_returns(monkeypatch, [
        {"id": 8, "is_company": True, "name": "LIT AG", "company": "LIT AG"},
    ])
    assert ps.find_company("L.I.T. AG") == 8


def test_find_company_ignores_spacing_in_legal_form(monkeypatch):
    _search_returns(monkeypatch, [
        {"id": 11, "is_company": True, "name": "Uhlhorn GmbH & Co.KG", "company": "Uhlhorn GmbH & Co.KG"},
    ])
    assert ps.find_company("Uhlhorn GmbH & Co. KG") == 11


def test_find_company_no_false_positive_on_similar_name(monkeypatch):
    _search_returns(monkeypatch, [
        {"id": 12, "is_company": True, "name": "L.I.T. Speditions GmbH", "company": "L.I.T. Speditions GmbH"},
    ])
    assert ps.find_company("L.I.T. AG") is None


def test_find_company_does_not_match_person_flagged_as_company(monkeypatch):
    # "Person (Firma)"-Altlast: darf nicht als Firma "Firma" durchgehen
    _search_returns(monkeypatch, [
        {"id": 9, "is_company": True, "name": "Robin Balsmeier (ImmoKonzept Plan GmbH)",
         "company": "ImmoKonzept Plan GmbH", "first_name": "Robin", "last_name": "Balsmeier"},
    ])
    # company-Feld stimmt zwar, aber der Datensatz ist eine Person
    assert ps.find_company("ImmoKonzept Plan GmbH") is None


def test_find_company_uses_per_not_per_page(monkeypatch):
    calls = _search_returns(monkeypatch, [])
    ps.find_company("Irgendwas GmbH")
    assert "per" in calls[0] and "per_page" not in calls[0]


def test_create_company_clears_last_name(monkeypatch):
    puts = []
    monkeypatch.setattr(ps.httpx, "post", lambda url, **kw: _Resp({"id": 42}))
    monkeypatch.setattr(ps.httpx, "put", lambda url, json=None, **kw: puts.append(json) or _Resp({}))
    assert ps.create_company(ContactData(email="a@b.de", company="Bayer AG")) == 42
    assert puts[0]["commercial"] is True
    assert puts[0]["company"] == "Bayer AG"
    assert "last_name" in puts[0] and puts[0]["last_name"] is None


def test_name_duplicate_found_even_if_flagged_as_company(monkeypatch):
    _search_returns(monkeypatch, [
        {"id": 5, "is_company": True, "first_name": "Robin", "last_name": "Balsmeier",
         "name": "Robin Balsmeier (ImmoKonzept Plan GmbH)"},
    ])
    assert ps.check_duplicate_by_name("Robin", "Balsmeier") is True
