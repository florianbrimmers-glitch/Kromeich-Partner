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


def _unit(custom=None, **kw) -> dict:
    """Eine Propstack-Einheit in der ECHTEN Feldstruktur (gemessen 12.08.2026).

    Mieten liegen in Custom Fields, je Flächenart getrennt und bereits als
    €/m². Werte kommen als {"value": …, "pretty_value": …}, Standardfelder
    als {"label": …, "value": …}.
    """
    custom_fields = {
        "lagerflache": {"value": 5000.0, "pretty_value": "5.000 m²"},
        "buroflache": {"value": 400.0, "pretty_value": "400 m²"},
        "intern_mietpreis_hallenflache": {"value": 4.58, "pretty_value": "4,58 €"},
        "nebenkosten": {"value": 2.15, "pretty_value": "2,15 €"},
    }
    custom_fields.update(custom or {})
    basis = {
        "id": 2778398,
        "name": "Logistikhalle in (59) Bergkamen",
        "street": "Industriestraße",
        "house_number": "12",
        "zip_code": "59192",
        "city": "Bergkamen",
        "marketing_type": "RENT",
        "rs_category": "HALL",
        "rented": {"label": "Vermietet", "value": False},
        "updated_at": "2026-07-01T10:00:00Z",
        "broker": {"id": 259613, "name": "Oguzhan Sahin"},
        "custom_fields": custom_fields,
    }
    basis.update(kw)
    return basis


def _halle(unit: dict, stat: PropstackReport | None = None):
    """Die Halle/Lager-Zeile einer Einheit."""
    zeilen = normalize.propstack_zu_zeilen_einer_unit(unit, stat or PropstackReport())
    return next((z for z in zeilen if z.nutzungsart == "Halle/Lager"), None)


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
HALLE = config.FLAECHENARTEN[0]
BUERO = config.FLAECHENARTEN[1]


def test_kaltmiete_aus_custom_field():
    wert, feld = propstack_gateway.hole_betrag(_unit(), HALLE.miete_felder)
    assert wert == 4.58
    assert feld == "custom_fields.intern_mietpreis_hallenflache"


def test_ausgeschriebener_wert_hat_vorrang_vor_dem_internen():
    """Vorgabe K&P (13.08.2026): die externe Miete sticht die interne.

    Wo der Vermieter einen Preis ausschreibt, ist das der belastbarere Wert;
    `intern_mietpreis_*` ist unsere Einschätzung und greift nur, wenn nichts
    ausgeschrieben ist.
    """
    unit = _unit(custom={
        "intern_mietpreis_hallenflache": {"value": 4.58},
        "mietpreis_hallenflache": {"value": 5.50},
    })
    wert, feld = propstack_gateway.hole_betrag(unit, HALLE.miete_felder)
    assert (wert, feld) == (5.50, "custom_fields.mietpreis_hallenflache")


def test_interner_wert_greift_ohne_ausgeschriebenen():
    unit = _unit(custom={"intern_mietpreis_hallenflache": {"value": 4.58}})
    wert, feld = propstack_gateway.hole_betrag(unit, HALLE.miete_felder)
    assert (wert, feld) == (4.58, "custom_fields.intern_mietpreis_hallenflache")


def test_fallback_auf_ausgeschriebenen_mietpreis():
    unit = _unit(custom={
        "intern_mietpreis_hallenflache": {"value": None},
        "mietpreis_hallenflache": {"value": 5.50},
    })
    wert, feld = propstack_gateway.hole_betrag(unit, HALLE.miete_felder)
    assert (wert, feld) == (5.50, "custom_fields.mietpreis_hallenflache")


def test_stellplatzmiete_wird_nie_als_qm_miete_gelesen():
    """95 Einheiten tragen stellplatzmiete mit 20-70 € PRO STELLPLATZ.
    Ein Teilstring-Match auf 'miete' hätte den €/m²-Median zerstört."""
    unit = _unit(custom={
        "intern_mietpreis_hallenflache": {"value": None},
        "mietpreis_hallenflache": {"value": None},
        "stellplatzmiete": {"value": 30.0},
        "lkw_stellplatzmiete": {"value": 70.0},
    })
    assert propstack_gateway.hole_betrag(unit, HALLE.miete_felder) == (None, None)
    assert normalize.propstack_zu_zeilen_einer_unit(unit, PropstackReport()) == []


def test_standardfelder_werden_ignoriert():
    """base_rent ist bei K&P kaum gepflegt (6 von 1.978) und mischt €/m² mit
    absoluten Monatsmieten – bewusst außen vor."""
    unit = _unit(base_rent={"label": "Kaltmiete", "value": 19848.0},
                 custom={"intern_mietpreis_hallenflache": {"value": None},
                         "mietpreis_hallenflache": {"value": None}})
    assert normalize.propstack_zu_zeilen_einer_unit(unit, PropstackReport()) == []


def test_null_betrag_gilt_als_nicht_gesetzt():
    """value=0 ist 'nicht erfasst', nicht 'Miete null'."""
    unit = _unit(custom={"intern_mietpreis_hallenflache": {"value": 0},
                         "mietpreis_hallenflache": {"value": None}})
    assert propstack_gateway.hole_betrag(unit, HALLE.miete_felder)[0] is None


def test_flaeche_der_flaechenart_zuerst():
    wert, feld = propstack_gateway.hole_flaeche(_unit(), HALLE.flaeche_felder)
    assert (wert, feld) == (5000.0, "custom_fields.lagerflache")
    wert, feld = propstack_gateway.hole_flaeche(_unit(), BUERO.flaeche_felder)
    assert (wert, feld) == (400.0, "custom_fields.buroflache")


def test_flaeche_fallback_auf_gesamtflaeche():
    unit = _unit(custom={"lagerflache": {"value": None}, "lagerflache_gesamt": {"value": None}},
                 property_space_value=6679.0)
    wert, feld = propstack_gateway.hole_flaeche(unit, HALLE.flaeche_felder)
    assert (wert, feld) == (6679.0, "property_space_value")


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
def test_qm_miete_wird_direkt_uebernommen():
    """Die Custom Fields stehen bereits in €/m² – nichts wird gerechnet."""
    stat = PropstackReport()
    zeile = _halle(_unit(), stat)
    assert zeile.kaltmiete_eur_qm == 4.58
    assert zeile.nebenkosten_eur_qm == 2.15
    assert zeile.flaeche_qm == 5000.0
    assert zeile.normalisiert_aus_absolut is False
    assert zeile.region_key == "59"
    assert zeile.quelle == "propstack"
    assert zeile.verwertbar
    assert stat.miete_felder == {"custom_fields.intern_mietpreis_hallenflache": 1}


def test_je_flaechenart_eine_eigene_zeile(monkeypatch):
    """Halle 6,00 und Büro 12,50 sind zwei Datenpunkte in zwei Märkten –
    ein gemeinsamer Median wäre eine Phantasiezahl. (Standardmäßig ist nur
    Halle/Lager im Report, hier wird der Mechanismus geprüft.)"""
    monkeypatch.setenv("FLAECHENARTEN", "Halle/Lager,Büro,Mezzanine")
    unit = _unit(custom={
        "intern_mietpreis_hallenflache": {"value": 6.00},
        "intern_mietpreis_buro": {"value": 12.50},
        "intern_mietpreis_mezzanine": {"value": 3.25},
    })
    zeilen = normalize.propstack_zu_zeilen_einer_unit(unit, PropstackReport())
    nach_art = {z.nutzungsart: z.kaltmiete_eur_qm for z in zeilen}
    assert nach_art == {"Halle/Lager": 6.00, "Büro": 12.50, "Mezzanine": 3.25}


def test_flaechenart_bekommt_ihre_eigene_flaeche(monkeypatch):
    monkeypatch.setenv("FLAECHENARTEN", "Halle/Lager,Büro")
    unit = _unit(custom={
        "intern_mietpreis_hallenflache": {"value": 6.00},
        "intern_mietpreis_buro": {"value": 12.50},
    })
    zeilen = {z.nutzungsart: z.flaeche_qm
              for z in normalize.propstack_zu_zeilen_einer_unit(unit, PropstackReport())}
    assert zeilen["Halle/Lager"] == 5000.0
    assert zeilen["Büro"] == 400.0


def test_unplausible_flaeche_verwirft_nur_die_flaeche():
    """Realer Datenfehler in Propstack: 'lagerflache_gesamt' = 10.403 (statt
    10.403 m²), angezeigt als '10,40 m²'. Die Miete ist trotzdem gültig, sie
    steht schon als €/m² – ~190 Datenpunkte hingen daran."""
    stat = PropstackReport()
    unit = _unit(custom={
        "lagerflache": {"value": None},
        "lagerflache_gesamt": {"value": 10.403, "pretty_value": "10,40 m²"},
    })
    zeile = _halle(unit, stat)
    assert zeile.verwertbar                       # Miete bleibt!
    assert zeile.kaltmiete_eur_qm == 4.58
    assert zeile.flaeche_qm is None               # Fläche verworfen
    assert "Tausendertrennung" in zeile.option_hinweis
    assert stat.flaeche_unplausibel == 1


def test_absolute_miete_wird_als_solche_erkannt():
    """mietpreis_hallenflache trägt vereinzelt absolute Monatsmieten
    (61.880 €). Die fliegen MIT nachvollziehbarem Grund raus."""
    unit = _unit(custom={"intern_mietpreis_hallenflache": {"value": 61880.0}})
    zeile = _halle(unit)
    assert not zeile.verwertbar
    assert "absolute Monatsmiete" in zeile.ausschluss_grund


def test_einheit_ohne_miete_ergibt_keine_zeile():
    """Der Normalfall – Mieten werden am Markt nicht geteilt. Gezählt wird es,
    als Mangel gilt es nicht."""
    stat = PropstackReport()
    unit = _unit(custom={k: {"value": None} for k in (
        "intern_mietpreis_hallenflache", "mietpreis_hallenflache",
    )}, furnishings={"price_on_inquiry": True})
    assert normalize.propstack_zu_zeilen_einer_unit(unit, stat) == []
    assert stat.ohne_miete == 1
    assert stat.preis_auf_anfrage == 1


def test_kaufobjekt_wird_nicht_ausgewertet():
    stat = PropstackReport()
    assert normalize.propstack_zu_zeilen_einer_unit(
        _unit(marketing_type="BUY", for_rent=False), stat) == []
    assert stat.keine_mietobjekte == 1


def test_vermietete_einheit_wird_markiert():
    stat = PropstackReport()
    zeile = _halle(_unit(rented={"label": "Vermietet", "value": True}), stat)
    assert zeile.vermietet is True
    assert "vermietet" in zeile.option_hinweis
    assert stat.vermietet == 1


def test_altimport_felder_werden_nie_gelesen():
    """`lagerflache_miete_m_von` existiert in der Propstack-MASKE nicht und
    wird von niemandem gepflegt. Nachgewiesen an "Stettiner Straße 2, Neuss":
    Kaltmiete und beide Intern-Felder leer, das Alt-Feld trug 1,00 €/m².
    Über den Bestand lagen 119 von 128 Werten unter "auf Anfrage"."""
    unit = _unit(custom={
        "intern_mietpreis_hallenflache": {"value": None},
        "mietpreis_hallenflache": {"value": None},
        "lagerflache_miete_m_von": {"value": 1.0},
        "lagerflache_miete_m_bis": {"value": 1.0},
        "preisangabe": {"value": "auf Anfrage"},
    })
    assert normalize.propstack_zu_zeilen_einer_unit(unit, PropstackReport()) == []


def test_preisangabe_auf_anfrage_wird_erkannt():
    """K&P pflegt das Custom Field `preisangabe`, nicht price_on_inquiry."""
    assert propstack_gateway.preis_auf_anfrage(
        _unit(custom={"preisangabe": {"value": "auf Anfrage"}}))
    assert propstack_gateway.preis_auf_anfrage(
        _unit(custom={"preisangabe": {"value": "Auf Anfrage"}}))
    assert not propstack_gateway.preis_auf_anfrage(
        _unit(custom={"preisangabe": {"value": "nach Mietpreisangabe"}}))


def test_auf_anfrage_entwertet_keinen_internen_mietpreis():
    """Öffentlich "auf Anfrage", intern bekannt – der Normalfall bei K&P
    (267 von 369 Einheiten mit Miete). Ein Veto würde genau die Daten
    wegwerfen, um die es in diesem Report geht."""
    unit = _unit(custom={
        "intern_mietpreis_hallenflache": {"value": 8.20},
        "preisangabe": {"value": "auf Anfrage"},
    })
    zeile = _halle(unit)
    assert zeile is not None
    assert zeile.kaltmiete_eur_qm == 8.20
    assert zeile.verwertbar


def test_propstack_zeilen_gelten_als_eigene_angebote():
    assert _halle(_unit()).eigenes_angebot is True


def test_adresse_wird_zusammengesetzt():
    assert _halle(_unit()).adresse == "Industriestraße 12"


def test_ohne_plz_keine_region():
    zeile = _halle(_unit(zip_code=None))
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


# --- Report-Filter der Flächenarten ---------------------------------------
def test_standardmaessig_nur_halle_lager():
    """Auf Wunsch 13.08.2026: Büro, Mezzanine, Service und Keller sind raus."""
    stat = PropstackReport()
    unit = _unit(custom={
        "intern_mietpreis_hallenflache": {"value": 6.00},
        "intern_mietpreis_buro": {"value": 12.50},
        "intern_mietpreis_mezzanine": {"value": 3.25},
    })
    zeilen = normalize.propstack_zu_zeilen_einer_unit(unit, stat)
    assert [z.nutzungsart for z in zeilen] == ["Halle/Lager"]
    assert stat.flaechenart_uebersprungen == 2      # nicht still verschwunden
    assert stat.mit_miete == 1


def test_einheit_nur_mit_bueromiete_zaehlt_als_ohne_miete():
    """Sie trägt eine Miete, aber keine im Report – der Zähler sagt beides."""
    stat = PropstackReport()
    unit = _unit(custom={
        "intern_mietpreis_hallenflache": {"value": None},
        "mietpreis_hallenflache": {"value": None},
        "intern_mietpreis_buro": {"value": 12.50},
    })
    assert normalize.propstack_zu_zeilen_einer_unit(unit, stat) == []
    assert stat.flaechenart_uebersprungen == 1
    assert stat.ohne_miete == 1


def test_filter_ist_per_env_erweiterbar(monkeypatch):
    monkeypatch.setenv("FLAECHENARTEN", "Halle/Lager,Büro")
    unit = _unit(custom={
        "intern_mietpreis_hallenflache": {"value": 6.00},
        "intern_mietpreis_buro": {"value": 12.50},
        "intern_mietpreis_mezzanine": {"value": 3.25},
    })
    zeilen = normalize.propstack_zu_zeilen_einer_unit(unit, PropstackReport())
    assert {z.nutzungsart for z in zeilen} == {"Halle/Lager", "Büro"}


# --- Nutzungsart-Synonyme (Drive) -----------------------------------------
def test_drive_nutzungsarten_landen_in_derselben_gruppe():
    """Das LLM schreibt 'Logistik', Propstack 'Halle/Lager' – ohne Abbildung
    stünden sie in getrennten Abschnitten."""
    for wert in ("Logistik", "Halle", "Lagerfläche", "logistikhalle", "LAGER"):
        assert normalize.normalisiere_nutzungsart(wert) == "Halle/Lager"
    assert normalize.normalisiere_nutzungsart("Büro") == "Büro"


def test_unbekannte_nutzungsart_bleibt_unveraendert():
    """Lieber ein eigener Abschnitt als eine falsche Einordnung."""
    assert normalize.normalisiere_nutzungsart("Freifläche") == "Freifläche"
    assert normalize.normalisiere_nutzungsart(None) is None


def test_stabile_sortierung_wird_mitgeschickt(monkeypatch):
    """Ohne sort_by verschieben sich die Seiten während der Paginierung und
    es fallen Einheiten durchs Raster – gemessen ~120 pro Lauf."""
    gesendet = []

    def fake_request(path, params):
        gesendet.append(params)
        return _FakeResponse(_fake_units(1, 5) if params["page"] == 1 else [])

    monkeypatch.setattr(propstack_gateway, "_request", fake_request)
    propstack_gateway.fetch_units()
    assert gesendet[0]["sort_by"] == "id"
    assert gesendet[0]["order"] == "asc"
