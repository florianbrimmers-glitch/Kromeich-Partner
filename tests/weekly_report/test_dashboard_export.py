"""Datenexport fürs Dashboard: Wochen-Bucketing, Projekt-Datierung, Größenschutz."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from weekly_report.dashboard_export import MAX_DOKUMENT_BYTES, baue_dokumente, wochen_schluessel
from weekly_report.models import NewUnit, PruefTask

BERLIN = ZoneInfo("Europe/Berlin")
SINCE = datetime(2026, 7, 1, 6, 0, tzinfo=BERLIN)
UNTIL = datetime(2026, 10, 1, 6, 0, tzinfo=BERLIN)


def _bauen(einheiten, titel=None, beginn=None, aufgaben=()):
    return baue_dokumente(
        einheiten, titel or {}, beginn or {}, list(aufgaben),
        since=SINCE, until=UNTIL, tage=92, broker_ids=[254958],
    )


def test_iso_woche_als_dokument_id():
    assert wochen_schluessel(datetime(2026, 9, 28, tzinfo=BERLIN)) == "2026-KW40"
    assert wochen_schluessel(datetime(2026, 9, 27, 23, 59, tzinfo=BERLIN)) == "2026-KW39"
    # Jahreswechsel: 1.1.2027 ist ein Freitag und gehört noch zu 2026-KW53.
    assert wochen_schluessel(datetime(2027, 1, 1, tzinfo=BERLIN)) == "2026-KW53"


def test_einheiten_landen_in_ihrer_woche():
    docs = _bauen([
        NewUnit(id=1, title="A", created_at="2026-09-28T10:00:00+02:00", project_id=7),
        NewUnit(id=2, title="B", created_at="2026-09-21T10:00:00+02:00"),
    ])
    assert [e["id"] for e in docs["wochen/2026-KW40"]["einheiten"]] == [1]
    assert [e["id"] for e in docs["wochen/2026-KW39"]["einheiten"]] == [2]
    assert docs["meta/stand"]["wochen"] == ["2026-KW39", "2026-KW40"]


def test_nur_abgeschlossene_aufgaben_nach_abschlusswoche():
    docs = _bauen([], aufgaben=[
        PruefTask(id=10, title="Pruefung X", done=True,
                  original_created_at="2026-07-30T08:00:00+02:00",
                  updated_at="2026-09-23T09:00:00+02:00", property_names=["Unit 1.1"]),
        PruefTask(id=11, title="Offen", done=None, updated_at="2026-09-23T09:00:00+02:00"),
    ])
    aufgaben = docs["wochen/2026-KW39"]["aufgaben"]
    assert [a["id"] for a in aufgaben] == [10]
    assert aufgaben[0]["bezug"] == "Unit 1.1"
    assert docs["meta/stand"]["anzahl_aufgaben"] == 1


def test_projekte_mit_beginn_und_geloeschtem_projekt():
    docs = _bauen(
        [NewUnit(id=1, created_at="2026-09-28T10:00:00+02:00", project_id=7),
         NewUnit(id=2, created_at="2026-09-28T11:00:00+02:00", project_id=8)],
        titel={7: "Logistikhalle in (40) Düsseldorf"},
        beginn={7: "2026-09-28T10:00:00+02:00", 8: None},
    )
    projekte = docs["meta/projekte"]["projekte"]
    assert projekte["7"] == {"titel": "Logistikhalle in (40) Düsseldorf", "vorhanden": True,
                             "erste_einheit": "2026-09-28T10:00:00+02:00"}
    # 404-Projekt: Einheit zeigt noch darauf, es hat aber keinen Titel mehr.
    assert projekte["8"]["vorhanden"] is False


def test_leeres_fenster_erzeugt_nur_meta():
    docs = _bauen([])
    assert set(docs) == {"meta/stand", "meta/projekte"}
    assert docs["meta/stand"]["wochen"] == []


def test_realistische_spitzenwoche_bleibt_unter_der_dokumentgrenze():
    """KW31/32 2026 hatten je ~255 Einheiten (Massen-Anlage). Mit langen Titeln
    muss eine solche Woche sicher unter 256 KiB bleiben."""
    einheiten = [
        NewUnit(id=6_000_000 + i, title="Logistikhalle in (71) Kornwestheim – Bauteil C – Halle 12 Süd",
                property_space_value=12345.5, marketing_type="RENT", city="Kornwestheim",
                project_id=590_000 + i % 40, created_at="2026-08-04T10:00:00+02:00")
        for i in range(600)
    ]
    groesse = len(json.dumps(_bauen(einheiten)["wochen/2026-KW32"], ensure_ascii=False).encode())
    assert groesse < MAX_DOKUMENT_BYTES, groesse


def test_woche_wird_in_berliner_zeit_bestimmt():
    """Sonntag 22:30 UTC ist Montag 00:30 Berlin – gehört schon zur neuen Woche.
    Muss mit keyVon() im Dashboard übereinstimmen (dort per Intl in Europe/Berlin)."""
    from datetime import timezone
    assert wochen_schluessel(datetime(2026, 9, 27, 22, 30, tzinfo=timezone.utc)) == "2026-KW40"
