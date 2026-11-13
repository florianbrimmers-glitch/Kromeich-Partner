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


def test_link_labels_person_row_as_mitarbeiter(monkeypatch):
    # name beschreibt client_id (die Person) und wird an der Firma angezeigt.
    # Am 12.11.2026 irrtümlich auf "Firma" gedreht: Dann steht am Kontakt die
    # Firma als "Mitarbeiter" (Oberfläche geprüft am 13.11.2026).
    posts = []

    def fake_post(url, json=None, headers=None, **kw):
        posts.append((url, json, headers))
        return _Resp({}, 201)

    monkeypatch.setattr(ps.httpx, "post", fake_post)
    assert ps.link_contact_to_company(111, 222) is True
    url, body, headers = posts[0]
    assert url == "https://api.propstack.de/v2/relationships"
    assert body == {"internal_name": "associate", "name": "Mitarbeiter",
                    "client_id": 111, "related_client_id": 222}
    assert headers["X-Api-Key"] == "v2"


# --- Firmen-Dubletten bei abweichender Rechtsform (12.11.2026) -----------------

def _search_by_term(monkeypatch, by_term):
    """Propstack-Suche nachstellen: Treffer hängen vom Suchbegriff ab."""
    calls = []

    def fake_get(url, params=None, **kw):
        calls.append(params["q"])
        return _Resp(by_term.get(params["q"], []))

    monkeypatch.setattr(ps.httpx, "get", fake_get)
    return calls


GOODMAN = {"id": 17366550, "is_company": True, "name": "Goodman Germany GmbH",
           "company": "Goodman Germany GmbH", "first_name": None, "last_name": None}
GOODMAN_SHORT = {"id": 36103370, "is_company": True, "name": "Goodman",
                 "company": "Goodman", "first_name": None, "last_name": None}


def test_search_terms_full_core_first_word():
    assert ps._company_search_terms("Goodman Germany GmbH & Co. KG") == [
        "Goodman Germany GmbH & Co. KG", "Goodman Germany", "Goodman"]
    assert ps._company_search_terms("Bayer AG") == ["Bayer AG", "Bayer"]
    assert ps._company_search_terms("Goodman") == ["Goodman"]
    # kurzes erstes Wort wird nicht allein gesucht
    assert ps._company_search_terms("DB Schenker AG") == ["DB Schenker AG", "DB Schenker"]


def test_find_company_other_legal_form(monkeypatch):
    # Propstack verlangt jedes Wort: der volle Name findet nichts, der Kern schon
    calls = _search_by_term(monkeypatch, {"Goodman Germany": [GOODMAN], "Goodman": [GOODMAN, GOODMAN_SHORT]})
    assert ps.find_company("Goodman Germany AG") == 17366550
    assert calls == ["Goodman Germany AG", "Goodman Germany", "Goodman"]


def test_find_company_other_legal_form_and_spelling(monkeypatch):
    _search_by_term(monkeypatch, {"L.I.T.": [
        {"id": 8, "is_company": True, "name": "LIT AG", "company": "LIT AG"}]})
    assert ps.find_company("L.I.T. GmbH") == 8


def test_find_company_prefers_exact_over_other_legal_form(monkeypatch):
    ag = {"id": 5, "is_company": True, "name": "Goodman Germany AG", "company": "Goodman Germany AG"}
    _search_by_term(monkeypatch, {"Goodman Germany AG": [ag], "Goodman Germany": [GOODMAN, ag]})
    assert ps.find_company("Goodman Germany AG") == 5


def test_find_company_takes_oldest_of_several(monkeypatch):
    newer = dict(GOODMAN, id=99999999)
    _search_by_term(monkeypatch, {"Goodman Germany": [newer, GOODMAN]})
    assert ps.find_company("Goodman Germany SE") == 17366550


def test_find_company_short_form_uses_single_similar_company(monkeypatch, caplog):
    # Signatur nennt nur die Kurzform; vorhanden ist genau eine länger benannte Firma
    _search_by_term(monkeypatch, {"Goodman": [GOODMAN]})
    with caplog.at_level("WARNING"):
        assert ps.find_company("Goodman") == 17366550
    assert "ähnlich benannten Firma zugeordnet" in caplog.text
    # und umgekehrt: vorhanden ist nur die Kurzform
    _search_by_term(monkeypatch, {"Goodman": [GOODMAN_SHORT]})
    assert ps.find_company("Goodman Germany GmbH") == 36103370


def test_find_company_several_similar_companies_not_used(monkeypatch, caplog):
    belgium = {"id": 77, "is_company": True, "name": "Goodman Belgium NV", "company": "Goodman Belgium NV"}
    _search_by_term(monkeypatch, {"Goodman": [GOODMAN, belgium]})
    with caplog.at_level("WARNING"):
        assert ps.find_company("Goodman") is None
    assert "wird nicht verwendet" in caplog.text


def test_find_company_similar_with_legal_form_is_other_company(monkeypatch):
    # Der kürzere Name trägt eine Rechtsform -> eigene Firma, keine Kurzform
    _search_by_term(monkeypatch, {"L.I.T.": [
        {"id": 12, "is_company": True, "name": "L.I.T. Speditions GmbH", "company": "L.I.T. Speditions GmbH"}]})
    assert ps.find_company("L.I.T. AG") is None


def test_find_company_person_flagged_as_company_not_matched_loosely(monkeypatch):
    _search_by_term(monkeypatch, {"Goodman Germany": [
        {"id": 9, "is_company": True, "name": "Max Muster (Goodman Germany GmbH)",
         "company": "Goodman Germany GmbH", "first_name": "Max", "last_name": "Muster"}]})
    assert ps.find_company("Goodman Germany AG") is None


def test_find_company_search_error_returns_none(monkeypatch):
    def boom(url, params=None, **kw):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(ps.httpx, "get", boom)
    assert ps.find_company("Goodman Germany GmbH") is None
