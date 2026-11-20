"""Absicherung des scharf laufenden #objekte-Handlers (Stand 19.11.2026).

Zwei Dinge, beide an Live-Daten geprüft (nur gelesen):
1. 47 der 82 offenen Aufgaben dieses Handlers antworteten auf Vollzugsmeldungen –
   „neues Objekt angelegt …“ oder Berichte aus Claude-Sitzungen. 25 von 30 Aufgaben
   „Objekt fehlt in Propstack: bitte anlegen“ betrafen gerade angelegte Objekte.
2. Stufe A lief seit Juli zweimal. Die Wege dorthin waren weiter als nötig: Absagen
   auch an Deals in der Abschluss-Phase und in Verkaufs-Pipelines, „nächstliegende“
   Fläche ohne Toleranz, alle Einheiten einer Adresse auch bei „Halle 2 ist vermietet“.
Die fünf Regressionsfälle vom 08.07.2026 (test_regression_cases.py) bleiben unverändert.
"""
from __future__ import annotations

import httpx
import pytest

from objekte_handler import main, matcher, propstack
from objekte_handler.matcher import find_unit, nennt_einzelne_einheit, parse_qm, pick_by_size_hint
from objekte_handler.models import (
    AktionsTyp,
    Classification,
    MatchResult,
    MatchStatus,
    MessageType,
    RunReport,
    Unit,
)
from objekte_handler.propstack import absage_hindernis
from objekte_handler.vollzug import vollzugsmeldung

from .fixtures import HAMBURGRING_UNITS, VIERSEN_UNITS


def _cls(**kwargs) -> Classification:
    defaults = {"typ": MessageType.STATUS_ANWEISUNG, "aktion": AktionsTyp.VERMIETET, "confidence": 0.95}
    defaults.update(kwargs)
    return Classification(**defaults)


# --- Vollzugsmeldungen sind kein Auftrag ------------------------------------------

@pytest.mark.parametrize("text", [
    # so postet der Slack-Connector aus einer Claude-Sitzung
    "_Mileway Immo-Blitz 09.11.2026 – Abgleich mit Propstack_ (alles provisionsfrei)\n_Neu angelegt (15 Objekte):_ …\n_Gesendet mit_ Claude\n*Gesendet mit* Claude",
    "*Update: Logistikzentrum Nohra (bei Erfurt)* – Unit 1 und 2 sind vermietet, nur noch *Unit 3* frei\n*Gesendet mit* Claude",
    # so melden Kollegen eine fertige Anlage
    "neues Objekt angelegt\n SEGRO - (32) Herford\n gesamt ca. 9.133 m² Mietfläche …",
    "*Neues Objekt angelegt*: CTPark Recklinghausen",
])
def test_vollzugsmeldung_erkannt(text):
    assert vollzugsmeldung(text)


@pytest.mark.parametrize("text", [
    "Moers ist vermietet",
    "Hamburgring 48, Mönchengladbach ist vermietet – bitte Objekt inaktiv setzen, Deals absagen",
    "Das Objekt Landau von Nvelop fehlt in Propstack",
    "bitte Objekt & Provisionsvereinbarung anlegen",
    "Newsletter Hillwood 11/26 INKLUSIVE Mietpreise",
    "Bilder herne prologis sind im drive",
    "Haben wir das objekt?",
    "Das Objekt wurde letzte Woche neu angelegt, bitte Bilder ergänzen",   # „angelegt“ nicht am Anfang
    "", None,
])
def test_auftraege_bleiben_auftraege(text):
    assert vollzugsmeldung(text) is None


def test_vollzugsmeldung_kostet_keine_ki_und_keine_aufgabe(monkeypatch):
    monkeypatch.setattr(main, "classify_message", lambda *a: pytest.fail("keine Klassifikation erwartet"))
    monkeypatch.setattr(main, "create_task", lambda *a: pytest.fail("keine Aufgabe erwartet"))
    monkeypatch.setattr(main, "add_checkmark", lambda *a: pytest.fail("kein ✅ erwartet"))
    records = []
    monkeypatch.setattr(main, "append_record", records.append)

    report = RunReport()
    main._process_message({"ts": "1.1", "text": "neues Objekt angelegt\n SEGRO - (32) Herford"}, None, "run", report)

    assert (report.vollzugsmeldungen, report.stufe_b, report.fehler) == (1, 0, [])
    assert "kein Auftrag" in records[0].decision.grund


# --- Absagen: nie in der Abschluss-Phase, nur in der Vermietung --------------------

VERMIETUNG = {156095, 251265, 266668}  # "300 Mieter", "300 Leverkusen", "300 Sontra"


@pytest.mark.parametrize("deal,erwartet", [
    ({"id": 1, "deal_pipeline_id": 156095, "deal_stage_chance": 0.3}, None),               # Exposé versendet
    ({"id": 2, "deal_pipeline_id": None, "deal_stage_chance": None}, None),                 # ohne Pipeline
    ({"id": 3, "deal_pipeline_id": 156095, "deal_stage_chance": 1.0}, "Abschluss-Phase"),   # der Mieter selbst
    ({"id": 4, "deal_pipeline_id": 252688, "deal_stage_chance": 0.1}, "keine Vermietungs-Pipeline"),  # 200 Ratingen
    ({"id": 5, "deal_pipeline_id": 234963, "deal_stage_chance": 0.5}, "keine Vermietungs-Pipeline"),  # Kaltenkirchen
])
def test_absage_hindernis(deal, erwartet):
    assert absage_hindernis(deal, VERMIETUNG) == erwartet


def test_pipelines_nicht_lesbar_dann_nur_deals_ohne_pipeline():
    assert absage_hindernis({"deal_pipeline_id": None}, None) is None
    assert absage_hindernis({"deal_pipeline_id": 156095, "deal_stage_chance": 0.3}, None) == "Pipelines nicht lesbar"


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_vermietungs_pipelines_am_namen(monkeypatch):
    # GET /v1/deal_pipelines, gekürzt (Stand 19.11.2026)
    pipelines = {"data": [
        {"id": 156093, "name": "100 Eigentümer"}, {"id": 156094, "name": "200 Investment"},
        {"id": 252688, "name": "200 Ratingen"}, {"id": 251265, "name": "300 Leverkusen"},
        {"id": 156095, "name": "300 Mieter"}, {"id": 266668, "name": "300 Sontra"},
        {"id": 234963, "name": "Kaltenkirchen"},
    ]}
    monkeypatch.setenv("PROPSTACK_API_KEY", "x")
    monkeypatch.setattr(propstack, "_request", lambda *a, **k: _Resp(pipelines))
    assert propstack.fetch_vermietungs_pipelines() == VERMIETUNG


def test_stufe_a_laesst_abschluss_und_verkauf_unangetastet(monkeypatch):
    angelegt, antworten = [], []
    deals = [
        {"id": 1, "client_id": 11, "property_id": 5, "deal_pipeline_id": 156095, "deal_stage_chance": 0.3},
        {"id": 2, "client_id": 12, "property_id": 5, "deal_pipeline_id": 156095, "deal_stage_chance": 1.0},
        {"id": 3, "client_id": 13, "property_id": 5, "deal_pipeline_id": 252688, "deal_stage_chance": 0.1},
    ]
    monkeypatch.setattr(main, "set_rented", lambda unit_id: True)
    monkeypatch.setattr(main, "create_task", lambda payload: angelegt.append(payload) or 1)
    monkeypatch.setattr(main, "get_open_deals", lambda unit_id: deals)
    monkeypatch.setattr(main, "fetch_vermietungs_pipelines", lambda: VERMIETUNG)
    monkeypatch.setattr(main, "add_checkmark", lambda ts: True)
    monkeypatch.setattr(main, "post_thread_reply", lambda ts, text: antworten.append(text) or True)

    unit = Unit(id=5, street="Hamburgring", house_number="48", city="Mönchengladbach")
    match = MatchResult(status=MatchStatus.UNIQUE, units=[unit], kandidaten=[unit])
    aktionen = main._stufe_a({"ts": "1763550000.000100", "text": "Hamburgring 48 ist vermietet"}, _cls(), match, "https://x")

    absagen = [p for p in angelegt if p.reservation_reason_id]
    assert [p.client_ids for p in absagen] == [[11]]
    assert "1 offene Deals abgesagt" in antworten[0]
    assert "2 Deal(s) nicht angetastet (1× Abschluss-Phase, 1× keine Vermietungs-Pipeline)" in antworten[0]
    assert sum("nicht abgesagt" in a for a in aktionen) == 2


def test_stufe_a_scheitert_die_notiz_laufen_die_absagen_trotzdem(monkeypatch):
    """Die Einheit ist dann schon vermietet gesetzt. Ohne den Rest bliebe ein halber Zustand
    ohne Antwort und ohne ✅ zurück – und die Nachricht fiele am nächsten Tag aus dem Fenster."""
    angelegt, antworten, haken = [], [], []

    def create_task(payload):
        if not payload.reservation_reason_id:
            raise httpx.HTTPStatusError("HTTP 502", request=None, response=None)
        angelegt.append(payload)
        return 7

    monkeypatch.setattr(main, "set_rented", lambda unit_id: True)
    monkeypatch.setattr(main, "create_task", create_task)
    monkeypatch.setattr(main, "get_open_deals", lambda unit_id: [{"id": 1, "client_id": 11, "property_id": 5, "deal_pipeline_id": None}])
    monkeypatch.setattr(main, "fetch_vermietungs_pipelines", lambda: VERMIETUNG)
    monkeypatch.setattr(main, "add_checkmark", lambda ts: haken.append(ts) or True)
    monkeypatch.setattr(main, "post_thread_reply", lambda ts, text: antworten.append(text) or True)

    unit = Unit(id=5, street="Hamburgring", house_number="48", city="Mönchengladbach")
    match = MatchResult(status=MatchStatus.UNIQUE, units=[unit], kandidaten=[unit])
    aktionen = main._stufe_a({"ts": "1.1", "text": "Hamburgring 48 ist vermietet"}, _cls(), match, "https://x")

    assert len(angelegt) == 1 and haken == ["1.1"]
    assert antworten[0].startswith("⚠️ Nur teilweise erledigt") and "Doku-Notiz nicht angelegt" in antworten[0]
    assert any(a.startswith(main.WARNUNG) for a in aktionen)   # macht den Lauf rot


def test_stufe_a_ohne_vermietungs_pipeline_wird_gemeldet(monkeypatch):
    monkeypatch.setattr(main, "set_rented", lambda unit_id: True)
    monkeypatch.setattr(main, "create_task", lambda payload: 1)
    monkeypatch.setattr(main, "get_open_deals", lambda unit_id: [])
    monkeypatch.setattr(main, "fetch_vermietungs_pipelines", lambda: set())
    monkeypatch.setattr(main, "add_checkmark", lambda ts: True)
    monkeypatch.setattr(main, "post_thread_reply", lambda ts, text: True)
    unit = Unit(id=5, street="Hamburgring", house_number="48")
    aktionen = main._stufe_a({"ts": "1.1", "text": "x"}, _cls(), MatchResult(status=MatchStatus.UNIQUE, units=[unit]), "")
    assert any(a.startswith(main.WARNUNG) and "Keine Pipeline" in a for a in aktionen)


# --- Schreiben wird nach einem Serverfehler nicht wiederholt ----------------------

class _Antwort:
    def __init__(self, status_code):
        self.status_code = status_code
        self.text = ""
        self.request = None

    def raise_for_status(self):
        raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=None, response=self)

    def json(self):
        return {"id": 1}


def _zaehle(monkeypatch, status_folge):
    aufrufe = []

    def request(method, url, **kw):
        aufrufe.append(method)
        return _Antwort(status_folge[min(len(aufrufe), len(status_folge)) - 1])

    monkeypatch.setattr(propstack.httpx, "request", request)
    monkeypatch.setattr(propstack.time, "sleep", lambda s: None)
    return aufrufe


def test_post_nach_500_kein_zweiter_versuch(monkeypatch):
    """Kam der erste Versuch doch an, entstünde die Aufgabe oder Absage doppelt."""
    aufrufe = _zaehle(monkeypatch, [502])
    with pytest.raises(httpx.HTTPStatusError):
        propstack._request("POST", "/tasks", key="k", json={"task": {}})
    assert aufrufe == ["POST"]


def test_post_timeout_kein_zweiter_versuch(monkeypatch):
    aufrufe = []

    def request(method, url, **kw):
        aufrufe.append(method)
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(propstack.httpx, "request", request)
    monkeypatch.setattr(propstack.time, "sleep", lambda s: None)
    with pytest.raises(httpx.ReadTimeout):
        propstack._request("POST", "/tasks", key="k", json={})
    assert aufrufe == ["POST"]


def test_put_wird_wiederholt(monkeypatch):
    """rented=true ein zweites Mal zu setzen ändert nichts – also darf PUT wiederholt werden.
    Sonst bliebe nach einem einzelnen 502 die Einheit unverändert und die Meldung verloren."""
    aufrufe = []

    class _Ok(_Antwort):
        def raise_for_status(self):
            return None

    folge = [_Antwort(502), _Ok(200)]
    monkeypatch.setattr(propstack.httpx, "request", lambda method, url, **kw: aufrufe.append(method) or folge[len(aufrufe) - 1])
    monkeypatch.setattr(propstack.time, "sleep", lambda s: None)
    assert propstack._request("PUT", "/units/1", key="k", json={}).status_code == 200
    assert aufrufe == ["PUT", "PUT"]


def test_get_wird_weiter_wiederholt(monkeypatch):
    aufrufe = _zaehle(monkeypatch, [502, 502, 200])

    class _Ok(_Antwort):
        def raise_for_status(self):
            return None

    folge = [_Antwort(502), _Antwort(502), _Ok(200)]
    monkeypatch.setattr(propstack.httpx, "request", lambda method, url, **kw: aufrufe.append(method) or folge[len(aufrufe) - 1])
    assert propstack._request("GET", "/units", key="k").status_code == 200
    assert aufrufe == ["GET", "GET", "GET"]


# --- Größen-Hinweis --------------------------------------------------------------

@pytest.mark.parametrize("text,erwartet", [
    ("7.666 qm", 7666), ("7666.0", 7666), ("9,024", 9024), ("12.500,5 m²", 12500.5),
    ("3000", 3000), ("ca. 4.200m²", 4200), ("keine Zahl", None),
])
def test_parse_qm(text, erwartet):
    assert parse_qm(text) == erwartet


def test_zahl_ohne_passende_einheit_ist_kein_treffer():
    """„3.000 m² vermietet“ traf früher die Einheit mit 7.666 m² (nächstliegende)."""
    assert pick_by_size_hint(VIERSEN_UNITS, "3000") is None


@pytest.mark.parametrize("hint,unit_id", [("7666.0", 5050165), ("9,024", 5050166), ("7.600 qm", 5050165), ("ca. 9.000", 5050166)])
def test_zahl_trifft_die_einheit_mit_dieser_flaeche(hint, unit_id):
    assert pick_by_size_hint(VIERSEN_UNITS, hint).id == unit_id


def test_zahl_passt_auf_zwei_einheiten_ist_kein_treffer():
    units = [Unit(id=1, property_space_value=5000.0), Unit(id=2, property_space_value=5300.0)]
    assert pick_by_size_hint(units, "5.100") is None


def test_kleinste_ist_schon_vermietet_dann_entscheidet_ein_mensch():
    """Zwei Lesarten: Die Vermietung der 3.000er wird ein zweites Mal gemeldet – oder gemeint
    ist die kleinste noch freie. Nie auf die nächste freie ausweichen: Das träfe eine
    Einheit, von der niemand gesprochen hat (Befund des Gegenlesens, 19.11.2026)."""
    units = [
        Unit(id=1, property_space_value=3000.0, rented=True),
        Unit(id=2, property_space_value=7666.0, rented=False),
        Unit(id=3, property_space_value=9024.0, rented=False),
    ]
    assert pick_by_size_hint(units, "kleinste") is None
    assert pick_by_size_hint(units, "groesste").id == 3     # die größte ist frei -> eindeutig


def test_vermietete_einheit_die_nicht_gemeint_sein_kann_stoert_nicht():
    units = [
        Unit(id=1, property_space_value=3000.0, rented=False),
        Unit(id=2, property_space_value=7666.0, rented=True),
    ]
    assert pick_by_size_hint(units, "kleinste").id == 1


def test_zahl_trifft_schon_vermietete_einheit_dann_entscheidet_ein_mensch():
    units = [Unit(id=1, property_space_value=3000.0, rented=True), Unit(id=2, property_space_value=7666.0)]
    assert pick_by_size_hint(units, "3.000 m²") is None


# --- Ganzes Objekt nur, wenn die Nachricht keine einzelne Einheit nennt ---------------

@pytest.mark.parametrize("text", [
    "Hamburgring 48 Halle 2 ist vermietet", "Unit 1 und 2 sind vermietet", "Halle B ist weg", "Gebäude 17 EG vermietet",
    "BA 2 ist vermietet", "DC3 vermietet", "Teilfläche vermietet", "ist teilweise vermietet", "eine der Hallen ist vermietet",
    "Hallen 1 und 2 sind vermietet", "Units 1 und 2 sind weg", "Einheiten 3 und 4 vermietet", "Teilflächen vermietet",
    "die 1. Halle ist vermietet", "die hintere Halle ist vermietet", "ein Teil der Fläche ist vermietet",
])
def test_nachricht_nennt_einzelne_einheit(text):
    assert nennt_einzelne_einheit(text)


@pytest.mark.parametrize("text", [
    "Hamburgring 48, Mönchengladbach ist vermietet – bitte Objekt inaktiv setzen, Deals absagen",
    "Bad Hersfeld ist vermietet", "Die Halle ist vermietet", "Hallesche Straße 4 vermietet",
    "Halle (Saale) Nord ist vermietet", "Moers ist vermietet", "P3 Bielefeld ist vom Markt", None,
])
def test_nachricht_nennt_keine_einzelne_einheit(text):
    assert nennt_einzelne_einheit(text) is None


def test_halle_2_schliesst_nicht_alle_einheiten_der_adresse(monkeypatch):
    monkeypatch.setattr(matcher, "search_units", lambda q: HAMBURGRING_UNITS)
    cls = _cls(strasse="Hamburgring", hausnummer="48", stadt="Mönchengladbach")

    ganz = find_unit(cls, "Hamburgring 48, Mönchengladbach ist vermietet – bitte Deals absagen")
    assert ganz.status == MatchStatus.UNIQUE and len(ganz.units) == 2   # wie bisher (Fall 1)

    teil = find_unit(cls, "Hamburgring 48 Halle 2 ist vermietet")
    assert teil.status == MatchStatus.AMBIGUOUS and teil.units == []
    assert "Halle 2" in teil.grund and len(teil.kandidaten) == 2


def test_einzelne_einheit_steht_im_thread_die_antwort_sagt_nur_vermietet(monkeypatch):
    monkeypatch.setattr(matcher, "search_units", lambda q: HAMBURGRING_UNITS)
    cls = _cls(strasse="Hamburgring", hausnummer="48", stadt="Mönchengladbach")
    kontext = "Ursprungsnachricht: Hamburgring 48 Halle 2 – Besichtigung nächste Woche"
    result = find_unit(cls, f"{kontext}\nist jetzt vermietet")
    assert result.status == MatchStatus.AMBIGUOUS


# --- Adresse und Name --------------------------------------------------------------

def test_gleiche_strasse_in_zwei_orten_ist_nicht_dasselbe_objekt(monkeypatch):
    units = [
        Unit(id=1, street="Industriestraße", house_number="12", city="Krefeld", zip_code="47807"),
        Unit(id=2, street="Industriestraße", house_number="12", city="Willich", zip_code="47877"),
    ]
    monkeypatch.setattr(matcher, "search_units", lambda q: units)
    result = find_unit(_cls(strasse="Industriestraße", hausnummer="12"), "Industriestr. 12 ist vermietet")
    assert result.status == MatchStatus.AMBIGUOUS


def test_fremder_einzeltreffer_ist_kein_treffer(monkeypatch):
    """Die Suche fand genau eine Einheit, deren Name nichts mit dem genannten zu tun hat."""
    fremd = [Unit(id=9, name="Logistikhalle in (44) Bochum", street="Wittener Straße", house_number="1", city="Bochum")]
    monkeypatch.setattr(matcher, "search_units", lambda q: fremd)
    assert find_unit(_cls(objekt_name="prodac"), "prodac ist vermietet").status == MatchStatus.NONE


def test_nur_ort_genannt_ist_nicht_eindeutig(monkeypatch):
    einzige = [Unit(id=9, name="Logistikhalle in (44) Castrop-Rauxel", street="Industriestraße", house_number="1", city="Castrop-Rauxel")]
    monkeypatch.setattr(matcher, "search_units", lambda q: einzige)
    assert find_unit(_cls(stadt="Castrop-Rauxel"), "Castrop-Rauxel ist vermietet").status == MatchStatus.AMBIGUOUS


# --- Antworten der KI ------------------------------------------------------------------

def test_zahl_statt_text_verwirft_die_nachricht_nicht():
    cls = Classification.model_validate({"typ": "status_anweisung", "aktion": "vermietet", "hausnummer": 48,
                                         "groessen_hinweis": 6000, "confidence": 0.9})
    assert (cls.hausnummer, cls.groessen_hinweis) == ("48", "6000")


# --- Dieselbe Nachricht nur einmal ------------------------------------------------------

def test_antwort_mit_kopie_im_kanal_wird_einmal_verarbeitet(monkeypatch):
    import time as _time

    jetzt = _time.time()
    parent = {"ts": f"{jetzt - 3600:.6f}", "text": "Newsletter Hillwood", "user": "U1", "reply_count": 1}
    antwort = {"ts": f"{jetzt - 1800:.6f}", "text": "Langenselbold ist vermietet", "user": "U2", "thread_ts": parent["ts"]}
    monkeypatch.setattr(main, "fetch_channel_messages", lambda hours, latest_hours=0: [parent, dict(antwort)])
    monkeypatch.setattr(main, "fetch_thread_replies", lambda ts: [parent, antwort])
    monkeypatch.setattr(main.time, "sleep", lambda s: None)

    kandidaten = main._collect_candidates("UBOT")
    assert [m["ts"] for m, _ in kandidaten] == [parent["ts"], antwort["ts"]]
    assert kandidaten[1][1] and "Newsletter Hillwood" in kandidaten[1][1]   # die Fassung mit Thread-Kontext
