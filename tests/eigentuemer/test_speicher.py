from __future__ import annotations

import pytest

from eigentuemer import config, speicher
from eigentuemer.models import Nachweisart, Rolle, Status

from .fixtures import NACHWEIS, kontakt, objekt


@pytest.fixture(autouse=True)
def eigenes_verzeichnis(tmp_path, monkeypatch):
    monkeypatch.setenv("EIGENTUEMER_DATEN", str(tmp_path))
    speicher.init()


def anlegen(rolle=Rolle.EIGENTUEMER, bilder=None):
    return speicher.anlegen(rolle, kontakt(), objekt(), NACHWEIS, bilder or [])


def test_vorgangsnummern_laufen_hoch():
    erste, zweite = anlegen(), anlegen()
    assert erste.nummer.endswith("0001")
    assert zweite.nummer.endswith("0002")
    assert erste.nummer.startswith(config.NUMMER_PRAEFIX)


def test_nachweisart_folgt_der_rolle():
    assert anlegen(Rolle.EIGENTUEMER).nachweis_art is Nachweisart.GRUNDBUCHAUSZUG
    assert anlegen(Rolle.MAKLER).nachweis_art is Nachweisart.ALLEINVERMARKTUNGSAUFTRAG


def test_nachweis_wird_nach_der_pruefung_geloescht():
    """Der Kern des Datenschutzversprechens: der Grundbuchauszug verschwindet."""
    einreichung = anlegen()
    pfad = speicher.nachweis_pfad(einreichung)
    assert pfad is not None and pfad.exists()

    nachher = speicher.entscheiden(einreichung.id, freigeben=True, pruefer="Florian")

    assert not pfad.exists(), "die Nachweisdatei muss weg sein"
    assert nachher.nachweis_dateiname is None
    assert speicher.nachweis_pfad(nachher) is None


def test_protokoll_bleibt_nach_dem_loeschen():
    einreichung = anlegen()
    nachher = speicher.entscheiden(einreichung.id, freigeben=True, pruefer="Florian")
    assert nachher.geprueft_von == "Florian"
    assert nachher.geprueft_am
    assert nachher.nachweis_art is Nachweisart.GRUNDBUCHAUSZUG, "Art des Nachweises bleibt dokumentiert"


def test_ablehnung_mit_grund():
    einreichung = anlegen()
    nachher = speicher.entscheiden(einreichung.id, freigeben=False, pruefer="Lena", grund="Auszug zu alt")
    assert nachher.status is Status.ABGELEHNT
    assert nachher.ablehnungsgrund == "Auszug zu alt"


def test_bilder_werden_durchnummeriert_abgelegt():
    einreichung = anlegen(bilder=[("bild.jpg", b"aaa"), ("bild.png", b"bbb")])
    assert einreichung.bilder == ["bild_1.jpg", "bild_2.png"]
    assert speicher.bild_pfad(einreichung, "bild_1.jpg").read_bytes() == b"aaa"


def test_fremder_bildname_wird_nicht_ausgeliefert():
    """Der Name kommt aus der URL – nur was in der Liste steht, darf raus."""
    einreichung = anlegen(bilder=[("bild.jpg", b"aaa")])
    for versuch in ("../../../etc/passwd", "nachweis.pdf", "bild_2.jpg"):
        assert speicher.bild_pfad(einreichung, versuch) is None, versuch


def test_token_findet_den_vorgang_und_ist_nicht_die_id():
    einreichung = anlegen()
    assert speicher.holen_per_token(einreichung.token).id == einreichung.id
    assert str(einreichung.id) != einreichung.token
    assert len(einreichung.token) >= 16


def test_liste_filtert_nach_status():
    offen, freigegeben = anlegen(), anlegen()
    speicher.entscheiden(freigegeben.id, freigeben=True, pruefer="Florian")
    assert [e.id for e in speicher.liste(Status.IN_PRUEFUNG)] == [offen.id]
    assert [e.id for e in speicher.liste(Status.FREIGEGEBEN)] == [freigegeben.id]
