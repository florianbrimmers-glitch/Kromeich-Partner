"""Gesuch-Abgleich (scripts/gesuch_matching.py) – ohne Netz.

Die Einheiten sind so aufgebaut, wie GET /v1/units?expand=1 sie am 19.11.2026 lieferte
(gekürzt): Felder teils als {label, value}, Lagerfläche/Höhe/Rampen als Custom-Felder,
Rampen als Text ("9") im Feld `ramepntore`.
"""
import importlib.util
from pathlib import Path

import pytest

_PFAD = Path(__file__).resolve().parents[2] / "scripts" / "gesuch_matching.py"
_spec = importlib.util.spec_from_file_location("gesuch_matching", _PFAD)
gm = importlib.util.module_from_spec(_spec)
import sys
sys.modules["gesuch_matching"] = gm   # dataclasses braucht das Modul in sys.modules
_spec.loader.exec_module(gm)

WERMELSKIRCHEN = (51.139, 7.215)


def _unit(unit_id, ort, lat, lng, lagerflache, *, hoehe=None, rampen=None, teilbar=None, status=163674,
          rented=False, archived=False, logistik="Aktiv", bezug=None, projekt=None):
    custom = {"lagerflache": lagerflache, "status_logistik": logistik}
    if hoehe is not None:
        custom["hallenhohe"] = hoehe
    if rampen is not None:
        custom["ramepntore"] = rampen
    if teilbar is not None:
        custom["lagerflache_teilbar_ab"] = teilbar
    if bezug:
        custom["bezug"] = bezug
    return {
        "id": unit_id, "name": f"Halle {unit_id}", "city": {"label": "Stadt", "value": ort},
        "lat": lat, "lng": lng, "archived": archived, "project_id": projekt,
        "property_status": {"id": status, "name": "Vermarktung"} if status else None,
        "rented": {"label": "Vermietet", "value": rented},
        "property_space_value": lagerflache, "custom_fields": custom,
    }


GESUCH = gm.Gesuch(*WERMELSKIRCHEN, umkreis_km=30, flaeche_von=8000, flaeche_bis=12000, hoehe_min=9, rampen_min=4)


@pytest.mark.parametrize("wert,erwartet", [
    (7575.0, 7575.0), ("7.575 m²", 7575.0), ("9", 9.0), ("9,5", 9.5), (12, 12.0),
    (None, None), ("", None), ("auf Anfrage", None), (True, None),
])
def test_zahl(wert, erwartet):
    assert gm.zahl(wert) == erwartet


def test_entfernung():
    # Wermelskirchen – Köln Dom: rund 28 km Luftlinie
    assert 26 <= gm.entfernung_km(*WERMELSKIRCHEN, 50.9413, 6.9583) <= 30


def test_passende_einheit():
    k = gm.pruefe(_unit(1, "Wuppertal", 51.25, 7.15, 10500.0, hoehe=10.5, rampen="20", bezug="Q2 2027", projekt=412177), GESUCH)
    assert (k.unit_id, k.flaeche, k.hoehe, k.rampen, k.luecken) == (1, 10500, 10.5, 20.0, [])
    assert k.bezug == "Q2 2027" and k.projekt_id == 412177


@pytest.mark.parametrize("unit", [
    _unit(2, "Hamburg", 53.55, 10.0, 10000.0, hoehe=10, rampen="8"),        # zu weit weg
    _unit(3, "Wuppertal", 51.25, 7.15, 3000.0, hoehe=10, rampen="8"),       # zu klein
    _unit(4, "Wuppertal", 51.25, 7.15, 30000.0, hoehe=10, rampen="8"),      # zu groß, nicht teilbar
    _unit(5, "Wuppertal", 51.25, 7.15, 10000.0, hoehe=6.5, rampen="8"),     # Höhe gepflegt und zu niedrig
    _unit(6, "Wuppertal", 51.25, 7.15, 10000.0, hoehe=10, rampen="2"),      # Rampen gepflegt und zu wenige
    _unit(7, "Wuppertal", None, None, 10000.0, hoehe=10, rampen="8"),       # ohne Koordinaten
])
def test_passt_nicht(unit):
    assert gm.pruefe(unit, GESUCH) is None


def test_groessere_einheit_passt_wenn_teilbar():
    k = gm.pruefe(_unit(8, "Remscheid", 51.18, 7.19, 30000.0, hoehe=12, rampen="30", teilbar="ab 9.000 m²"), GESUCH)
    assert k is not None and k.teilbar_ab == 9000


def test_fehlender_wert_ist_kein_ausschluss_sondern_eine_luecke():
    k = gm.pruefe(_unit(9, "Remscheid", 51.18, 7.19, 9000.0), GESUCH)
    assert k is not None and k.luecken == ["Hallenhöhe", "Rampen"]


@pytest.mark.parametrize("aenderung", [
    {"status": 163676}, {"status": None}, {"rented": True}, {"archived": True}, {"logistik": "Inaktiv"},
])
def test_nur_was_in_vermarktung_ist(aenderung):
    assert gm.in_vermarktung(_unit(1, "Wuppertal", 51.25, 7.15, 10000.0)) is True
    assert gm.in_vermarktung(_unit(1, "Wuppertal", 51.25, 7.15, 10000.0, **aenderung)) is False


def test_finde_sortiert_und_zaehlt_die_unsichtbaren():
    units = [
        _unit(1, "Köln", 50.99, 7.0, 9000.0),                                      # Lücken
        _unit(2, "Wuppertal", 51.25, 7.15, 10500.0, hoehe=10.5, rampen="20"),      # vollständig, 13 km
        _unit(3, "Remscheid", 51.18, 7.19, 11000.0, hoehe=12, rampen="6"),         # vollständig, 5 km
        _unit(4, "Solingen", None, None, 10000.0, hoehe=12, rampen="6"),           # ohne Koordinaten
        _unit(5, "Wuppertal", 51.25, 7.15, 10000.0, hoehe=12, rampen="6", rented=True),
    ]
    kandidaten, verfuegbar, ohne_koordinaten = gm.finde(units, GESUCH)
    assert [k.unit_id for k in kandidaten] == [3, 2, 1]
    assert (verfuegbar, ohne_koordinaten) == (4, 1)


def test_ortsmitte_aus_dem_eigenen_bestand():
    units = [_unit(1, "Köln", 50.94, 6.96, 1.0), _unit(2, "Köln-Ossendorf", 50.98, 6.90, 1.0), _unit(3, "Bonn", 50.73, 7.1, 1.0)]
    lat, lng = gm.ortsmitte(units, "köln")
    assert round(lat, 2) == 50.96 and round(lng, 2) == 6.93
    assert gm.ortsmitte(units, "Wermelskirchen") is None


def test_flaeche_als_bereich_oder_einzelne_zahl():
    assert gm._bereich("8000-12000") == (8000.0, 12000.0)
    assert gm._bereich("8.000 – 12.000") == (8000.0, 12000.0)
    assert gm._bereich("10000") == (8500.0, 11500.0)
    with pytest.raises(Exception):
        gm._bereich("viel")
