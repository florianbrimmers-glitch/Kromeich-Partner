from comparables_handler import regions


def test_plz_aus_freitext():
    assert regions.normalize_plz("59192 Bergkamen") == "59192"
    assert regions.normalize_plz("D-06749 Bitterfeld") == "06749"
    assert regions.normalize_plz("Bergkamen") is None
    assert regions.normalize_plz(None) is None


def test_vierstellige_zahl_ist_keine_plz():
    assert regions.normalize_plz("Halle 2026") is None


def test_leitregionen_der_echten_objekte():
    """Die Regionen aus der Asana-Aufgabe: Bergkamen, Bitterfeld, Burbach, Dortmund."""
    assert regions.leitregion("59192")[0] == "59"
    assert "Bergkamen" in regions.leitregion("59192")[1]
    assert regions.leitregion("06749")[0] == "06"
    assert "Bitterfeld" in regions.leitregion("06749")[1]
    assert regions.leitregion("57299")[0] == "57"
    assert "Burbach" in regions.leitregion("57299")[1]
    assert regions.leitregion("44145")[0] == "44"
    assert regions.leitregion("44145")[1] == "Dortmund"


def test_kaltenkirchen_und_glandorf():
    assert "Kaltenkirchen" in regions.leitregion("24568")[1]
    assert "Glandorf" in regions.leitregion("49219")[1]


def test_unbekannte_leitregion_bekommt_neutrales_label():
    key, label = regions.leitregion("23966")
    assert key == "23"
    assert label == "PLZ-Gebiet 23"


def test_postleitzonen():
    assert regions.zone("59192")[0] == "5"
    assert regions.zone("06749")[0] == "0"
    assert "Sachsen" in regions.zone("06749")[1]
    assert regions.zone("80331")[0] == "8"
    assert "München" in regions.zone("80331")[1]


def test_ohne_plz_keine_region():
    assert regions.leitregion(None) is None
    assert regions.zone("keine Angabe") is None


def test_alle_zonen_haben_ein_label():
    for ziffer in "0123456789":
        assert regions.zone(f"{ziffer}0000")[1]
