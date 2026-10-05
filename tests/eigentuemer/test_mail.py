from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from eigentuemer import api, mail
from eigentuemer.models import Status

from .fixtures import formular, kontakt

PASSWORT = "test-passwort"
ZUGANG = ("florian", PASSWORT)


@pytest.fixture
def versand(monkeypatch):
    """Sammelt, was verschickt würde, statt es zu verschicken."""
    gesendet: list[tuple[list[str], str, str]] = []

    def fake(an, betreff, text):
        gesendet.append((an, betreff, text))
        return True

    monkeypatch.setattr(mail, "_versenden", fake)
    return gesendet


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EIGENTUEMER_DATEN", str(tmp_path))
    monkeypatch.setenv("EIGENTUEMER_PRUEF_PASSWORT", PASSWORT)
    monkeypatch.setenv("EIGENTUEMER_INTERN_AN", "objekte@kromeichpartner.de")
    monkeypatch.setenv("EIGENTUEMER_BASIS_URL", "https://hallen.example")
    with TestClient(api.app) as c:
        yield c


def nachweis():
    return [("nachweis", ("grundbuch.pdf", b"%PDF-1.4 test", "application/pdf"))]


def test_eingangsmail_enthaelt_den_statuslink(client, versand):
    """Ohne diese Mail ist der Statuslink nach dem Schließen des Browsers weg."""
    antwort = client.post("/api/einreichung", data=formular(), files=nachweis())
    token = antwort.json()["token"]

    an_einsender = [m for m in versand if kontakt().email in m[0]]
    assert len(an_einsender) == 1
    _, betreff, text = an_einsender[0]
    assert antwort.json()["nummer"] in betreff
    assert f"https://hallen.example/status.html?t={token}" in text
    assert "Grundbuchauszug" in text


def test_intern_wird_ueber_neue_einreichung_informiert(client, versand):
    client.post("/api/einreichung", data=formular(), files=nachweis())
    intern = [m for m in versand if "objekte@kromeichpartner.de" in m[0]]
    assert len(intern) == 1
    assert "Neue Einreichung" in intern[0][1]


def test_freigabe_meldet_dass_das_objekt_online_ist(client, versand):
    client.post("/api/einreichung", data=formular(), files=nachweis())
    versand.clear()

    client.post("/api/pruefung/1/entscheidung", auth=ZUGANG,
                json={"freigeben": True, "pruefer": "Florian"})

    _, betreff, text = versand[0]
    assert "online" in betreff.lower()
    assert "zurückziehen" in text.lower()


def test_ablehnung_nennt_den_grund_in_der_mail(client, versand):
    client.post("/api/einreichung", data=formular(), files=nachweis())
    versand.clear()

    client.post("/api/pruefung/1/entscheidung", auth=ZUGANG,
                json={"freigeben": False, "pruefer": "Florian", "grund": "Auszug älter als 6 Monate"})

    _, _, text = versand[0]
    assert "Auszug älter als 6 Monate" in text


def test_adressaenderung_meldet_sich_intern(client, versand):
    import json
    from .fixtures import objekt

    antwort = client.post("/api/einreichung", data=formular(), files=nachweis())
    token = antwort.json()["token"]
    client.post("/api/pruefung/1/entscheidung", auth=ZUGANG, json={"freigeben": True, "pruefer": "F"})
    versand.clear()

    daten = {**objekt().model_dump(), "strasse": "Neue Straße"}
    client.put(f"/api/vorgang/{token}", data={"objekt": json.dumps(daten)}, files=nachweis())

    intern = [m for m in versand if "objekte@kromeichpartner.de" in m[0]]
    assert intern and "erneute Prüfung" in intern[0][1]


def test_smtp_ausfall_zerstoert_die_einreichung_nicht(client, monkeypatch):
    """Ein Vorgang, der an einem SMTP-Timeout stirbt, wäre schlimmer als
    ein Vorgang ohne Mail."""
    def kaputt(*args, **kwargs):
        raise OSError("SMTP nicht erreichbar")

    monkeypatch.setenv("EIGENTUEMER_SMTP_HOST", "mail.example.invalid")
    monkeypatch.setattr(mail.smtplib, "SMTP", kaputt)

    antwort = client.post("/api/einreichung", data=formular(), files=nachweis())

    assert antwort.status_code == 200, "die Einreichung muss trotzdem durchgehen"
    assert antwort.json()["nummer"].startswith("KP-")


def test_ohne_smtp_wird_nur_geloggt(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("EIGENTUEMER_DATEN", str(tmp_path))
    monkeypatch.delenv("EIGENTUEMER_SMTP_HOST", raising=False)
    with caplog.at_level("INFO"):
        verschickt = mail._versenden(["jemand@example.invalid"], "Test", "Inhalt")
    assert verschickt is False
    assert "[KEIN VERSAND]" in caplog.text


def test_ohne_interne_empfaenger_keine_interne_mail(client, versand, monkeypatch):
    monkeypatch.setenv("EIGENTUEMER_INTERN_AN", "")
    client.post("/api/einreichung", data=formular(), files=nachweis())
    assert all("objekte@kromeichpartner.de" not in m[0] for m in versand)
