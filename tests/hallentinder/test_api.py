from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hallentinder import api, catalog, leads
from hallentinder.models import LeadResult
from hallentinder.ratelimit import limiter

from .fixtures import BESTAND


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(catalog, "cards", lambda force=False: catalog.build_cards(BESTAND))
    monkeypatch.setenv("NO_WRITE", "true")
    limiter.reset()
    return TestClient(api.app)


def profil(**overrides):
    basis = {"ort": "49076", "flaeche_min": 0, "flaeche_max": 0, "radius_km": 200}
    basis.update(overrides)
    return basis


def test_session_liefert_token_und_erste_karten(client):
    antwort = client.post("/api/session", json=profil())
    assert antwort.status_code == 200
    daten = antwort.json()
    assert daten["token"]
    assert daten["region_erkannt"] is True
    assert daten["treffer"] == len(daten["karten"])
    assert daten["karten"][0]["id"] == 1


def test_api_gibt_keine_internen_felder_heraus(client):
    daten = client.post("/api/session", json=profil()).json()
    for karte in daten["karten"]:
        assert "broker" not in karte
        assert "rented" not in karte


def test_ungueltiges_profil_wird_abgelehnt(client):
    assert client.post("/api/session", json=profil(ort="")).status_code == 422
    assert client.post("/api/session", json=profil(flaeche_min=-5)).status_code == 422


def test_swipe_zaehlt_likes(client):
    token = client.post("/api/session", json=profil()).json()["token"]
    antwort = client.post("/api/swipe", json={"token": token, "unit_id": 1, "richtung": "like"})
    assert antwort.json() == {"likes": 1, "dislikes": 0}
    client.post("/api/swipe", json={"token": token, "unit_id": 3, "richtung": "dislike"})
    assert client.get("/api/likes", params={"token": token}).json()["karten"][0]["id"] == 1


def test_abgelaufenes_token_gibt_404(client):
    antwort = client.post("/api/swipe", json={"token": "x" * 12, "unit_id": 1, "richtung": "like"})
    assert antwort.status_code == 404


def test_lead_ohne_likes_gibt_400(client):
    token = client.post("/api/session", json=profil()).json()["token"]
    antwort = client.post("/api/lead", json={
        "token": token, "nachname": "Muster", "email": "max@example.com", "einwilligung": True,
    })
    assert antwort.status_code == 400


def test_lead_erfolgreich(client, monkeypatch):
    monkeypatch.setattr(leads, "verarbeite", lambda s, l: LeadResult(kontakt_id=1, deals_angelegt=2))
    token = client.post("/api/session", json=profil()).json()["token"]
    client.post("/api/swipe", json={"token": token, "unit_id": 1, "richtung": "like"})
    antwort = client.post("/api/lead", json={
        "token": token, "nachname": "Muster", "email": "max@example.com", "einwilligung": True,
    })
    assert antwort.status_code == 200
    assert antwort.json()["deals_angelegt"] == 2


def test_honeypot_meldet_erfolg_ohne_write(client, monkeypatch):
    """Bots sollen keinen Unterschied zum Erfolgsfall sehen – geschrieben wird nichts."""
    def kein_write(session, lead):
        raise leads.LeadFehler("honeypot")

    monkeypatch.setattr(leads, "verarbeite", kein_write)
    token = client.post("/api/session", json=profil()).json()["token"]
    antwort = client.post("/api/lead", json={
        "token": token, "nachname": "Muster", "email": "max@example.com",
        "einwilligung": True, "website": "http://spam",
    })
    assert antwort.status_code == 200
    assert antwort.json()["deals_angelegt"] == 0


def test_propstack_ausfall_gibt_502(client, monkeypatch):
    def kaputt(session, lead):
        raise RuntimeError("API down")

    monkeypatch.setattr(leads, "verarbeite", kaputt)
    token = client.post("/api/session", json=profil()).json()["token"]
    client.post("/api/swipe", json={"token": token, "unit_id": 1, "richtung": "like"})
    antwort = client.post("/api/lead", json={
        "token": token, "nachname": "Muster", "email": "max@example.com", "einwilligung": True,
    })
    assert antwort.status_code == 502


def test_bestand_nicht_erreichbar_gibt_503(client, monkeypatch):
    def kaputt(force=False):
        raise RuntimeError("down")

    monkeypatch.setattr(catalog, "cards", kaputt)
    assert client.post("/api/session", json=profil()).status_code == 503


def test_rate_limit_greift(client, monkeypatch):
    monkeypatch.setenv("HALLENTINDER_RATE_LIMIT", "3")
    limiter.reset()
    codes = [client.post("/api/session", json=profil()).status_code for _ in range(4)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429


def test_healthz(client):
    daten = client.get("/healthz").json()
    assert daten["status"] == "ok"
    assert daten["no_write"] is True


def test_startseite_wird_ausgeliefert(client):
    antwort = client.get("/")
    assert antwort.status_code == 200
    assert "Hallentinder" in antwort.text
