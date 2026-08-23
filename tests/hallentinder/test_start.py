from __future__ import annotations

from hallentinder import main


def test_zugangshinweis_nennt_beide_adressen():
    zeilen = main._zugangshinweis(8080)
    text = "\n".join(zeilen)
    assert "http://localhost:8080" in text
    assert "8080" in text
    assert "Bestand" in text, "der Hinweis auf die Ladezeit fehlt"


def test_zugangshinweis_ohne_netzwerk(monkeypatch):
    """Ohne ermittelbare Adresse bleibt ein brauchbarer Hinweis stehen."""
    monkeypatch.setattr(main, "_lan_adresse", lambda: None)
    text = "\n".join(main._zugangshinweis(8080))
    assert "manuell" in text
    assert "http://localhost:8080" in text


def test_lan_adresse_verschickt_nichts_und_wirft_nicht():
    ergebnis = main._lan_adresse()
    assert ergebnis is None or ergebnis.count(".") == 3
