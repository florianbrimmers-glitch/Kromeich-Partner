"""Auswertung eines Lese-Laufs gegen den Prüfsatz (ohne Netz)."""
import importlib.util
import json
from pathlib import Path

_PFAD = Path(__file__).resolve().parents[2] / "scripts" / "radar_zuordnung_messen.py"
_spec = importlib.util.spec_from_file_location("radar_zuordnung_messen", _PFAD)
skript = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skript)

URTEIL = {"aufgabe": 160024693, "digest_ts": "1794470000.000100", "objekt": "Ixocon", "mieter": "Logistikdienstleister",
          "vermieter": "Ixocon", "urteil": "erledigt", "ort": "Moers, Am Schürmannshütt 11",
          "gemeint": [2778068], "nicht_gemeint": [6319230], "offen": []}


def _zeile(**kw):
    basis = {"ts": "1794470000.000100", "idx": 0, "objekt": "Ixocon Moers", "mieter": "tsit", "vermieter": "Ixocon",
             "verlaengerung": False, "status": "none", "units": [], "anderer_eigentuemer": False,
             "bereits_abgeschlossen": False, "stufe": "none", "grund": ""}
    return {**basis, **kw}


def test_lies_lauf_nimmt_nur_auswertungszeilen():
    protokoll = "\n".join([
        "2026-11-20T23:01:02 [INFO] newsletter_handler.main: Deal 1#0: typ=vermietung",
        "2026-11-20T23:01:02 [INFO] newsletter_handler.main: AUSWERTUNG " + json.dumps(_zeile(), ensure_ascii=False),
        "2026-11-20T23:01:03 [INFO] newsletter_handler.main: AUSWERTUNG {kaputt",
    ])
    assert [z["objekt"] for z in skript.lies_lauf(protokoll)] == ["Ixocon Moers"]


def test_zuordnung_ueber_digest_und_namen():
    andere = _zeile(objekt="Panattoni Park", mieter="Maersk", vermieter="Panattoni")
    fremder_digest = _zeile(ts="1790000000.000100")
    passende = _zeile()
    paare = skript.ordne_zu([URTEIL], [andere, fremder_digest, passende])
    assert paare[0][1] is passende
    assert skript.ordne_zu([URTEIL], [andere])[0][1] is None   # kein gemeinsames Wort: nicht zuordnen


def test_ergebnis_in_worten():
    assert skript.ergebnis(URTEIL, None) == "im Lauf nicht wiedergefunden"
    assert skript.ergebnis(URTEIL, _zeile(bereits_abgeschlossen=True)) == "keine Aufgabe: Einheit geschlossen"
    assert skript.ergebnis(URTEIL, _zeile(anderer_eigentuemer=True)) == "keine Aufgabe: anderer Eigentümer"
    assert skript.ergebnis(URTEIL, _zeile(verlaengerung=True)) == "keine Aufgabe: Verlängerung"
    assert skript.ergebnis(URTEIL, _zeile()) == "keine Aufgabe: kein Treffer"
    assert skript.ergebnis(URTEIL, _zeile(stufe="B", units=[2778068])) == "Aufgabe an der gemeinten Einheit"
    assert skript.ergebnis(URTEIL, _zeile(stufe="B", units=[6319230])) == "Aufgabe an derselben falschen Einheit wie damals"
    assert skript.ergebnis(URTEIL, _zeile(stufe="B", units=[1])) == "Aufgabe an anderer Einheit"
    assert skript.ergebnis(URTEIL, _zeile(stufe="B")) == "Aufgabe ohne Einheit"


def test_pruefsatz_im_repo():
    daten = json.loads((_PFAD.parent / "radar_pruefsatz_2026-11-20.json").read_text(encoding="utf-8"))
    zeilen = daten["zeilen"]
    assert len(zeilen) == len({z["aufgabe"] for z in zeilen}) == 129
    assert all(z["digest_ts"].count(".") == 1 and len(z["digest_ts"]) == 17 for z in zeilen)
    assert all(z["gemeint"] for z in zeilen if z["urteil"] in ("erledigt", "eintragen"))
