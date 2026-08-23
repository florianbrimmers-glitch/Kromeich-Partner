from __future__ import annotations

import pytest

from hallentinder import catalog, config, ranking
from hallentinder.models import SearchProfile

from .fixtures import BESTAND, unit


def karten():
    return catalog.build_cards(BESTAND)


@pytest.fixture
def ohne_erweiterung(monkeypatch):
    """Radius-Erweiterung abschalten, um den reinen Filter zu prüfen."""
    monkeypatch.setattr(config, "MIN_CARDS_BEFORE_EXPANSION", 0)


def profil(**overrides) -> SearchProfile:
    basis = {"ort": "49076", "flaeche_min": 3000, "flaeche_max": 6000, "radius_km": 50}
    basis.update(overrides)
    return SearchProfile(**basis)


def test_umkreis_filtert_entfernte_objekte(ohne_erweiterung):
    treffer, zentrum, radius = ranking.rangliste(karten(), profil())
    assert zentrum.quelle == "plz"
    assert radius == 50
    # Münster (id 3) liegt ~46 km entfernt und ist damit noch im Umkreis, Hamburg/München nicht
    assert [k.id for k in treffer] == [1, 3]


def test_ortsname_wird_ueber_den_bestand_aufgeloest(ohne_erweiterung):
    treffer, zentrum, _ = ranking.rangliste(karten(), profil(ort="Osnabrück"))
    assert zentrum.quelle == "bestand"
    assert [k.id for k in treffer] == [1, 3]


def test_unbekannte_region_liefert_trotzdem_karten():
    treffer, zentrum, _ = ranking.rangliste(karten(), profil(ort="Nirgendwo"))
    assert zentrum.bekannt() is False
    # Nur der Flächenfilter greift: 1200 m² (id 2) liegt unter 3000*0.6, alles andere bleibt
    assert {k.id for k in treffer} == {1, 3, 4, 5}
    assert all(k.entfernung_km is None for k in treffer)


def test_flaechenfilter_mit_toleranz(ohne_erweiterung):
    treffer, _, _ = ranking.rangliste(karten(), profil(ort="Nirgendwo", flaeche_min=5000, flaeche_max=5000))
    # 5000 ±: 3000–8000 → 4000er und 6000er sind noch dabei, 1200 und 9000 nicht
    assert {k.id for k in treffer} == {1, 4, 5}


def test_radius_wird_erweitert_wenn_zu_wenige_treffer():
    treffer, _, radius = ranking.rangliste(karten(), profil(ort="80939", radius_km=25))
    assert radius > 25
    assert treffer, "Erweiterung soll ein leeres Deck verhindern"


def test_reihenfolge_ist_deterministisch_und_nach_entfernung(ohne_erweiterung):
    bestand = [
        unit(id=10, lat=52.28, lng=8.05, property_space_value=5000),
        unit(id=11, lat=52.10, lng=8.05, property_space_value=5000),
        unit(id=12, lat=52.28, lng=8.05, property_space_value=5000),
    ]
    p = profil()
    erste, _, _ = ranking.rangliste(catalog.build_cards(bestand), p)
    zweite, _, _ = ranking.rangliste(catalog.build_cards(bestand), p)
    assert [k.id for k in erste] == [k.id for k in zweite]
    assert [k.id for k in erste] == [10, 12, 11]


def test_objekte_ohne_flaeche_bleiben_drin_aber_hinten(ohne_erweiterung):
    bestand = [
        unit(id=20, property_space_value=None, industrial_area=None,
             usable_floor_space=None, net_floor_space=None, total_floor_space=None),
        unit(id=21, property_space_value=5000),
    ]
    treffer, _, _ = ranking.rangliste(catalog.build_cards(bestand), profil())
    assert [k.id for k in treffer] == [21, 20]


def test_entfernung_wird_an_die_karte_geschrieben(ohne_erweiterung):
    treffer, _, _ = ranking.rangliste(karten(), profil(radius_km=200))
    per_id = {k.id: k.entfernung_km for k in treffer}
    assert per_id[1] == 0.0
    assert 40 < per_id[3] < 70  # Osnabrück → Münster
