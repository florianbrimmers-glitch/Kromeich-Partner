from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from eigentuemer import api
from eigentuemer.models import Status

from .fixtures import formular, objekt

PASSWORT = "test-passwort"
ZUGANG = ("florian", PASSWORT)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EIGENTUEMER_DATEN", str(tmp_path))
    monkeypatch.setenv("EIGENTUEMER_PRUEF_PASSWORT", PASSWORT)
    monkeypatch.delenv("EIGENTUEMER_SMTP_HOST", raising=False)
    with TestClient(api.app) as c:
        yield c


def nachweis(name="grundbuch.pdf"):
    return [("nachweis", (name, b"%PDF-1.4 test", "application/pdf"))]


def bild(name="foto.jpg"):
    return ("bilder", (name, b"\xff\xd8\xff-bild", "image/jpeg"))


def einreichen(client, **overrides):
    antwort = client.post("/api/einreichung", data=formular(**overrides), files=nachweis())
    assert antwort.status_code == 200
    return antwort.json()["token"]


def freigeben(client, vorgang_id=1):
    return client.post(f"/api/pruefung/{vorgang_id}/entscheidung", auth=ZUGANG,
                       json={"freigeben": True, "pruefer": "Florian"})


def aendern(client, token, **felder):
    daten = {**objekt().model_dump(), **felder}
    return client.put(f"/api/vorgang/{token}", data={"objekt": json.dumps(daten)})


def test_daten_aendern_ohne_erneute_pruefung(client):
    """Der Nachweis belegte die Verfügungsbefugnis, nicht die Ausstattung."""
    token = einreichen(client)
    freigeben(client)

    antwort = aendern(client, token, flaeche_qm=6100.0, miete_eur_qm=5.9,
                      beschreibung="Jetzt mit neuem Hallentor.")

    assert antwort.status_code == 200
    assert antwort.json()["status"] == "freigegeben", "Datenänderung darf nicht zurück in die Prüfung"
    objekte = client.get("/api/objekte").json()["objekte"]
    assert objekte[0]["flaeche_qm"] == 6100.0


def test_neue_adresse_braucht_neuen_nachweis(client):
    token = einreichen(client)
    freigeben(client)

    antwort = aendern(client, token, strasse="Ganz andere Straße", hausnummer="1")

    assert antwort.status_code == 400
    assert "Nachweis" in antwort.json()["detail"]
    assert client.get("/api/objekte").json()["objekte"][0]["adresse"].startswith("Mellinghofer")


def test_neue_adresse_mit_nachweis_geht_zurueck_in_die_pruefung(client):
    token = einreichen(client)
    freigeben(client)

    daten = {**objekt().model_dump(), "strasse": "Ganz andere Straße", "hausnummer": "1"}
    antwort = client.put(f"/api/vorgang/{token}", data={"objekt": json.dumps(daten)},
                         files=nachweis("neuer_grundbuchauszug.pdf"))

    assert antwort.status_code == 200
    assert antwort.json()["status"] == "in_pruefung"
    assert client.get("/api/objekte").json()["objekte"] == [], "nicht mehr öffentlich sichtbar"
    # der neue Nachweis liegt zur Prüfung bereit
    assert client.get("/api/pruefung/1/nachweis", auth=ZUGANG).status_code == 200


def test_gross_und_kleinschreibung_ist_keine_neue_adresse(client):
    token = einreichen(client)
    freigeben(client)
    antwort = aendern(client, token, strasse="mellinghofer  straße", stadt="MÜLHEIM AN DER RUHR")
    assert antwort.status_code == 200
    assert antwort.json()["status"] == "freigegeben"


def test_zurueckziehen_und_wieder_online(client):
    """Die häufigste Änderung: die Halle ist vermietet."""
    token = einreichen(client)
    freigeben(client)

    client.post(f"/api/vorgang/{token}/sichtbarkeit", data={"sichtbar": "false"})
    assert client.get("/api/objekte").json()["objekte"] == []
    assert client.get(f"/api/status/{token}").json()["status"] == "zurueckgezogen"

    client.post(f"/api/vorgang/{token}/sichtbarkeit", data={"sichtbar": "true"})
    assert len(client.get("/api/objekte").json()["objekte"]) == 1


def test_ungeprueftes_objekt_laesst_sich_nicht_online_stellen(client):
    token = einreichen(client)
    antwort = client.post(f"/api/vorgang/{token}/sichtbarkeit", data={"sichtbar": "true"})
    assert antwort.status_code == 409
    assert client.get("/api/objekte").json()["objekte"] == []


def test_fotos_ergaenzen_und_entfernen(client):
    token = einreichen(client)
    ergaenzt = client.post(f"/api/vorgang/{token}/bilder", files=[bild(), bild("zwei.jpg")])
    assert ergaenzt.status_code == 200
    assert ergaenzt.json()["bilder"] == ["bild_1.jpg", "bild_2.jpg"]

    entfernt = client.delete(f"/api/vorgang/{token}/bilder/bild_1.jpg")
    assert entfernt.json()["bilder"] == ["bild_2.jpg"]
    assert client.get(f"/api/vorgang/{token}/bild/bild_1.jpg").status_code == 404


def test_fremdes_foto_laesst_sich_nicht_entfernen(client):
    """Entscheidend ist nicht der Statuscode, sondern dass nichts verschwindet:
    der Nachweis liegt im selben Ordner wie die Fotos."""
    token = einreichen(client)
    client.post(f"/api/vorgang/{token}/bilder", files=[bild()])

    for versuch in ("nachweis.pdf", "..%2F..%2Fnachweis.pdf", "bild_9.jpg"):
        antwort = client.delete(f"/api/vorgang/{token}/bilder/{versuch}")
        assert antwort.status_code >= 400, versuch

    assert client.get("/api/pruefung/1/nachweis", auth=ZUGANG).status_code == 200, "Nachweis muss unberührt sein"
    assert client.get(f"/api/vorgang/{token}/bild/bild_1.jpg").status_code == 200, "eigenes Foto muss unberührt sein"


def test_eigene_fotos_schon_vor_der_freigabe_sichtbar(client):
    token = einreichen(client)
    client.post(f"/api/vorgang/{token}/bilder", files=[bild()])
    assert client.get(f"/api/vorgang/{token}/bild/bild_1.jpg").status_code == 200
    nummer = client.get("/api/pruefung/1", auth=ZUGANG).json()["nummer"]
    assert client.get(f"/api/bild/{nummer}/bild_1.jpg").status_code == 404


def test_falscher_token_aendert_nichts(client):
    einreichen(client)
    assert aendern(client, "gibtesnicht", flaeche_qm=99.0).status_code == 404


def test_verlauf_protokolliert_die_schritte(client):
    token = einreichen(client)
    freigeben(client)
    aendern(client, token, miete_eur_qm=6.5)
    client.post(f"/api/vorgang/{token}/sichtbarkeit", data={"sichtbar": "false"})

    verlauf = [e["text"] for e in client.get(f"/api/status/{token}").json()["verlauf"]]
    assert verlauf[0] == "Eingereicht"
    assert any("Freigegeben von Florian" in t for t in verlauf)
    assert any("Miete" in t for t in verlauf)
    assert any("zurückgezogen" in t for t in verlauf)
