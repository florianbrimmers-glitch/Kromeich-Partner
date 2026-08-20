"""Projekt-Klassifikation: neu vs. bestehend.

Propstack liefert für Projekte keinen Zeitstempel (verifiziert für GET /v1/projects und
GET /v1/projects/:id). Ein Projekt gilt deshalb als neu, wenn seine früheste Einheit
ebenfalls im Berichtsfenster liegt."""
from datetime import datetime
from zoneinfo import ZoneInfo

from weekly_report.main import klassifiziere_projekte, teile_aufgaben
from weekly_report.models import NewUnit, ProjectInfo, PruefTask

BERLIN = ZoneInfo("Europe/Berlin")
SINCE = datetime(2026, 8, 13, 19, 0, tzinfo=BERLIN)

PROJEKTE = {
    570215: ProjectInfo(id=570215, title="Logistikflächen in (41) Kaarst"),
    554679: ProjectInfo(id=554679, title="Halle in (44) Bochum"),
}


def _unit(uid: int, project_id: int | None, flaeche: float | None = None) -> NewUnit:
    return NewUnit(
        id=uid, title=f"Einheit {uid}", project_id=project_id,
        property_space_value=flaeche, created_at="2026-08-17T15:39:39+02:00",
    )


def test_projekt_mit_erster_einheit_im_fenster_ist_neu():
    neu, bestehend = klassifiziere_projekte(
        [_unit(1, 570215, 4200.0), _unit(2, 570215, 8200.5)],
        PROJEKTE,
        lambda pid: datetime(2026, 8, 17, 15, 39, tzinfo=BERLIN),
        SINCE,
    )
    assert [p.project.id for p in neu] == [570215]
    assert bestehend == []
    assert neu[0].neue_einheiten == 2
    assert neu[0].gesamtflaeche == 12400.5


def test_projekt_mit_aelterer_erster_einheit_ist_bestehend():
    neu, bestehend = klassifiziere_projekte(
        [_unit(3, 554679)],
        PROJEKTE,
        lambda pid: datetime(2026, 5, 2, 9, 0, tzinfo=BERLIN),
        SINCE,
    )
    assert neu == []
    assert [p.project.id for p in bestehend] == [554679]
    assert bestehend[0].neue_einheiten == 1


def test_einheit_ohne_projekt_erzeugt_keinen_projekt_eintrag():
    neu, bestehend = klassifiziere_projekte([_unit(4, None)], PROJEKTE, lambda pid: None, SINCE)
    assert neu == []
    assert bestehend == []


def test_unbekanntes_datum_wird_als_neu_gemeldet():
    """Lieber einmal zu viel melden als ein Projekt stillschweigend verschlucken."""
    neu, bestehend = klassifiziere_projekte([_unit(5, 570215)], PROJEKTE, lambda pid: None, SINCE)
    assert [p.project.id for p in neu] == [570215]
    assert bestehend == []


def test_unbekanntes_projekt_bekommt_platzhalter():
    neu, _ = klassifiziere_projekte([_unit(6, 999999)], {}, lambda pid: None, SINCE)
    assert neu[0].project.label() == "Projekt 999999"


def test_grenzfall_erste_einheit_genau_auf_since():
    """created_at == since gehört ins Fenster (Intervall ist [since, until))."""
    neu, bestehend = klassifiziere_projekte([_unit(7, 570215)], PROJEKTE, lambda pid: SINCE, SINCE)
    assert [p.project.id for p in neu] == [570215]
    assert bestehend == []


def test_projekte_nach_anzahl_neuer_einheiten_sortiert():
    neu, _ = klassifiziere_projekte(
        [_unit(8, 570215), _unit(9, 554679), _unit(10, 554679)],
        PROJEKTE,
        lambda pid: SINCE,
        SINCE,
    )
    assert [p.project.id for p in neu] == [554679, 570215]


def _task(tid: int, done, angelegt: str, geaendert: str) -> PruefTask:
    return PruefTask(id=tid, title=f"Aufgabe {tid}", done=done,
                     original_created_at=angelegt, updated_at=geaendert)


ABGESCHLOSSEN = _task(1, True, "2026-07-21T07:22:53+02:00", "2026-08-17T14:52:15+02:00")
BEARBEITET = _task(2, None, "2026-08-10T10:36:00+02:00", "2026-08-17T11:38:00+02:00")
UNBERUEHRT = _task(3, None, "2026-08-16T08:00:00+02:00", "2026-08-16T08:00:00+02:00")


def test_nur_abgeschlossene_wenn_schalter_aus(monkeypatch):
    monkeypatch.delenv("REPORT_INCLUDE_TOUCHED", raising=False)
    abgeschlossen, bearbeitet = teile_aufgaben([ABGESCHLOSSEN, BEARBEITET, UNBERUEHRT])
    assert [t.id for t in abgeschlossen] == [1]
    assert bearbeitet == []


def test_bearbeitete_nur_mit_schalter(monkeypatch):
    monkeypatch.setenv("REPORT_INCLUDE_TOUCHED", "true")
    abgeschlossen, bearbeitet = teile_aufgaben([ABGESCHLOSSEN, BEARBEITET, UNBERUEHRT])
    assert [t.id for t in abgeschlossen] == [1]
    # Aufgabe 3 wurde nach der Anlage nie angefasst und zählt nicht als bearbeitet.
    assert [t.id for t in bearbeitet] == [2]


def test_geloeschtes_projekt_wird_als_nicht_gefunden_markiert():
    """Einheiten können auf ein Projekt zeigen, das es nicht mehr gibt: GET /v1/projects
    listet es nicht, GET /v1/projects/:id antwortet 404 (verifiziert an 570742)."""
    neu, _ = klassifiziere_projekte([_unit(11, 570742)], PROJEKTE, lambda pid: None, SINCE)
    assert neu[0].gefunden is False
    assert neu[0].project.label() == "Projekt 570742"


def test_bekanntes_projekt_gilt_als_gefunden():
    neu, _ = klassifiziere_projekte([_unit(12, 570215)], PROJEKTE, lambda pid: SINCE, SINCE)
    assert neu[0].gefunden is True
