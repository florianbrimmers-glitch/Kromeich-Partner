from __future__ import annotations

import pytest

from hallentinder import catalog, leads
from hallentinder.models import LeadPayload, SearchProfile, SwipeRichtung
from hallentinder.session import SessionStore

from .fixtures import BESTAND


def session_mit_likes(*ids):
    store = SessionStore()
    session = store.anlegen(
        SearchProfile(ort="49076", flaeche_min=3000, flaeche_max=6000),
        catalog.build_cards(BESTAND),
        50,
    )
    for unit_id in ids:
        store.swipe(session.token, unit_id, SwipeRichtung.LIKE)
    return session


def lead(**overrides) -> LeadPayload:
    basis = {
        "token": "x" * 12,
        "nachname": "Muster",
        "email": "max@example.com",
        "einwilligung": True,
    }
    basis.update(overrides)
    return LeadPayload(**basis)


@pytest.fixture(autouse=True)
def kein_no_write(monkeypatch):
    monkeypatch.setenv("NO_WRITE", "false")


def test_bestehender_kontakt_wird_wiederverwendet(monkeypatch):
    angelegt = []
    monkeypatch.setattr(leads.propstack, "find_contact_by_email", lambda e: 4242)
    monkeypatch.setattr(leads.propstack, "create_contact", lambda l: pytest.fail("darf nicht anlegen"))
    monkeypatch.setattr(leads.propstack, "create_deal", lambda c, p, n=None: angelegt.append((c, p)) or 1)

    ergebnis = leads.verarbeite(session_mit_likes(1, 3), lead())

    assert ergebnis.kontakt_id == 4242
    assert ergebnis.kontakt_neu is False
    assert ergebnis.deals_angelegt == 2
    assert [p for _, p in angelegt] == [1, 3]


def test_neuer_kontakt_wird_angelegt(monkeypatch):
    monkeypatch.setattr(leads.propstack, "find_contact_by_email", lambda e: None)
    monkeypatch.setattr(leads.propstack, "create_contact", lambda l: 777)
    monkeypatch.setattr(leads.propstack, "create_deal", lambda c, p, n=None: 1)

    ergebnis = leads.verarbeite(session_mit_likes(1), lead())

    assert (ergebnis.kontakt_id, ergebnis.kontakt_neu, ergebnis.deals_angelegt) == (777, True, 1)


def test_ein_fehlgeschlagener_deal_stoppt_die_uebrigen_nicht(monkeypatch):
    def deal(client_id, property_id, note=None):
        if property_id == 1:
            raise RuntimeError("HTTP 422")
        return 5

    monkeypatch.setattr(leads.propstack, "find_contact_by_email", lambda e: 1)
    monkeypatch.setattr(leads.propstack, "create_deal", deal)

    ergebnis = leads.verarbeite(session_mit_likes(1, 3), lead())

    assert (ergebnis.deals_angelegt, ergebnis.deals_fehlgeschlagen) == (1, 1)


def test_no_write_schreibt_nichts(monkeypatch):
    monkeypatch.setenv("NO_WRITE", "true")
    monkeypatch.setattr(leads.propstack, "find_contact_by_email", lambda e: None)

    ergebnis = leads.verarbeite(session_mit_likes(1, 3), lead())

    assert ergebnis.no_write is True
    assert ergebnis.deals_geplant == 2
    assert ergebnis.deals_angelegt == 0


def test_ohne_einwilligung_kein_write():
    with pytest.raises(leads.LeadFehler):
        leads.verarbeite(session_mit_likes(1), lead(einwilligung=False))


def test_honeypot_wird_erkannt():
    with pytest.raises(leads.LeadFehler, match="honeypot"):
        leads.verarbeite(session_mit_likes(1), lead(website="http://spam"))


def test_ungueltige_email():
    with pytest.raises(leads.LeadFehler):
        leads.verarbeite(session_mit_likes(1), lead(email="keine-adresse"))


def test_ohne_likes_kein_lead():
    with pytest.raises(leads.LeadFehler):
        leads.verarbeite(session_mit_likes(), lead())


def test_deal_notiz_enthaelt_suchprofil():
    session = session_mit_likes(1)
    notiz = leads._deal_notiz(session.profil, session.gelikte_karten()[0], "Bitte um Rückruf")
    assert "Hallentinder" in notiz
    assert "49076" in notiz
    assert "Rückruf" in notiz
