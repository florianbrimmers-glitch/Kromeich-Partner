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
    Einheit an einem anderen Ort (Befund des Gegenlesens, 19.11.2026). Seit dem Lese-Lauf
    vom 20.11.2026 nur noch, wenn die gemeldete Fläche auf sie passt."""
    offen = SALZGITTER_OFFEN.model_copy(update={"property_space_value": 31000.0})
    erste = MatchResult(status=MatchStatus.AMBIGUOUS, units=[DISSEN_ZU], kandidaten=[DISSEN_ZU, offen])
    zweite = MatchResult(status=MatchStatus.AMBIGUOUS, units=[offen], kandidaten=[offen], grund="KI-Treffer unsicher")
    fake, aufrufe = _ki([erste, zweite])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL.model_copy(update={"groessen_hinweis": "31000"}), [DISSEN_ZU, offen])
    assert schon_zu is False and [u.id for u in match.units] == [offen.id]
    assert aufrufe[1] == [offen.id]
    assert "Erste Wahl bereits abgeschlossen" in match.grund


def test_zweite_wahl_ohne_flaechenbeleg_ist_erledigt(monkeypatch):
    """Köln-Niehl, 17.11.2026: „Goodcang mietet 40.000 m² im Panattoni Park Köln II“. Der
    gemeinte Datensatz 5255688 ist abgeschlossen und trägt keine Fläche; die zweite Wahl
    fiel auf Am Niehler Hafen 2 (ohne Fläche, conf 0.50). Im Lese-Lauf vom 20.11.2026
    entstanden aus solchen zweiten Wahlen 8 Aufgaben, alle an einer freien Nachbar-Einheit."""
    hafen = Unit(id=2778001, name="Am Niehler Hafen 2 - Köln", street="Am Niehler Hafen", house_number="2",
                 city="Köln", status_id=VERMARKTUNG)
    erste = MatchResult(status=MatchStatus.UNIQUE, units=[KOELN_DUBLETTE], kandidaten=[KOELN_DUBLETTE, hafen])
    zweite = MatchResult(status=MatchStatus.AMBIGUOUS, units=[hafen], kandidaten=[hafen], grund="KI-Treffer unsicher (conf 0.50)")
    fake, aufrufe = _ki([erste, zweite])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL.model_copy(update={"groessen_hinweis": "40000"}), [KOELN_DUBLETTE, hafen])
    assert match.status == MatchStatus.NONE and schon_zu is True and len(aufrufe) == 2
    assert "passt zur gemeldeten Fläche" in match.grund


def test_flaeche_passt_auf_die_abgeschlossene_wahl_ohne_zweiten_ki_aufruf(monkeypatch):
    """Krefeld, 04.09.2026: CTP vermietet 19.000 m². Gewählt ist Unit 1 (19.020 m²,
    abgeschlossen). Bisher folgte eine zweite Wahl und eine Aufgabe an Unit 03 (3.318 m²)."""
    unit1 = Unit(id=5381316, name="Unit 1 (Platzhalter)", city="Krefeld", property_space_value=19020.0,
                 rented=True, status_id=ABGESCHLOSSEN)
    unit03 = Unit(id=5568526, name="Unit 03", street="Krützpoort", house_number="14", city="Krefeld",
                  property_space_value=3318.0, status_id=VERMARKTUNG)
    fake, aufrufe = _ki([MatchResult(status=MatchStatus.UNIQUE, units=[unit1], kandidaten=[unit1, unit03])])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL.model_copy(update={"groessen_hinweis": "19000"}), [unit1, unit03])
    assert match.status == MatchStatus.NONE and schon_zu is True and len(aufrufe) == 1


def test_ohne_flaechenangabe_gibt_es_keine_zweite_wahl(monkeypatch):
    """Köln, 18.11.2026: dieselbe Vermietung noch einmal, diesmal ohne Fläche. Gewählt ist
    der abgeschlossene Datensatz 5255688. Ohne Fläche in der Meldung spricht nichts für
    eine andere Einheit – kein zweiter KI-Aufruf."""
    erste = MatchResult(status=MatchStatus.UNIQUE, units=[KOELN_DUBLETTE], kandidaten=[KOELN_DUBLETTE, KOELN_ECHT])
    fake, aufrufe = _ki([erste])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL, [KOELN_DUBLETTE, KOELN_ECHT, SALZGITTER_OFFEN])
    assert match.status == MatchStatus.NONE and schon_zu is True and len(aufrufe) == 1


def test_zweite_wahl_nur_unter_offenen_am_selben_ort(monkeypatch):
    """Konstruiert (kein Fall im Lese-Lauf): sichere erste Wahl, abgeschlossen, Fläche passt
    nicht auf sie. Zweite Wahl nur unter den offenen Einheiten am selben Ort – und sie
    zählt, weil die Fläche passt."""
    zu = KOELN_DUBLETTE.model_copy(update={"property_space_value": 12000.0})
    echt = KOELN_ECHT.model_copy(update={"property_space_value": 40500.0})
    erste = MatchResult(status=MatchStatus.UNIQUE, units=[zu], kandidaten=[zu, echt])
    zweite = MatchResult(status=MatchStatus.UNIQUE, units=[echt], kandidaten=[echt], grund="KI-Zuordnung")
    fake, aufrufe = _ki([erste, zweite])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL.model_copy(update={"groessen_hinweis": "40000"}), [zu, echt, SALZGITTER_OFFEN])
    assert schon_zu is False and [u.id for u in match.units] == [echt.id]
    assert aufrufe[1] == [echt.id]                # nicht Salzgitter
    assert "Erste Wahl bereits abgeschlossen" in match.grund


def test_zweite_wahl_ohne_treffer_ist_erledigt(monkeypatch):
    zu = KOELN_DUBLETTE.model_copy(update={"property_space_value": 12000.0})
    erste = MatchResult(status=MatchStatus.UNIQUE, units=[zu], kandidaten=[zu, KOELN_ECHT])
    zweite = MatchResult(status=MatchStatus.NONE, grund="KI: kein passendes Objekt")
    fake, aufrufe = _ki([erste, zweite])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL.model_copy(update={"groessen_hinweis": "40000"}), [zu, KOELN_ECHT])
    assert match.status == MatchStatus.NONE and schon_zu is True and len(aufrufe) == 2


def test_flaeche_passt_auf_die_abgeschlossene_einheit_ist_erledigt(monkeypatch):
    """Offenbach, 13.10.2026: „Dauch mietet 5.200 m² im Panattoni Park Offenbach“. Halle 1
    (4.940 m²) ist vermietet, Halle 2 (4.940 m²) frei; die KI nannte beide. Die Fläche ist
    mit der vermieteten Halle erklärt – keine Aufgabe an der freien."""
    halle1 = Unit(id=5758704, city="Offenbach am Main", property_space_value=4940.0, rented=True, status_id=ABGESCHLOSSEN)
    halle2 = Unit(id=5758705, city="Offenbach am Main", property_space_value=4940.0, status_id=VERMARKTUNG)
    fake, aufrufe = _ki([MatchResult(status=MatchStatus.AMBIGUOUS, units=[halle1, halle2], kandidaten=[halle1, halle2])])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL.model_copy(update={"groessen_hinweis": "5200"}), [halle1, halle2])
    assert match.status == MatchStatus.NONE and schon_zu is True and len(aufrufe) == 1


def test_teils_vermieteter_park_ohne_flaechenangabe_ist_keine_aufgabe(monkeypatch):
    """Mülheim, Flex City, 16.09.2026: vier Einheiten genannt, Unit 1 und Unit 2 vermietet,
    keine Fläche in der Meldung. Für Unit 3 und den Turm spricht nichts."""
    zu = [Unit(id=i, city="Mülheim an der Ruhr", property_space_value=f, rented=True, status_id=ABGESCHLOSSEN)
          for i, f in ((4807585, 10685.0), (4807591, 4860.0))]
    frei = [Unit(id=i, city="Mülheim an der Ruhr", property_space_value=f, status_id=VERMARKTUNG)
            for i, f in ((4807608, 8798.0), (5766104, 17293.0))]
    fake, _ = _ki([MatchResult(status=MatchStatus.AMBIGUOUS, units=zu + frei, kandidaten=zu + frei)])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL, zu + frei)
    assert match.status == MatchStatus.NONE and schon_zu is True
    assert "für die 2 offene(n) Einheit(en) daneben spricht keine Fläche" in match.grund


# Log Plaza Frankfurt (Oder), Belgische Straße 2 – Flächen wie am 21.11.2026 gelesen.
_HALLE_B = [(5050191, 9865.0), (5050066, 10464.0), (5054002, 9788.0), (5054026, 10498.0), (5054059, 7204.0),
            (5054080, 7936.0), (5054095, 10764.0), (5050565, 11642.0), (5050578, 10896.0), (5050591, 8603.0)]


def _log_plaza(a_zu: bool, b_zu: bool) -> list[Unit]:
    def unit(i, flaeche, zu):
        return Unit(id=i, city="Frankfurt (Oder)", property_space_value=flaeche, rented=zu,
                    status_id=ABGESCHLOSSEN if zu else VERMARKTUNG)
    return ([unit(i, None, a_zu) for i in (5033678, 5033679, 5033680, 5033681)]      # Halle A: keine Fläche am Datensatz
            + [unit(i, f, b_zu) for i, f in _HALLE_B]                               # Halle B: zusammen 97.660 m²
            + [unit(i, 11400.0, False) for i in (5050615, 5050622)])                 # Halle C: frei


def test_frankfurt_oder_wie_es_falsch_stand_ergibt_aufgabe_an_den_offenen(monkeypatch):
    """Bis zum 20.11.2026 stand Halle A auf vermietet und Halle B auf frei – umgekehrt zur
    Meldung „94.000 m² vermietet“. Die KI nennt den ganzen Park (16 Einheiten). Die Regel
    „Einheit geschlossen → nichts zu tun“ hätte die Meldung verschluckt: Halle A erklärt
    die Fläche nicht, aus den offenen Einheiten lässt sie sich bilden."""
    park = _log_plaza(a_zu=True, b_zu=False)
    fake, _ = _ki([MatchResult(status=MatchStatus.AMBIGUOUS, units=park, kandidaten=park, grund="Objekt erkannt")])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL.model_copy(update={"groessen_hinweis": "94000"}), park)
    assert schon_zu is False and match.status == MatchStatus.AMBIGUOUS
    assert len(match.units) == 12 and 5033678 not in [u.id for u in match.units]
    assert "4 der genannten Einheiten sind schon vermietet" in match.grund


def test_frankfurt_oder_wie_es_heute_steht_ist_erledigt(monkeypatch):
    """Seit dem 20.11.2026: Halle B abgeschlossen (zusammen 97.660 m²), Halle A und C frei.
    Die 94.000 m² sind mit Halle B erklärt – im Lese-Lauf entstand hier noch eine Aufgabe
    an 16 Einheiten."""
    park = _log_plaza(a_zu=False, b_zu=True)
    fake, _ = _ki([MatchResult(status=MatchStatus.AMBIGUOUS, units=park, kandidaten=park)])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL.model_copy(update={"groessen_hinweis": "94000"}), park)
    assert match.status == MatchStatus.NONE and schon_zu is True


@pytest.mark.parametrize("soll, flaechen, erwartet", [
    (19000, [3318.0], False),                      # Krefeld: aus einer kleinen Halle nicht zu bilden
    (20000, [11561.0, 11763.0], False),            # Rheinau: zwei Hallen zusammen 23.324 m² – 17 % zu viel
    (20300, [10066.0, 8295.0], True),              # Duisburg, Bliersheimer Straße: Unit 5 + Unit 6
    (94000, [f for _, f in _HALLE_B] + [11400.0, 11400.0], True),
    (5000, [], False),
    (None, [5000.0], False),
])
def test_teilmenge_passt(soll, flaechen, erwartet):
    units = [Unit(id=i, property_space_value=f) for i, f in enumerate(flaechen, 1)]
    assert match_ai._teilmenge_passt(soll, units) is erwartet


def test_flaeche_geht_erst_mit_der_offenen_einheit_auf(monkeypatch):
    """Zwei Hallen je 10.000 m², eine vermietet; gemeldet sind 20.000 m². Dann gehört die
    freie zur Vermietung."""
    zu = Unit(id=1, city="Rheinau", property_space_value=10000.0, rented=True, status_id=ABGESCHLOSSEN)
    frei = Unit(id=2, city="Rheinau", property_space_value=10000.0, status_id=VERMARKTUNG)
    fake, _ = _ki([MatchResult(status=MatchStatus.UNIQUE, units=[zu, frei], kandidaten=[zu, frei])])
    monkeypatch.setattr(match_ai, "select_match", fake)

    match, schon_zu = match_ai.select_open_match(DEAL.model_copy(update={"groessen_hinweis": "20000"}), [zu, frei])
    assert schon_zu is False and [u.id for u in match.units] == [2]


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
