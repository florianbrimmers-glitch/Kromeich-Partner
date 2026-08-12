"""Propstack als primäre Datenquelle.

Die Aufgabe hielt Propstack für ungeeignet ("944/1018 ohne Preis"), notierte
aber den Nebenbefund "/units liefert nur 20 Einheiten". Der bestehende
objekte_handler schickt `per`, der propstack-pipeline-report-Skill `per_page`
– die Vermutung ist, dass `per` ignoriert wird und die Antwort auf die
Default-Seitengröße 20 zurückfällt. Diese Tests sichern die Paginierung und
die Feld-Auflösung ab, damit dieselbe Falle nicht erneut zuschlägt.
"""

from comparables_handler import config, normalize, propstack_gateway
from comparables_handler.models import PropstackReport


def _unit(**kw) -> dict:
    basis = {
        "id": 2778398,
        "name": "Logistikhalle in (59) Bergkamen",
        "street": "Industriestraße",
        "house_number": "12",
        "zip_code": "59192",
        "city": "Bergkamen",
        "marketing_type": "RENT",
        "rs_category": "HALL",
        "net_floor_space": 5000,
        "base_rent": 22900,          # absolut: 5000 m² * 4,58 €/m²
        "service_charge": 10750,     # absolut: 5000 m² * 2,15 €/m²
        "rented": False,
        "updated_at": "2026-07-01T10:00:00Z",
        "broker": {"id": 259613, "name": "Oguzhan Sahin"},
    }
    basis.update(kw)
    return basis


# --- Zahl-Parsing ----------------------------------------------------------
def test_deutsche_betraege_werden_gelesen():
    """Mieten stehen in Custom Fields oft als Text."""
    assert propstack_gateway.zu_zahl("4,58") == 4.58
    assert propstack_gateway.zu_zahl("4,58 €/m²") == 4.58
    assert propstack_gateway.zu_zahl("22.900,00 €") == 22900.0
    assert propstack_gateway.zu_zahl("1.234.567") == 1234567.0
    assert propstack_gateway.zu_zahl(4.58) == 4.58
    assert propstack_gateway.zu_zahl("4.58") == 4.58


def test_leere_und_unsinnige_werte():
    assert propstack_gateway.zu_zahl(None) is None
    assert propstack_gateway.zu_zahl("") is None
    assert propstack_gateway.zu_zahl("auf Anfrage") is None
    assert propstack_gateway.zu_zahl(True) is None


def test_custom_field_objekt_wird_entpackt():
    assert propstack_gateway.skalar({"label": "Kaltmiete", "value": "4,58"}) == "4,58"
    assert propstack_gateway.zu_zahl({"label": "Kaltmiete", "value": "4,58"}) == 4.58


# --- Feld-Auflösung --------------------------------------------------------
def test_kaltmiete_aus_standardfeld():
    wert, feld = propstack_gateway.hole_betrag(
        _unit(), config.KALTMIETE_FELDER, config.CUSTOM_FIELD_MIETE_MARKER,
    )
    assert wert == 22900.0
    assert feld == "base_rent"


def test_kaltmiete_aus_custom_field_wenn_standardfeld_leer():
    unit = _unit(base_rent=None, price=None)
    unit["custom_fields"] = {"kaltmiete_qm": "4,58 €/m²"}
    wert, feld = propstack_gateway.hole_betrag(
        unit, config.KALTMIETE_FELDER, config.CUSTOM_FIELD_MIETE_MARKER,
    )
    assert wert == 4.58
    assert feld == "custom_fields.kaltmiete_qm"


def test_null_betrag_gilt_als_nicht_gesetzt():
    """base_rent=0 ist 'nicht erfasst', nicht 'Miete null'."""
    wert, _ = propstack_gateway.hole_betrag(
        _unit(base_rent=0), config.KALTMIETE_FELDER, config.CUSTOM_FIELD_MIETE_MARKER,
    )
    assert wert is None


def test_flaeche_in_prioritaetsreihenfolge():
    wert, feld = propstack_gateway.hole_flaeche(_unit())
    assert (wert, feld) == (5000.0, "net_floor_space")
    wert, feld = propstack_gateway.hole_flaeche(_unit(net_floor_space=None, total_floor_space=8000))
    assert (wert, feld) == (8000.0, "total_floor_space")


def test_mietobjekt_erkennung():
    assert propstack_gateway.ist_mietobjekt(_unit())
    assert propstack_gateway.ist_mietobjekt(_unit(marketing_type="BUY", for_rent=True))
    assert not propstack_gateway.ist_mietobjekt(_unit(marketing_type="BUY", for_rent=False))


def test_preis_auf_anfrage_auch_verschachtelt():
    """Im GET steht das Flag unter furnishings (laut Exposé-Workflow-Skill)."""
    assert propstack_gateway.preis_auf_anfrage(_unit(price_on_inquiry=True))
    assert propstack_gateway.preis_auf_anfrage(_unit(furnishings={"price_on_inquiry": True}))
    assert not propstack_gateway.preis_auf_anfrage(_unit())


# --- Mapping auf Report-Zeilen --------------------------------------------
def test_absolute_miete_wird_auf_qm_normalisiert():
    """22.900 € auf 5.000 m² -> 4,58 €/m² (der verifizierte Referenzwert)."""
    stat = PropstackReport()
    zeile = normalize.propstack_zu_zeile(_unit(), stat)
    assert zeile.kaltmiete_eur_qm == 4.58
    assert zeile.nebenkosten_eur_qm == 2.15
    assert zeile.normalisiert_aus_absolut is True
    assert zeile.region_key == "59"
    assert zeile.quelle == "propstack"
    assert zeile.verwertbar
    assert stat.mit_miete == 1
    assert stat.miete_felder == {"base_rent": 1}


def test_qm_miete_wird_nicht_noch_einmal_geteilt():
    """Steht die Miete schon als €/m² drin, darf nicht durch die Fläche geteilt werden."""
    unit = _unit(base_rent=4.58, service_charge=2.15)
    zeile = normalize.propstack_zu_zeile(unit, PropstackReport())
    assert zeile.kaltmiete_eur_qm == 4.58
    assert zeile.nebenkosten_eur_qm == 2.15
    assert zeile.normalisiert_aus_absolut is False


def test_absolute_miete_ohne_flaeche_faellt_als_ausreisser_auf():
    """Kein stiller Fehler: ohne Fläche bleibt der Betrag stehen und wird
    von der Plausibilitätsprüfung mit Grund aussortiert."""
    unit = _unit(net_floor_space=None, total_floor_space=None, usable_floor_space=None,
                 industrial_area=None, property_space_value=None, living_space=None)
    zeile = normalize.propstack_zu_zeile(unit, PropstackReport())
    assert not zeile.verwertbar
    assert "außerhalb" in zeile.ausschluss_grund


def test_einheit_ohne_miete_bleibt_mit_grund_im_datensatz():
    """Grundlage der Abdeckungsaussage – solche Zeilen dürfen nicht verschwinden."""
    stat = PropstackReport()
    unit = _unit(base_rent=None, price=None, price_on_inquiry=True)
    zeile = normalize.propstack_zu_zeile(unit, stat)
    assert zeile is not None
    assert not zeile.verwertbar
    assert zeile.ausschluss_grund == "keine Kaltmiete extrahierbar"
    assert stat.ohne_miete == 1
    assert stat.preis_auf_anfrage == 1


def test_kaufobjekt_wird_nicht_zur_zeile():
    stat = PropstackReport()
    assert normalize.propstack_zu_zeile(_unit(marketing_type="BUY", for_rent=False), stat) is None
    assert stat.keine_mietobjekte == 1


def test_vermietete_einheit_wird_markiert():
    stat = PropstackReport()
    zeile = normalize.propstack_zu_zeile(_unit(rented=True), stat)
    assert zeile.vermietet is True
    assert zeile.option_hinweis == "vermietet"
    assert stat.vermietet == 1


def test_propstack_zeilen_gelten_als_eigene_angebote():
    zeile = normalize.propstack_zu_zeile(_unit(), PropstackReport())
    assert zeile.eigenes_angebot is True


def test_adresse_wird_zusammengesetzt():
    zeile = normalize.propstack_zu_zeile(_unit(), PropstackReport())
    assert zeile.adresse == "Industriestraße 12"


def test_ohne_plz_keine_region():
    zeile = normalize.propstack_zu_zeile(_unit(zip_code=None), PropstackReport())
    assert not zeile.verwertbar
    assert "PLZ" in zeile.ausschluss_grund


# --- Paginierung -----------------------------------------------------------
class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload


def _fake_units(start: int, anzahl: int) -> list[dict]:
    return [_unit(id=start + i) for i in range(anzahl)]


def test_paginierung_holt_alle_seiten(monkeypatch):
    """Der eigentliche Kern: nicht bei 20 (oder 100) stehenbleiben."""
    seiten = {1: _fake_units(1, 100), 2: _fake_units(101, 100), 3: _fake_units(201, 30)}
    gesendet = []

    def fake_request(path, params):
        gesendet.append(params)
        return _FakeResponse(seiten.get(params["page"], []))

    monkeypatch.setattr(propstack_gateway, "_request", fake_request)
    units = propstack_gateway.fetch_units()

    assert len(units) == 230
    # per_page MUSS mitgeschickt werden – 'per' allein liefert nur 20
    assert all(p["per_page"] == 100 for p in gesendet)
    assert [p["page"] for p in gesendet] == [1, 2, 3]


def test_paginierung_bricht_ab_wenn_page_ignoriert_wird(monkeypatch):
    """Liefert der Endpoint immer dieselbe Seite, darf es keine Endlosschleife geben."""
    immer_gleich = _fake_units(1, 100)
    aufrufe = []

    def fake_request(path, params):
        aufrufe.append(params["page"])
        return _FakeResponse(immer_gleich)

    monkeypatch.setattr(propstack_gateway, "_request", fake_request)
    units = propstack_gateway.fetch_units()

    assert len(units) == 100
    assert len(aufrufe) == 2      # zweite Seite bringt keine neuen IDs -> Stop


def test_antwort_als_dict_wird_entpackt(monkeypatch):
    monkeypatch.setattr(
        propstack_gateway, "_request",
        lambda path, params: _FakeResponse(
            {"data": _fake_units(1, 5)} if params["page"] == 1 else {"data": []}
        ),
    )
    assert len(propstack_gateway.fetch_units()) == 5


def test_leere_erste_seite_ist_kein_fehler(monkeypatch):
    monkeypatch.setattr(propstack_gateway, "_request", lambda path, params: _FakeResponse([]))
    assert propstack_gateway.fetch_units() == []


# --- Quellen-Auswahl -------------------------------------------------------
def test_propstack_ist_die_standardquelle(monkeypatch):
    monkeypatch.delenv("QUELLE", raising=False)
    assert config.quelle() == "propstack"
    assert config.nutzt_propstack()
    assert not config.nutzt_drive()


def test_beide_quellen(monkeypatch):
    monkeypatch.setenv("QUELLE", "beide")
    assert config.nutzt_propstack()
    assert config.nutzt_drive()


def test_unbekannte_quelle_faellt_auf(monkeypatch):
    monkeypatch.setenv("QUELLE", "sharepoint")
    try:
        config.quelle()
    except RuntimeError as e:
        assert "unbekannt" in str(e)
    else:
        raise AssertionError("hätte scheitern müssen")
