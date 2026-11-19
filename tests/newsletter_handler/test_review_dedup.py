"""Dublettenschutz für Review-Aufgaben und Umgang mit bereits abgeschlossenen Einheiten.

Anlass (Propstack-Stand 19.11.2026, Review-Sitz 254958): 156 offene Aufgaben
„Newsletter-Vermietung prüfen“. 58 davon wiederholten nur eine ältere offene Aufgabe
zur selben Einheit, 40 zeigten auf Einheiten, die vermietet/abgeschlossen/archiviert waren.
Die Zeilen unten sind so aufgebaut, wie GET /v1/activities und GET /v1/units sie liefern.
"""
from __future__ import annotations

import pytest

from newsletter_handler import config, main, match_ai, propstack, review_dedup
from newsletter_handler.models import (
    Deal,
    DealTyp,
    MatchResult,
    MatchStatus,
    NewsletterExtraction,
    RunReport,
    Unit,
)
from newsletter_handler.propstack import _to_unit, fetch_open_review_units
from newsletter_handler.review_dedup import OffeneReviews

ABGESCHLOSSEN = config.STATUS_ABGESCHLOSSEN
VERMARKTUNG = 163674


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _aufgabe(activity_id, task_id, title, unit_ids, *, done=None, angelegt="2026-10-16T09:59:46.949+02:00"):
    """Eine Zeile aus GET /v1/activities?item_type=reminder (gekürzt auf die genutzten Felder)."""
    return {
        "id": activity_id,
        "activatable_id": task_id,
        "title": title,
        "done": done,
        "broker_id": 254958,
        "property_ids": unit_ids,
        "original_created_at": angelegt,
    }


# --- _to_unit: Status und Archiv -------------------------------------------------

def test_to_unit_liest_status_aus_property_status():
    unit = _to_unit({
        "id": 5032898, "name": "Westring 8 - Dissen am Teutoburger Wald", "archived": False,
        "property_status": {"id": 163676, "name": "Abgeschlossen", "position": 5},
        "rented": {"label": "Vermietet", "value": True},
    })
    assert unit.status_id == ABGESCHLOSSEN
    assert unit.archived is False
    assert unit.ist_abgeschlossen(ABGESCHLOSSEN)


def test_to_unit_ohne_status_gilt_als_offen():
    unit = _to_unit({"id": 1, "rented": {"label": "Vermietet", "value": False}, "property_status": None})
    assert unit.status_id is None
    assert not unit.ist_abgeschlossen(ABGESCHLOSSEN)


@pytest.mark.parametrize("unit,erwartet", [
    (Unit(id=1, rented=True), True),                       # als vermietet geführt
    (Unit(id=2, status_id=ABGESCHLOSSEN), True),           # Status Abgeschlossen, rented nicht gesetzt
    (Unit(id=3, archived=True), True),                     # archiviert
    (Unit(id=4, rented=False, status_id=VERMARKTUNG), False),
    (Unit(id=5), False),                                   # keine Angaben -> offen
])
def test_ist_abgeschlossen(unit, erwartet):
    assert unit.ist_abgeschlossen(ABGESCHLOSSEN) is erwartet


# --- fetch_open_review_units ------------------------------------------------------

def test_offene_reviews_nur_eigene_offene_aufgaben(monkeypatch):
    seite = {"data": [
        _aufgabe(1, 101, "Newsletter-Vermietung prüfen: Garbe Industrial", [5032898]),
        _aufgabe(2, 102, "Newsletter-Vermietung prüfen: CTP", [5769426], done=True),      # erledigt
        _aufgabe(3, 103, "Flächenupdate abgleichen: Panattoni", [777]),                   # andere Art
        _aufgabe(4, 104, "Newsletter-Vermietung prüfen: ohne Objekt", []),                # kein Objekt
        _aufgabe(5, 105, "Newsletter-Vermietung prüfen: Ganzes Objekt", [11, 12]),
    ], "meta": {"total_count": 5}}
    monkeypatch.setattr(propstack, "_request", lambda *a, **k: _Response(seite))
    monkeypatch.setenv("PROPSTACK_API_KEY", "x")

    assert fetch_open_review_units(254958, config.REVIEW_TITEL_PRAEFIX) == {5032898: 101, 11: 105, 12: 105}


def test_offene_reviews_aelteste_aufgabe_gewinnt(monkeypatch):
    seite = {"data": [
        _aufgabe(3, 303, "Newsletter-Vermietung prüfen: Garbe", [5032898], angelegt="2026-10-30T10:46:10.244+01:00"),
        _aufgabe(1, 301, "Newsletter-Vermietung prüfen: Garbe Industrial", [5032898], angelegt="2026-10-16T09:59:46.949+02:00"),
        _aufgabe(2, 302, "Newsletter-Vermietung prüfen: Garbe Industrial", [5032898], angelegt="2026-10-17T09:37:14.396+02:00"),
    ]}
    monkeypatch.setattr(propstack, "_request", lambda *a, **k: _Response(seite))
    monkeypatch.setenv("PROPSTACK_API_KEY", "x")

    assert fetch_open_review_units(254958, config.REVIEW_TITEL_PRAEFIX) == {5032898: 301}


def test_offene_reviews_liest_alle_seiten(monkeypatch):
    seiten = {
        1: [_aufgabe(i, 1000 + i, "Newsletter-Vermietung prüfen: A", [i]) for i in range(1, 201)],
        2: [_aufgabe(999, 1999, "Newsletter-Vermietung prüfen: B", [999])],
    }
    gesehen = []

    def fake_request(method, path, *, key, params=None, json=None):
        gesehen.append(params["page"])
        return _Response({"data": seiten[params["page"]]})

    monkeypatch.setattr(propstack, "_request", fake_request)
    monkeypatch.setattr(propstack.time, "sleep", lambda s: None)
    monkeypatch.setenv("PROPSTACK_API_KEY", "x")

    result = fetch_open_review_units(254958, config.REVIEW_TITEL_PRAEFIX)
    assert gesehen == [1, 2]
    assert len(result) == 201 and result[999] == 1999


# --- OffeneReviews ----------------------------------------------------------------

def test_vorhanden_nur_wenn_jede_einheit_abgedeckt(monkeypatch):
    monkeypatch.setattr(review_dedup, "fetch_open_review_units", lambda broker, praefix, tage=None: {11: 105})
    offene = OffeneReviews()
    assert offene.vorhanden([11]) == (True, 105)
    assert offene.vorhanden([11, 12]) == (False, None)   # Einheit 12 hätte sonst nie eine Aufgabe
    assert offene.vorhanden([]) == (False, None)         # ohne Objekt nichts zu vergleichen


def test_bestand_wird_einmal_je_lauf_geladen_und_ergaenzt(monkeypatch):
    aufrufe = []
    monkeypatch.setattr(review_dedup, "fetch_open_review_units",
                        lambda broker, praefix, tage=None: aufrufe.append(1) or {})
    offene = OffeneReviews()
    assert offene.vorhanden([7]) == (False, None)
    offene.merke([7], 4711)
    assert offene.vorhanden([7]) == (True, 4711)
    assert len(aufrufe) == 1


def test_laden_fehlgeschlagen_dann_wird_angelegt(monkeypatch):
    def kaputt(broker, praefix, tage=None):
        raise RuntimeError("HTTP 500")

    monkeypatch.setattr(review_dedup, "fetch_open_review_units", kaputt)
    offene = OffeneReviews()
    assert offene.vorhanden([7]) == (False, None)
    assert offene.laden_fehlgeschlagen is True


# --- select_open_match -------------------------------------------------------------

DISSEN_ZU = Unit(id=5032898, name="Westring 8 - Dissen am Teutoburger Wald", street="Westring",
                 house_number="8", city="Dissen am Teutoburger Wald", rented=True, status_id=ABGESCHLOSSEN)
SALZGITTER_OFFEN = Unit(id=2777978, name="Gottfried-Linke-Straße - Salzgitter", city="Salzgitter",
                        rented=False, status_id=VERMARKTUNG)
KOELN_DUBLETTE = Unit(id=5255688, name="Geestemünder Straße - Köln", street="Geestemünder Straße",
                      city="Köln", rented=False, status_id=ABGESCHLOSSEN)
KOELN_ECHT = Unit(id=4114850, name="Panattoni Park Köln II – Unit 1", street="Geestemünder Straße",
                  city="Köln", rented=False, status_id=VERMARKTUNG)
DEAL = Deal(deal_typ=DealTyp.VERMIETUNG, ist_vermietung=True, objekt_name="Garbe Industrial", confidence=0.9)


def _ki(antworten):
    """Ersetzt select_match: liefert der Reihe nach die vorgegebenen Ergebnisse und
    merkt sich, unter welchen Kandidaten jeweils gewählt wurde."""
    aufrufe = []

    def fake(deal, candidates):
        aufrufe.append([u.id for u in candidates])
        return antworten[len(aufrufe) - 1]

    return fake, aufrufe


def test_offene_wahl_bleibt_unveraendert(monkeypatch):
    treffer = MatchResult(status=MatchStatus.UNIQUE, units=[SALZGITTER_OFFEN], kandidaten=[SALZGITTER_OFFEN])
    fake, aufrufe = _ki([treffer])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL, [SALZGITTER_OFFEN, DISSEN_ZU])
    assert match is treffer and schon_zu is False
    assert len(aufrufe) == 1


def test_sichere_wahl_abgeschlossen_ohne_offene_einheit_am_ort_ist_erledigt(monkeypatch):
    """Dissen: Die KI ist sicher, das Objekt ist abgeschlossen, die offene Einheit in Salzgitter
    ist ein anderer Ort."""
    fake, aufrufe = _ki([MatchResult(status=MatchStatus.UNIQUE, units=[DISSEN_ZU],
                                     kandidaten=[DISSEN_ZU, SALZGITTER_OFFEN])])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL, [DISSEN_ZU, SALZGITTER_OFFEN])
    assert match.status == MatchStatus.NONE and schon_zu is True
    assert "bereits vermietet/abgeschlossen" in match.grund
    assert len(aufrufe) == 1  # kein zweiter KI-Aufruf


def test_unsichere_wahl_abgeschlossen_zweite_wahl_unter_allen_offenen(monkeypatch):
    """Eine unsichere erste Wahl kann schlicht falsch sein – dann zählt auch eine offene
    Einheit an einem anderen Ort (Befund des Gegenlesens, 19.11.2026)."""
    erste = MatchResult(status=MatchStatus.AMBIGUOUS, units=[DISSEN_ZU], kandidaten=[DISSEN_ZU, SALZGITTER_OFFEN])
    zweite = MatchResult(status=MatchStatus.AMBIGUOUS, units=[SALZGITTER_OFFEN], kandidaten=[SALZGITTER_OFFEN], grund="KI-Treffer unsicher")
    fake, aufrufe = _ki([erste, zweite])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL, [DISSEN_ZU, SALZGITTER_OFFEN])
    assert schon_zu is False and [u.id for u in match.units] == [SALZGITTER_OFFEN.id]
    assert aufrufe[1] == [SALZGITTER_OFFEN.id]


def test_unsichere_wahl_abgeschlossen_und_kein_offener_passt_ist_erledigt(monkeypatch):
    erste = MatchResult(status=MatchStatus.AMBIGUOUS, units=[DISSEN_ZU], kandidaten=[DISSEN_ZU, SALZGITTER_OFFEN])
    fake, aufrufe = _ki([erste, MatchResult(status=MatchStatus.NONE, grund="KI: kein passendes Objekt")])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL, [DISSEN_ZU, SALZGITTER_OFFEN])
    assert match.status == MatchStatus.NONE and schon_zu is True and len(aufrufe) == 2


def test_stillgelegte_dublette_zweite_wahl_unter_offenen_am_selben_ort(monkeypatch):
    """Köln: Die KI wählt die stillgelegte Dublette; der richtige Datensatz ist in Vermarktung."""
    erste = MatchResult(status=MatchStatus.UNIQUE, units=[KOELN_DUBLETTE], kandidaten=[KOELN_DUBLETTE, KOELN_ECHT])
    zweite = MatchResult(status=MatchStatus.UNIQUE, units=[KOELN_ECHT], kandidaten=[KOELN_ECHT], grund="KI-Zuordnung")
    fake, aufrufe = _ki([erste, zweite])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL, [KOELN_DUBLETTE, KOELN_ECHT, SALZGITTER_OFFEN])
    assert schon_zu is False
    assert [u.id for u in match.units] == [KOELN_ECHT.id]
    assert aufrufe[1] == [KOELN_ECHT.id]          # zweite Wahl nur unter offenen Einheiten in Köln
    assert "Erste Wahl bereits abgeschlossen" in match.grund


def test_zweite_wahl_ohne_treffer_ist_erledigt(monkeypatch):
    erste = MatchResult(status=MatchStatus.UNIQUE, units=[KOELN_DUBLETTE], kandidaten=[KOELN_DUBLETTE, KOELN_ECHT])
    zweite = MatchResult(status=MatchStatus.NONE, grund="KI: kein passendes Objekt")
    fake, _ = _ki([erste, zweite])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL, [KOELN_DUBLETTE, KOELN_ECHT])
    assert match.status == MatchStatus.NONE and schon_zu is True


# --- Ablauf einer Nachricht --------------------------------------------------------

@pytest.fixture
def ablauf(monkeypatch):
    """_process_message ohne Netz: KI, Propstack und Slack sind ersetzt."""
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("NO_WRITE", "false")
    angelegt: list = []
    antworten: list[str] = []

    def fake_create_task(payload):
        angelegt.append(payload)
        return 9000 + len(angelegt)

    monkeypatch.setattr(main, "create_task", fake_create_task)
    monkeypatch.setattr(main, "propose_search_terms", lambda deal: [])
    monkeypatch.setattr(main, "get_permalink", lambda ts: "https://example.invalid/p1")
    monkeypatch.setattr(main, "add_checkmark", lambda ts: True)
    monkeypatch.setattr(main, "post_thread_reply", lambda ts, text: antworten.append(text) or True)
    monkeypatch.setattr(main, "append_record", lambda record: None)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    return angelegt, antworten


def _deal(name):
    return Deal(deal_typ=DealTyp.VERMIETUNG, ist_vermietung=True, objekt_name=name, confidence=0.9)


def _lauf(monkeypatch, deals, wahl, bestand):
    """Verarbeitet eine Digest-Nachricht. wahl: Objektname -> (MatchResult, bereits_abgeschlossen)."""
    monkeypatch.setattr(main, "extract_deals", lambda text: NewsletterExtraction(deals=deals))
    monkeypatch.setattr(main, "gather_candidates", lambda deal, extra_queries=None: [SALZGITTER_OFFEN])
    monkeypatch.setattr(main, "select_open_match", lambda deal, candidates: wahl[deal.objekt_name])
    monkeypatch.setattr(review_dedup, "fetch_open_review_units", lambda broker, praefix, tage=None: dict(bestand))
    report = RunReport()
    main._process_message({"ts": "1763550000.000100", "text": "Logistik-Deal Radar"}, "run1", report, OffeneReviews())
    return report


def test_zweimal_dieselbe_einheit_in_einem_digest_ergibt_eine_aufgabe(ablauf, monkeypatch):
    angelegt, antworten = ablauf
    treffer = (MatchResult(status=MatchStatus.AMBIGUOUS, units=[SALZGITTER_OFFEN], kandidaten=[SALZGITTER_OFFEN]), False)
    report = _lauf(monkeypatch, [_deal("Garbe Industrial"), _deal("Garbe")],
                   {"Garbe Industrial": treffer, "Garbe": treffer}, bestand={})

    assert len(angelegt) == 1
    assert angelegt[0].title == "Newsletter-Vermietung prüfen: Garbe Industrial"
    assert angelegt[0].property_ids == [SALZGITTER_OFFEN.id]
    assert (report.stufe_b, report.bereits_offen) == (1, 1)
    assert "1 Review-Aufgabe(n) erstellt" in antworten[0]
    assert "1 ohne neue Aufgabe" in antworten[0]


def test_offene_aufgabe_von_gestern_verhindert_neue(ablauf, monkeypatch):
    angelegt, antworten = ablauf
    treffer = (MatchResult(status=MatchStatus.AMBIGUOUS, units=[SALZGITTER_OFFEN], kandidaten=[SALZGITTER_OFFEN]), False)
    report = _lauf(monkeypatch, [_deal("Garbe Industrial")], {"Garbe Industrial": treffer},
                   bestand={SALZGITTER_OFFEN.id: 160584509})

    assert angelegt == []
    assert (report.stufe_b, report.bereits_offen) == (0, 1)
    assert "0 Review-Aufgabe(n) erstellt" in antworten[0]


def test_abgeschlossene_einheit_ergibt_keine_aufgabe(ablauf, monkeypatch):
    angelegt, antworten = ablauf
    erledigt = (MatchResult(status=MatchStatus.NONE, grund="Westring 8 … bereits vermietet/abgeschlossen"), True)
    report = _lauf(monkeypatch, [_deal("Garbe Industrial")], {"Garbe Industrial": erledigt}, bestand={})

    assert angelegt == []
    assert (report.stufe_b, report.bereits_abgeschlossen, report.ignoriert) == (0, 1, 0)
    assert "bereits vermietet/abgeschlossen" in antworten[0]


def test_ohne_objekt_wird_weiter_jede_aufgabe_angelegt(ablauf, monkeypatch):
    """Ohne zugeordnete Einheit gibt es nichts zu vergleichen – Verhalten wie bisher."""
    angelegt, _ = ablauf
    unklar = (MatchResult(status=MatchStatus.AMBIGUOUS, kandidaten=[SALZGITTER_OFFEN], grund="KI-Auswahl fehlgeschlagen"), False)
    report = _lauf(monkeypatch, [_deal("Park A"), _deal("Park A")], {"Park A": unklar}, bestand={})

    assert len(angelegt) == 2
    assert all(a.property_ids is None for a in angelegt)
    assert (report.stufe_b, report.bereits_offen) == (2, 0)


# --- Nachträge aus dem Gegenlesen (19.11.2026) ----------------------------------------

def test_alte_offene_aufgabe_unterdrueckt_keine_neue_meldung(monkeypatch):
    """Der Radar wiederholt über Tage – eine Meldung Monate später ist meist eine neue
    Vermietung. Ohne Grenze bekäme eine Einheit nie wieder eine Aufgabe."""
    from datetime import datetime, timedelta, timezone

    jetzt = datetime.now(timezone.utc)
    seite = {"data": [
        _aufgabe(1, 101, "Newsletter-Vermietung prüfen: frisch", [11], angelegt=(jetzt - timedelta(days=3)).isoformat()),
        _aufgabe(2, 102, "Newsletter-Vermietung prüfen: alt", [12], angelegt=(jetzt - timedelta(days=90)).isoformat()),
    ]}
    monkeypatch.setattr(propstack, "_request", lambda *a, **k: _Response(seite))
    monkeypatch.setenv("PROPSTACK_API_KEY", "x")

    assert fetch_open_review_units(254958, config.REVIEW_TITEL_PRAEFIX, 30) == {11: 101}
    assert fetch_open_review_units(254958, config.REVIEW_TITEL_PRAEFIX) == {11: 101, 12: 102}


def test_dublettenschutz_nicht_ladbar_macht_den_lauf_rot(monkeypatch):
    """Angelegt wird trotzdem – aber nicht mehr still: sonst entstehen wieder Dubletten in einem grünen Lauf."""
    def kaputt(broker, praefix, tage=None):
        raise RuntimeError("HTTP 500")

    monkeypatch.setattr(review_dedup, "fetch_open_review_units", kaputt)
    monkeypatch.setattr(main, "get_bot_user_id", lambda: "UBOT")
    monkeypatch.setattr(main, "_collect_messages", lambda: [{"ts": "1.1", "text": "Radar"}])
    monkeypatch.setattr(main, "has_bot_checkmark", lambda msg, bot: False)

    def verarbeite(msg, run_id, report, offene_reviews):
        offene_reviews.vorhanden([7])   # löst das Laden aus

    monkeypatch.setattr(main, "_process_message", verarbeite)
    report = main.run_pipeline()
    assert len(report.fehler) == 1 and "ohne Dublettenschutz" in report.fehler[0]


def test_scheitert_ein_deal_gibt_es_keinen_haken(ablauf, monkeypatch):
    """Sonst gälte der Digest als ausgewertet, obwohl ein Deal verloren ging."""
    angelegt, antworten = ablauf
    haken = []
    monkeypatch.setattr(main, "add_checkmark", lambda ts: haken.append(ts) or True)

    def kaputt(payload):
        raise RuntimeError("HTTP 502")

    monkeypatch.setattr(main, "create_task", kaputt)
    treffer = (MatchResult(status=MatchStatus.AMBIGUOUS, units=[SALZGITTER_OFFEN], kandidaten=[SALZGITTER_OFFEN]), False)
    report = _lauf(monkeypatch, [_deal("Garbe Industrial")], {"Garbe Industrial": treffer}, bestand={})

    assert haken == [] and antworten == []
    assert len(report.fehler) == 1
