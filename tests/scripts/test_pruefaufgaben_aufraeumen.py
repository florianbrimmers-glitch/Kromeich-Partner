"""Auswahl der schließbaren Aufgaben in scripts/pruefaufgaben_aufraeumen.py (ohne Netz).

Die Zeilen sind so aufgebaut, wie GET /v1/activities und GET /v1/units?expand=1 sie am
19.11.2026 geliefert haben (gekürzt auf die genutzten Felder).
"""
import importlib.util
from pathlib import Path

_PFAD = Path(__file__).resolve().parents[2] / "scripts" / "pruefaufgaben_aufraeumen.py"
_spec = importlib.util.spec_from_file_location("pruefaufgaben_aufraeumen", _PFAD)
skript = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skript)

OFFEN = {"property_status": {"id": 163674, "name": "Vermarktung"}, "rented": {"label": "Vermietet", "value": False}, "archived": False}
ABGESCHLOSSEN = {"property_status": {"id": 163676, "name": "Abgeschlossen"}, "rented": {"label": "Vermietet", "value": False}, "archived": False}
VERMIETET = {"property_status": {"id": 163674, "name": "Vermarktung"}, "rented": {"label": "Vermietet", "value": True}, "archived": False}
OHNE_STATUS = {"property_status": None, "rented": {"label": "Vermietet", "value": False}, "archived": False}


def _aufgabe(task_id, titel, units, angelegt, done=None):
    return {"id": task_id + 1_000_000, "activatable_id": task_id, "title": titel, "done": done,
            "property_ids": units, "original_created_at": angelegt}


def _plan(aufgaben, einheiten):
    return {e["task_id"]: e for e in skript.plane(aufgaben, einheiten)}


def test_einheit_abgeschlossen():
    assert skript.einheit_abgeschlossen(ABGESCHLOSSEN)
    assert skript.einheit_abgeschlossen(VERMIETET)
    assert skript.einheit_abgeschlossen({**OFFEN, "archived": True})
    assert not skript.einheit_abgeschlossen(OFFEN)
    assert not skript.einheit_abgeschlossen(OHNE_STATUS)


def test_dublette_aelteste_bleibt_offen():
    aufgaben = [  # absteigend, wie die Schnittstelle liefert
        _aufgabe(3, "Newsletter-Vermietung prüfen: CTP", [5769426], "2026-10-28T10:27:31.732+01:00"),
        _aufgabe(2, "Newsletter-Vermietung prüfen: CTP", [5769426], "2026-10-06T11:54:19.470+02:00"),
        _aufgabe(1, "Newsletter-Vermietung prüfen: CTP", [5769426], "2026-09-30T10:00:00.000+02:00"),
    ]
    plan = _plan(aufgaben, {5769426: OFFEN})
    assert set(plan) == {2, 3}
    assert all(e["grund"] == skript.DUBLETTE and e["behalten"] == 1 for e in plan.values())


def test_gegenstandslos_auch_die_aelteste():
    """Ist die Einheit abgeschlossen, bleibt keine Aufgabe dazu offen – auch nicht die erste."""
    aufgaben = [
        _aufgabe(1, "Newsletter-Vermietung prüfen: Garbe Industrial", [5032898], "2026-10-16T09:59:46.949+02:00"),
        _aufgabe(2, "Newsletter-Vermietung prüfen: Garbe", [5032898], "2026-10-18T09:52:40.046+02:00"),
    ]
    plan = _plan(aufgaben, {5032898: ABGESCHLOSSEN})
    assert {t: e["grund"] for t, e in plan.items()} == {1: skript.GEGENSTANDSLOS, 2: skript.GEGENSTANDSLOS}


def test_mehrere_einheiten_nur_wenn_alle_zutreffen():
    aufgaben = [
        _aufgabe(1, "Newsletter-Vermietung prüfen: Park", [11], "2026-08-01T10:00:00.000+02:00"),
        _aufgabe(2, "Newsletter-Vermietung prüfen: Park", [11, 12], "2026-08-02T10:00:00.000+02:00"),  # 12 neu -> bleibt
        _aufgabe(3, "Newsletter-Vermietung prüfen: Park", [11, 12], "2026-08-03T10:00:00.000+02:00"),  # beide abgedeckt
        _aufgabe(4, "Newsletter-Vermietung prüfen: Halle", [21, 22], "2026-08-04T10:00:00.000+02:00"),  # nur 21 zu -> bleibt
    ]
    plan = _plan(aufgaben, {11: OFFEN, 12: OFFEN, 21: ABGESCHLOSSEN, 22: OFFEN})
    assert set(plan) == {3}
    assert plan[3]["grund"] == skript.DUBLETTE


def test_unangetastet_bleiben_andere_arten_erledigte_und_aufgaben_ohne_einheit():
    aufgaben = [
        _aufgabe(1, "Flächenupdate abgleichen: Panattoni", [11], "2026-08-01T10:00:00.000+02:00"),
        _aufgabe(2, "Flächenupdate abgleichen: Panattoni", [11], "2026-08-02T10:00:00.000+02:00"),
        _aufgabe(3, "Newsletter-Vermietung prüfen: erledigt", [11], "2026-08-03T10:00:00.000+02:00", done=True),
        _aufgabe(4, "Newsletter-Vermietung prüfen: ohne Objekt", [], "2026-08-04T10:00:00.000+02:00"),
        _aufgabe(5, "Newsletter-Vermietung prüfen: ohne Objekt", [], "2026-08-05T10:00:00.000+02:00"),
        _aufgabe(6, "Newsletter-Vermietung prüfen: erste offene", [11], "2026-08-06T10:00:00.000+02:00"),
    ]
    assert skript.plane(aufgaben, {11: OFFEN}) == []


def test_einheit_nicht_geladen_gilt_als_offen():
    aufgaben = [_aufgabe(1, "Newsletter-Vermietung prüfen: X", [99], "2026-08-01T10:00:00.000+02:00")]
    assert skript.plane(aufgaben, {}) == []
