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


def test_css_versteckt_nicht_aktive_bilder():
    """Regressionswächter für einen CSS-Konflikt, den kein Python-Test sieht:

    `.karte .bild img { display: block }` überstimmt das hidden-Attribut, weil ein
    Klassenselektor die Browser-Regel für [hidden] schlägt. Ohne die explizite
    Gegenregel liegen alle Bilder einer Karte gleichzeitig übereinander."""
    from pathlib import Path

    css = (Path(__file__).parents[2] / "hallentinder" / "static" / "styles.css").read_text()
    assert "img[hidden]" in css, "Regel .karte .bild img[hidden] { display: none } fehlt"
    assert css.index("img[hidden]") > css.index(".karte .bild img {"), \
        "die Gegenregel muss NACH der display:block-Regel stehen"
