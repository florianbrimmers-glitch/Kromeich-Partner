from __future__ import annotations

from hallentinder import catalog, config
from hallentinder.models import HallCard

from .fixtures import unit


def test_custom_field_objekte_werden_entpackt():
    """Propstack liefert manche Felder als {"label":…, "value":…}."""
    karte = catalog.to_card(unit(
        house_number={"label": "Hausnummer", "value": "12a"},
        city={"label": "Stadt", "value": "Bremen"},
        property_space_value={"label": "Fläche", "value": "3.500"},
    ))
    assert karte.strasse == "Musterstraße 12a"
    assert karte.stadt == "Bremen"
    assert karte.flaeche == 3500.0


def test_karte_enthaelt_keine_internen_felder():
    """Die Whitelist ist der Datenschutz-Kern: Rohfelder dürfen nicht durchrutschen."""
    karte = catalog.to_card(unit(broker={"id": 1, "name": "Intern"}, internal_note="geheim"))
    daten = karte.model_dump()
    assert "broker" not in daten
    assert "internal_note" not in daten
    assert set(daten) <= set(HallCard.model_fields)


def test_zahlen_in_deutscher_schreibweise():
    """3.500 sind dreieinhalbtausend Quadratmeter, 8.5 sind achteinhalb Meter."""
    assert catalog._zahl("3.500") == 3500.0
    assert catalog._zahl("8.5") == 8.5
    assert catalog._zahl("1.234,56") == 1234.56
    assert catalog._zahl("3,5") == 3.5
    assert catalog._zahl(True) is None
    assert catalog._zahl("keine Angabe") is None


def test_vermietete_objekte_fliegen_raus():
    assert catalog.ist_verfuegbare_halle(unit(rented=True)) is False
    assert catalog.ist_verfuegbare_halle(unit(rented={"label": "Vermietet", "value": True})) is False


def test_wohnimmobilien_fliegen_raus():
    assert catalog.ist_verfuegbare_halle(unit(rs_category="Wohnung", title="Wohnung")) is False


def test_reine_kaufobjekte_fliegen_raus():
    assert catalog.ist_verfuegbare_halle(unit(marketing_type="BUY")) is False
    assert catalog.ist_verfuegbare_halle(unit(marketing_type="RENT_AND_BUY")) is True


def test_unklare_kategorie_bleibt_drin_ausser_bei_strict(monkeypatch):
    unklar = unit(rs_category=None, rs_type=None, object_type=None, title="Objekt", name="Objekt")
    assert catalog.ist_verfuegbare_halle(unklar) is True
    monkeypatch.setenv("HALLENTINDER_STRICT_HALLE", "true")
    assert config.strict_halle() is True
    assert catalog.ist_verfuegbare_halle(unklar) is False
    assert catalog.ist_verfuegbare_halle(unit(rs_category=None, hall_height=8.5, title="Objekt", name="Objekt")) is True


def test_build_cards_ueberspringt_kaputte_eintraege():
    karten = catalog.build_cards([unit(id=1), {"kein": "id"}, unit(id=2, rented=True)])
    assert [k.id for k in karten] == [1]


def test_bild_url_aus_verschiedenen_formen():
    assert catalog._bild_url({"images": [{"big_url": "https://x/1.jpg"}]}) == "https://x/1.jpg"
    assert catalog._bild_url({"title_picture": {"url": "https://x/2.jpg"}}) == "https://x/2.jpg"
    assert catalog._bild_url({}) is None
