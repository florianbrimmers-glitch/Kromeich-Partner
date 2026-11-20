"""Eigentümer-Probe, mehrere Einheiten je Vermietung, Verlängerungen (ohne Netz).

Die Fälle stammen aus den 129 Review-Aufgaben, die am 19./20.11.2026 einzeln gegen
Propstack und die Fachpresse gelesen wurden (scripts/radar_vorpruefung_2026-11-19.json,
scripts/radar_nachpruefung_2026-11-20.json). Die Einheiten sind so aufgebaut, wie
GET /v1/units?expand=1 sie an diesem Tag geliefert hat.
"""
import json
import types

import pytest

from newsletter_handler import eigentuemer, main, match_ai, review_dedup
from newsletter_handler.decision import decide
from newsletter_handler.models import (
    Deal, DealTyp, MatchResult, MatchStatus, NewsletterExtraction, RunReport, Tier, Unit,
)
from newsletter_handler.propstack import _to_unit
from newsletter_handler.review_dedup import OffeneReviews

VERMARKTUNG, ABGESCHLOSSEN = 163674, 163676


# --- Namen vergleichen -------------------------------------------------------------

@pytest.mark.parametrize("vermieter, am_objekt, erwartet", [
    # derselbe – in den Schreibweisen, die am 20.11.2026 im Bestand standen
    ("Garbe", "GARBE Industrial GmbH & Co. KG", True),
    ("Garbe Industrial Real Estate", "GARBE Industrial GmbH & Co. KG", True),
    ("HIH / Urban Partners", "HIH Real Estate GmbH", True),
    ("P3 Logistic Parks", "P3 Logistic Parks GmbH", True),
    ("Logicor", "LogiCor Deutschland GmbH", True),
    ("bauwo Grundstücksgesellschaft mbH", "bauwo Grundstücksgesellschaft mbH", True),
    ("Four Parx", "FOUR PARX Holding GmbH", True),
    ("OSMAB Holding AG / ALCARO Invest GmbH", "ALCARO Invest GmbH", True),
    ("Trammell Crow Company (TCC)", "TCC", True),
    # Altbestand: Nummer und Ansprechpartner stehen vor der Firma
    ("ADOLF WEBER West", "65110 Jochen Boudon ADOLF WEBER INVESTMENT GMBH", True),
    ("Aurelis Real Estate GmbH", "31677 Jessica Evers Aurelis Real Estate GmbH & Co. KG", True),
    # erkennbar ein anderer
    ("Ixocon", "BEOS AG", False),
    ("Panattoni", "evolutiq GmbH (JV mit Logistik Service)", False),
    ("Prologis Germany Management GmbH", "bauwo Grundstücksgesellschaft mbH", False),
    ("VGP", "CTP Invest Germany GmbH", False),
    ("Garbe Industrial", "Sirius Facilities GmbH", False),
    ("Aurelis Real Estate GmbH", "Sirius Facilities GmbH", False),   # „Real Estate“ allein verbindet nicht
    # nicht zu sagen: eine Seite fehlt oder ist nur eine Umschreibung
    ("Garbe", None, None),
    (None, "GARBE Industrial GmbH & Co. KG", None),
    ("–", "GARBE Industrial GmbH & Co. KG", None),
    ("ein britischer Investor", "GARBE Industrial GmbH & Co. KG", None),
    ("Projektentwickler", "Hillwood Germany GmbH", None),
])
def test_passt(vermieter, am_objekt, erwartet):
    assert eigentuemer.passt(vermieter, am_objekt) is erwartet


def test_to_unit_liest_eigentuemer_und_einheit():
    """Zeile 3147067 (Oberhausen, Im Waldteich 10) aus GET /v1/units?expand=1, gekürzt."""
    unit = _to_unit({
        "id": 3147067, "unit_id": "Unit 1", "street": "Im Waldteich", "house_number": "10", "city": "Oberhausen",
        "rented": {"label": "Vermietet", "value": True}, "property_space_value": 7955.0,
        "property_status": {"id": 163676, "name": "Abgeschlossen"}, "archived": False,
        "custom_fields": {"eigentumer": {"value": "Hillwood Germany GmbH", "pretty_value": "Hillwood Germany GmbH"}},
    })
    assert (unit.einheit, unit.eigentuemer) == ("Unit 1", "Hillwood Germany GmbH")
    # ohne expand=1 oder ohne Eintrag: leer, kein Fehler
    assert _to_unit({"id": 1}).eigentuemer is None
    assert _to_unit({"id": 1, "custom_fields": {"eigentumer": {"value": "", "pretty_value": ""}}}).eigentuemer is None


# --- Auswahl der KI ----------------------------------------------------------------

WALDTEICH_1 = Unit(id=3147067, name="Im Waldteich 10 - Oberhausen", street="Im Waldteich", house_number="10",
                   city="Oberhausen", einheit="Unit 1", property_space_value=7955.0, eigentuemer="Hillwood Germany GmbH",
                   status_id=VERMARKTUNG)
WALDTEICH_2 = WALDTEICH_1.model_copy(update={"id": 3147070, "einheit": "Unit 2", "property_space_value": 9781.0})
EISENHAMMER = Unit(id=5407874, name="Zum Eisenhammer 52 - Oberhausen", street="Zum Eisenhammer", house_number="52",
                   city="Oberhausen", property_space_value=15891.0, status_id=VERMARKTUNG)
BERNS = Unit(id=6319230, name="Dr.-Berns-Straße 37 - Moers", street="Dr.-Berns-Straße", house_number="37", city="Moers",
             einheit="Gesamtobjekt", property_space_value=18490.0, eigentuemer="BEOS AG", status_id=VERMARKTUNG)
SCHUERMANNSHUETT = Unit(id=2778068, name="Am Schürmannshütt 11 - Moers", street="Am Schürmannshütt", house_number="11",
                        city="Moers", property_space_value=9658.0, eigentuemer="Ixocon Immobilien GmbH & Co. KG",
                        status_id=VERMARKTUNG)
CARL_LEGIEN = Unit(id=5769386, name="Carl-Legien-Straße 15 - Offenbach", street="Carl-Legien-Straße", house_number="15",
                   city="Offenbach", property_space_value=17500.0, eigentuemer="Sirius Facilities GmbH", status_id=VERMARKTUNG)
WEDEL_3 = Unit(id=6159434, name="Industriestraße 60 - Wedel", street="Industriestraße", house_number="60", city="Wedel",
               einheit="Unit 3", property_space_value=3097.0, eigentuemer="thirteen seven GmbH", status_id=VERMARKTUNG)


def _deal(**kw):
    return Deal(deal_typ=DealTyp.VERMIETUNG, ist_vermietung=True, confidence=0.9, **kw)


def _antworten(monkeypatch, *texte):
    """Die KI antwortet der Reihe nach mit den gegebenen JSON-Texten; gemerkt wird jeder Prompt."""
    prompts: list[str] = []

    def create(**kw):
        prompts.append(kw["messages"][0]["content"])
        return types.SimpleNamespace(content=[types.SimpleNamespace(text=texte[len(prompts) - 1])])

    monkeypatch.setattr(match_ai, "_get_client", lambda: types.SimpleNamespace(messages=types.SimpleNamespace(create=create)))
    return prompts


def test_ki_sieht_eigentuemer_und_einheit(monkeypatch):
    prompts = _antworten(monkeypatch, '{"unit_ids": [], "confidence": 0.0, "begruendung": "-"}')
    match_ai.select_match(_deal(objekt_name="Hillwood", vermieter="Hillwood"), [WALDTEICH_1, EISENHAMMER])
    assert '"eigentuemer": "Hillwood Germany GmbH"' in prompts[0]
    assert '"einheit": "Unit 1"' in prompts[0]
    assert '"unit_ids"' in prompts[0]


def test_mehrere_einheiten_desselben_objekts(monkeypatch):
    """Oberhausen, 08.09.2026: Hillwood vermietet 18.400 m² – das sind Unit 1 und Unit 2
    zusammen. Bisher konnte die KI nur eine Einheit nennen und wählte Zum Eisenhammer 52."""
    _antworten(monkeypatch, '{"unit_ids": [3147067, 3147070], "confidence": 0.9, "begruendung": "Summe passt"}')
    res = match_ai.select_match(_deal(vermieter="Hillwood", groessen_hinweis="18400"), [EISENHAMMER, WALDTEICH_1, WALDTEICH_2])
    assert res.status == MatchStatus.UNIQUE
    assert [u.id for u in res.units] == [3147067, 3147070]
    assert "(2 Einheiten)" in res.grund
    assert [u.id for u in res.kandidaten] == [3147067, 3147070, 5407874]


def test_einheiten_verschiedener_objekte_gelten_nicht_zusammen(monkeypatch):
    _antworten(monkeypatch, '{"unit_ids": [3147067, 5407874, 6319230], "confidence": 0.9, "begruendung": "vermischt"}')
    res = match_ai.select_match(_deal(vermieter="Hillwood"), [WALDTEICH_1, EISENHAMMER, BERNS])
    assert [u.id for u in res.units] == [3147067]


def test_alte_antwortform_mit_einer_id_gilt_weiter(monkeypatch):
    _antworten(monkeypatch, '{"unit_id": 5407874, "confidence": 0.9, "begruendung": "alt"}')
    assert [u.id for u in match_ai.select_match(_deal(), [EISENHAMMER]).units] == [5407874]
    _antworten(monkeypatch, '{"unit_ids": [], "confidence": 0.0, "begruendung": "nichts"}')
    assert match_ai.select_match(_deal(), [EISENHAMMER]).status == MatchStatus.NONE
    _antworten(monkeypatch, '{"unit_ids": [999], "confidence": 0.9, "begruendung": "erfunden"}')
    assert match_ai.select_match(_deal(), [EISENHAMMER]).status == MatchStatus.AMBIGUOUS


# --- Eigentümer-Probe --------------------------------------------------------------

def test_zweite_wahl_unter_den_einheiten_des_vermieters(monkeypatch):
    """Moers, 12.11.2026: „tsit mietet von Ixocon“. Die KI wählte die BEOS-Halle
    Dr.-Berns-Straße 37; gemeint war Am Schürmannshütt 11 – Eigentümer Ixocon."""
    prompts = _antworten(
        monkeypatch,
        '{"unit_ids": [6319230], "confidence": 0.55, "begruendung": "plausibelste Halle in Moers"}',
        '{"unit_ids": [2778068], "confidence": 0.85, "begruendung": "Ixocon-Halle in Moers"}',
    )
    res = match_ai.select_match_geprueft(_deal(objekt_name="Ixocon", vermieter="Ixocon", groessen_hinweis="10000"),
                                         [BERNS, SCHUERMANNSHUETT])
    assert [u.id for u in res.units] == [2778068]
    assert res.grund.startswith("Erste Wahl verworfen (Dr.-Berns-Straße 37, Moers (Unit 6319230) gehört BEOS AG")
    assert len(prompts) == 2 and "6319230" not in prompts[1]   # zweite Runde nur unter Ixocon-Einheiten


BRUNHAM = Unit(id=5769418, name="212 EG", street="Brunhamstraße", house_number="21", city="München", einheit="212 EG",
               property_space_value=2448.12, eigentuemer="Sirius Facilities GmbH", status_id=VERMARKTUNG)
RUPERT_BODNER_1 = Unit(id=6219281, name="Haus 1", street="Rupert-Bodner-Straße", house_number="9-21", city="München",
                       einheit="Haus 1", property_space_value=3203.0, eigentuemer="Aurelis Real Estate GmbH",
                       status_id=VERMARKTUNG)
KERPEN = Unit(id=2778125, name="BT I, Halle 3", street="Heinrich-Hertz-Straße", house_number="6", city="Kerpen",
              einheit="BT I, Halle 3", property_space_value=1220.0, eigentuemer="Aurelis Real Estate GmbH",
              status_id=VERMARKTUNG)


def test_zweite_wahl_bleibt_am_ort(monkeypatch):
    """München-Aubing, 11.08.2026: Die Landeshauptstadt mietet rund 7.000 m² von Aurelis. Die
    Aufgabe hing an der Sirius-Fläche Brunhamstraße 21. Im Bestand vom 20.11.2026 liegen
    Aurelis-Einheiten in zwölf Städten; die Suche nach „Aurelis“ bringt sie alle unter die
    Kandidaten. Die zweite Wahl bleibt in München und weicht nicht nach Kerpen aus."""
    prompts = _antworten(
        monkeypatch,
        '{"unit_ids": [5769418], "confidence": 0.6, "begruendung": "Neuaubing"}',
        '{"unit_ids": [], "confidence": 0.0, "begruendung": "Haus 1 ist die freie Resteinheit"}',
    )
    deal = _deal(objekt_name="Unternehmerpark München-Aubing", vermieter="Aurelis Real Estate GmbH", groessen_hinweis="7000")
    res = match_ai.select_match_geprueft(deal, [BRUNHAM, RUPERT_BODNER_1, KERPEN])
    assert len(prompts) == 2 and "6219281" in prompts[1] and "2778125" not in prompts[1]
    assert res.status == MatchStatus.NONE and res.anderer_eigentuemer is True
    # Liegt am Ort gar keine Einheit des Vermieters, gibt es keine zweite Runde.
    prompts = _antworten(monkeypatch, '{"unit_ids": [5769418], "confidence": 0.6, "begruendung": "Neuaubing"}')
    res = match_ai.select_match_geprueft(deal, [BRUNHAM, KERPEN])
    assert len(prompts) == 1 and res.status == MatchStatus.NONE and res.anderer_eigentuemer is True


def test_ort_der_meldung_zaehlt_fuer_die_zweite_wahl(monkeypatch):
    """Die erste Wahl kann im Nachbarort liegen. Nennt die Meldung den Ort, in dem der
    Vermieter eine Einheit hat, gehört sie in die zweite Runde."""
    nachbar = BERNS.model_copy(update={"id": 1, "city": "Duisburg", "name": "Halle in Duisburg"})
    prompts = _antworten(
        monkeypatch,
        '{"unit_ids": [1], "confidence": 0.5, "begruendung": "Region"}',
        '{"unit_ids": [2778068], "confidence": 0.8, "begruendung": "Ixocon in Moers"}',
    )
    res = match_ai.select_match_geprueft(_deal(vermieter="Ixocon", stadt="Moers"), [nachbar, SCHUERMANNSHUETT])
    assert len(prompts) == 2 and [u.id for u in res.units] == [2778068]


def test_anderer_eigentuemer_und_nichts_spricht_dafuer_ist_kein_eigener_bestand(monkeypatch):
    """Offenbach, 17.09.2026: „GKN mietet im Panattoni Park Offenbach“. Unsere Halle
    Carl-Legien-Straße 15 gehört Sirius; keine Fläche genannt. Das war kein eigenes Objekt."""
    _antworten(monkeypatch, '{"unit_ids": [5769386], "confidence": 0.55, "begruendung": "einzige große Halle"}')
    res = match_ai.select_match_geprueft(
        _deal(objekt_name="Panattoni Park Offenbach", vermieter="Panattoni", stadt="Offenbach"), [CARL_LEGIEN])
    assert res.status == MatchStatus.NONE and res.anderer_eigentuemer is True
    assert res.units == [] and "gehört Sirius Facilities GmbH, die Meldung nennt Panattoni" in res.grund
    assert decide(_deal(vermieter="Panattoni"), res).tier == Tier.NONE


def test_anderer_eigentuemer_aber_flaeche_passt_bleibt_als_unsicherer_treffer(monkeypatch):
    """Der Eigentümer am Objekt kann veraltet sein (Entwickler verkauft an Investor). Passt
    die Fläche, bleibt die Einheit zur Prüfung stehen – nie als sicherer Treffer.
    Wedel, 28.10.2026: 3.000 m² gegen Unit 3 mit 3.097 m²."""
    _antworten(monkeypatch, '{"unit_ids": [6159434], "confidence": 0.9, "begruendung": "Fläche passt"}')
    res = match_ai.select_match_geprueft(_deal(vermieter="Aroundtown", groessen_hinweis="3000", stadt="Wedel"), [WEDEL_3])
    assert res.status == MatchStatus.AMBIGUOUS and res.anderer_eigentuemer is False
    assert [u.id for u in res.units] == [6159434]
    assert res.grund.startswith("Eigentümer passt nicht (")


def test_summe_der_adresse_zaehlt_als_passende_flaeche(monkeypatch):
    """Langenselbold: am Objekt steht Hillwood, die Meldung nennt Propel Industrial. Die
    gemeldete Fläche entspricht der Summe der Einheiten an der Adresse – kein Verwerfen."""
    eins = Unit(id=1, street="Diebacher Weg", city="Langenselbold", property_space_value=8040.0, eigentuemer="Hillwood Germany GmbH")
    zwei = eins.model_copy(update={"id": 2, "property_space_value": 11510.0})
    _antworten(monkeypatch, '{"unit_ids": [1], "confidence": 0.6, "begruendung": "Park in Langenselbold"}')
    res = match_ai.select_match_geprueft(_deal(vermieter="Propel Industrial / Invesco Real Estate", groessen_hinweis="19500"), [eins, zwei])
    assert res.status == MatchStatus.AMBIGUOUS and [u.id for u in res.units] == [1]


@pytest.mark.parametrize("vermieter, einheit", [
    ("Hillwood", EISENHAMMER),                 # am Objekt steht kein Eigentümer
    ("ein britischer Investor", CARL_LEGIEN),  # die Meldung nennt keinen Namen
    (None, CARL_LEGIEN),
    ("Sirius", CARL_LEGIEN),                   # derselbe
])
def test_ohne_widerspruch_bleibt_die_wahl(monkeypatch, vermieter, einheit):
    prompts = _antworten(monkeypatch, json.dumps({"unit_ids": [einheit.id], "confidence": 0.9, "begruendung": "ok"}))
    res = match_ai.select_match_geprueft(_deal(vermieter=vermieter), [einheit])
    assert res.status == MatchStatus.UNIQUE and [u.id for u in res.units] == [einheit.id]
    assert len(prompts) == 1


@pytest.mark.parametrize("hinweis, erwartet", [
    ("6000", 6000.0), ("rund 6.700 m²", 6700.0), ("18.400", 18400.0), ("23175", 23175.0),
    (None, None), ("kleinste", None), ("", None), ("12", None),
])
def test_groesse(hinweis, erwartet):
    assert match_ai.groesse(_deal(groessen_hinweis=hinweis)) == erwartet


# --- Verlängerung ------------------------------------------------------------------

def test_verlaengerung_ist_keine_neue_vermietung():
    """Frickenhausen, 29.09.2026: „Wezel verlängert Mietvertrag mit CTP“ ergab eine Aufgabe."""
    deal = _deal(objekt_name="CTP", vermieter="CTP", mieter="Wezel GmbH Kaltumformtechnik", ist_verlaengerung=True)
    treffer = MatchResult(status=MatchStatus.UNIQUE, units=[EISENHAMMER])
    entscheidung = decide(deal, treffer)
    assert entscheidung.tier == Tier.NONE and "Verlängerung" in entscheidung.grund
    assert decide(_deal(objekt_name="CTP"), treffer).tier == Tier.B   # ohne das Kennzeichen wie bisher (DRY_RUN)


# --- Ablauf einer Nachricht --------------------------------------------------------

@pytest.fixture
def ablauf(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("NO_WRITE", "false")
    angelegt: list = []
    antworten: list[str] = []
    gesucht: list[str] = []
    monkeypatch.setattr(main, "create_task", lambda payload: angelegt.append(payload) or 9000 + len(angelegt))
    monkeypatch.setattr(main, "propose_search_terms", lambda deal: gesucht.append(deal.objekt_name) or [])
    monkeypatch.setattr(main, "gather_candidates", lambda deal, extra_queries=None: [CARL_LEGIEN])
    monkeypatch.setattr(main, "get_permalink", lambda ts: "https://example.invalid/p1")
    monkeypatch.setattr(main, "add_checkmark", lambda ts: True)
    monkeypatch.setattr(main, "post_thread_reply", lambda ts, text: antworten.append(text) or True)
    monkeypatch.setattr(main, "append_record", lambda record: None)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    monkeypatch.setattr(review_dedup, "fetch_open_review_units", lambda broker, praefix, tage=None: {})
    return angelegt, antworten, gesucht


def _verarbeite(monkeypatch, deals, wahl):
    monkeypatch.setattr(main, "extract_deals", lambda text: NewsletterExtraction(deals=deals))
    monkeypatch.setattr(main, "select_open_match", lambda deal, candidates: wahl[deal.objekt_name])
    report = RunReport()
    main._process_message({"ts": "1763550000.000100", "text": "Logistik-Deal Radar"}, "run1", report, OffeneReviews())
    return report


def test_fremder_eigentuemer_und_verlaengerung_ergeben_keine_aufgabe(ablauf, monkeypatch):
    angelegt, antworten, gesucht = ablauf
    fremd = (MatchResult(status=MatchStatus.NONE, grund="Kein eigener Bestand: …", anderer_eigentuemer=True), False)
    report = _verarbeite(monkeypatch, [
        _deal(objekt_name="Panattoni Park Offenbach", vermieter="Panattoni"),
        _deal(objekt_name="CTP", vermieter="CTP", ist_verlaengerung=True),
    ], {"Panattoni Park Offenbach": fremd})

    assert angelegt == []
    assert gesucht == ["Panattoni Park Offenbach"]   # für die Verlängerung wird gar nicht erst gesucht
    assert (report.vermietungen, report.anderer_eigentuemer, report.verlaengerungen, report.ignoriert) == (2, 1, 1, 0)
    assert "1 ohne Aufgabe: Das Objekt am Ort gehört einem anderen Eigentümer" in antworten[0]
    assert "1 ohne Aufgabe: bloße Vertragsverlängerung" in antworten[0]


def test_auswertungszeile_nur_im_lese_lauf(ablauf, monkeypatch, caplog):
    treffer = (MatchResult(status=MatchStatus.AMBIGUOUS, units=[CARL_LEGIEN], kandidaten=[CARL_LEGIEN], grund="KI-Treffer unsicher"), False)
    deals = [_deal(objekt_name="Sirius", vermieter="Sirius", mieter="Muster GmbH", groessen_hinweis="17500")]
    with caplog.at_level("INFO"):
        _verarbeite(monkeypatch, deals, {"Sirius": treffer})
    assert not [r for r in caplog.records if r.getMessage().startswith("AUSWERTUNG ")]

    monkeypatch.setenv("NO_WRITE", "true")
    caplog.clear()
    with caplog.at_level("INFO"):
        _verarbeite(monkeypatch, deals, {"Sirius": treffer})
    zeilen = [json.loads(r.getMessage()[len("AUSWERTUNG "):]) for r in caplog.records if r.getMessage().startswith("AUSWERTUNG ")]
    assert len(zeilen) == 1
    assert zeilen[0]["ts"] == "1763550000.000100" and zeilen[0]["units"] == [5769386]
    assert (zeilen[0]["mieter"], zeilen[0]["vermieter"], zeilen[0]["stufe"]) == ("Muster GmbH", "Sirius", "B")


def test_haken_wird_nur_im_lese_lauf_uebergangen(monkeypatch):
    """IGNORE_CHECKMARK darf einen schreibenden Lauf nie dazu bringen, einen schon
    ausgewerteten Digest noch einmal zu verarbeiten."""
    from newsletter_handler import config
    monkeypatch.setenv("IGNORE_CHECKMARK", "true")
    monkeypatch.setenv("NO_WRITE", "false")
    assert config.ignore_checkmark() is False
    monkeypatch.setenv("NO_WRITE", "true")
    assert config.ignore_checkmark() is True
    monkeypatch.setenv("IGNORE_CHECKMARK", "false")
    assert config.ignore_checkmark() is False
