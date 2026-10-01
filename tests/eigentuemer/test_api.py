from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from eigentuemer import api, speicher
from eigentuemer.models import Status

from .fixtures import formular, kontakt, objekt

PASSWORT = "test-passwort"
ZUGANG = ("florian", PASSWORT)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EIGENTUEMER_DATEN", str(tmp_path))
    monkeypatch.setenv("EIGENTUEMER_PRUEF_PASSWORT", PASSWORT)
    with TestClient(api.app) as c:
        yield c


def dateien(nachweis=("grundbuch.pdf", b"%PDF-1.4 test", "application/pdf"), bilder=()):
    liste = [("nachweis", nachweis)]
    liste += [("bilder", b) for b in bilder]
    return liste


def einreichen(client, **overrides):
    return client.post("/api/einreichung", data=formular(**overrides), files=dateien())


def test_einreichung_legt_vorgang_an(client):
    antwort = einreichen(client)
    assert antwort.status_code == 200
    daten = antwort.json()
    assert daten["nummer"].startswith("KP-")
    assert daten["nachweis_art"] == "grundbuchauszug"
    assert daten["token"] in daten["status_url"]


def test_ohne_einwilligung_keine_einreichung(client):
    antwort = client.post("/api/einreichung", data=formular(einwilligung="false"), files=dateien())
    assert antwort.status_code == 400
    assert "Einwilligung" in antwort.json()["detail"]


def test_falscher_dateityp_wird_abgewiesen(client):
    antwort = client.post(
        "/api/einreichung", data=formular(),
        files=dateien(nachweis=("schad.exe", b"MZ", "application/x-msdownload")),
    )
    assert antwort.status_code == 400
    assert "Nachweis" in antwort.json()["detail"]


def test_zu_grosser_nachweis_wird_abgewiesen(client, monkeypatch):
    monkeypatch.setattr(api.config, "MAX_NACHWEIS_BYTES", 100)
    antwort = client.post(
        "/api/einreichung", data=formular(),
        files=dateien(nachweis=("gross.pdf", b"x" * 500, "application/pdf")),
    )
    assert antwort.status_code == 413


def test_unvollstaendige_objektdaten_nennen_das_feld(client):
    kaputt = json.dumps({**objekt().model_dump(), "plz": "abcde"})
    antwort = client.post("/api/einreichung", data=formular(objekt=kaputt), files=dateien())
    assert antwort.status_code == 400
    assert "plz" in antwort.json()["detail"].lower()


def test_status_ist_ueber_den_token_abrufbar(client):
    token = einreichen(client).json()["token"]
    daten = client.get(f"/api/status/{token}").json()
    assert daten["status"] == "in_pruefung"
    assert daten["nachweis_geloescht"] is False
    assert "Mellinghofer" in daten["adresse"]


def test_unbekannter_token_gibt_404(client):
    assert client.get("/api/status/gibtesnicht").status_code == 404


def test_pruefansicht_ohne_zugang_gesperrt(client):
    einreichen(client)
    for pfad in ("/api/pruefung", "/api/pruefung/1", "/api/pruefung/1/nachweis"):
        assert client.get(pfad).status_code == 401, pfad
    assert client.get("/api/pruefung", auth=("florian", "falsch")).status_code == 401


def test_pruefliste_zeigt_keine_kontaktdaten(client):
    einreichen(client)
    vorgang = client.get("/api/pruefung", auth=ZUGANG).json()["vorgaenge"][0]
    assert "kontakt" not in vorgang, "die Übersicht braucht keine personenbezogenen Daten"
    assert vorgang["nachweis_vorhanden"] is True


def test_detail_zeigt_kontakt_und_nachweis(client):
    einreichen(client)
    detail = client.get("/api/pruefung/1", auth=ZUGANG).json()
    assert detail["kontakt"]["email"] == kontakt().email
    nachweis = client.get("/api/pruefung/1/nachweis", auth=ZUGANG)
    assert nachweis.status_code == 200
    assert nachweis.content.startswith(b"%PDF")


def test_freigabe_loescht_den_nachweis_und_veroeffentlicht(client):
    einreichen(client)
    antwort = client.post("/api/pruefung/1/entscheidung", auth=ZUGANG,
                          json={"freigeben": True, "pruefer": "Florian"})
    assert antwort.status_code == 200
    assert antwort.json()["status"] == "freigegeben"

    weg = client.get("/api/pruefung/1/nachweis", auth=ZUGANG)
    assert weg.status_code == 410, "der Nachweis darf danach nicht mehr abrufbar sein"

    objekte = client.get("/api/objekte").json()["objekte"]
    assert len(objekte) == 1
    assert objekte[0]["herkunft"] == "Direkt vom Eigentümer"


def test_oeffentliche_liste_verraet_den_einsender_nicht(client):
    einreichen(client)
    client.post("/api/pruefung/1/entscheidung", auth=ZUGANG, json={"freigeben": True, "pruefer": "F"})
    roh = client.get("/api/objekte").text
    assert kontakt().email not in roh
    assert kontakt().nachname not in roh


def test_ablehnung_braucht_einen_grund(client):
    einreichen(client)
    ohne = client.post("/api/pruefung/1/entscheidung", auth=ZUGANG,
                       json={"freigeben": False, "pruefer": "Florian"})
    assert ohne.status_code == 400

    mit = client.post("/api/pruefung/1/entscheidung", auth=ZUGANG,
                      json={"freigeben": False, "pruefer": "Florian", "grund": "Auszug zu alt"})
    assert mit.status_code == 200
    token = client.get("/api/pruefung/1", auth=ZUGANG).json()
    assert token["ablehnungsgrund"] == "Auszug zu alt"


def test_zweite_entscheidung_wird_abgelehnt(client):
    einreichen(client)
    client.post("/api/pruefung/1/entscheidung", auth=ZUGANG, json={"freigeben": True, "pruefer": "F"})
    nochmal = client.post("/api/pruefung/1/entscheidung", auth=ZUGANG,
                          json={"freigeben": False, "pruefer": "F", "grund": "doch nicht"})
    assert nochmal.status_code == 409


def test_bilder_erst_nach_der_freigabe_abrufbar(client):
    bild = ("foto.jpg", b"\xff\xd8\xff-bilddaten", "image/jpeg")
    client.post("/api/einreichung", data=formular(), files=dateien(bilder=[bild]))
    nummer = client.get("/api/pruefung/1", auth=ZUGANG).json()["nummer"]

    assert client.get(f"/api/bild/{nummer}/bild_1.jpg").status_code == 404

    client.post("/api/pruefung/1/entscheidung", auth=ZUGANG, json={"freigeben": True, "pruefer": "F"})
    assert client.get(f"/api/bild/{nummer}/bild_1.jpg").status_code == 200


def test_makler_braucht_den_vermarktungsauftrag(client):
    antwort = einreichen(client, rolle="makler")
    assert antwort.json()["nachweis_art"] == "alleinvermarktungsauftrag"
    client.post("/api/pruefung/1/entscheidung", auth=ZUGANG, json={"freigeben": True, "pruefer": "F"})
    assert client.get("/api/objekte").json()["objekte"][0]["herkunft"] == "Über Vermarktungsmandat"


def test_startseite_und_pruefseite_werden_ausgeliefert(client):
    assert "Halle einstellen" in client.get("/").text
    assert client.get("/pruefung.html").status_code == 200


def test_zugangsabfrage_ist_latin1_kodierbar():
    """Der Realm landet in einem HTTP-Header. Ein Gedankenstrich darin sorgte
    dafür, dass die Anmeldeaufforderung mit einem Serverfehler endete."""
    api.REALM.encode("latin-1")
