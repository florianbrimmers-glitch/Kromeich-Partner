"""Datenexport fürs Dashboard: Wochen-Bucketing, Projekt-Datierung, Größenschutz."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from weekly_report.dashboard_export import (
    AUFGABEN_PRO_TEIL, MAX_DOKUMENT_BYTES, aufgaben_art, baue_dokumente, wochen_schluessel,
)
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


def _task(tid, done, angelegt, geaendert, titel="Pruefung Panattoni Welle 3: Park Rheine"):
    return PruefTask(id=tid, title=titel, done=done, original_created_at=angelegt, updated_at=geaendert,
                     property_names=["Unit 1.1"])


def test_pruefung_offener_bestand_plus_fenster():
    """Offen zählt immer (Bestand, auch uralt); erledigt nur, wenn im Fenster angelegt
    oder erledigt – sonst wächst die Liste ohne Ende."""
    docs = _bauen([], aufgaben=[
        _task(1, None, "2026-03-29T09:00:00+02:00", "2026-03-29T09:00:00+02:00"),   # offen, alt
        _task(2, True, "2026-07-30T08:00:00+02:00", "2026-09-23T09:00:00+02:00"),   # erledigt im Fenster
        _task(3, True, "2026-03-01T08:00:00+01:00", "2026-03-30T10:00:00+02:00"),   # erledigt, alt
        _task(4, None, "2026-09-28T08:00:00+02:00", "2026-09-28T08:00:00+02:00"),   # neu, offen
    ])
    aufgaben = docs["pruefung/teil-01"]["aufgaben"]
    assert [a["id"] for a in aufgaben] == [1, 2, 4]
    assert [a["erledigt"] for a in aufgaben] == [False, True, False]
    assert aufgaben[1]["geaendert"] == "2026-09-23T09:00:00+02:00"
    assert aufgaben[0]["bezug"] == "Unit 1.1"
    stand = docs["meta/stand"]
    assert (stand["anzahl_offen"], stand["anzahl_aufgaben"]) == (2, 3)
    assert stand["pruefung_teile"] == ["teil-01"]


def test_wochen_enthalten_keine_aufgaben_mehr():
    """Prüfaufgaben stehen nur noch in pruefung/ – eine Quelle, nicht zwei."""
    docs = _bauen([NewUnit(id=1, created_at="2026-09-28T10:00:00+02:00")],
                  aufgaben=[_task(2, True, "2026-09-28T08:00:00+02:00", "2026-09-29T09:00:00+02:00")])
    assert set(docs["wochen/2026-KW40"]) == {"woche", "einheiten"}


def test_aufgaben_art_aus_titel():
    assert aufgaben_art("Pruefung Panattoni Welle 3: Park Rheine") == "Prüfung Panattoni Welle 3"
    assert aufgaben_art("Prüfung: Logistikfläche in (85) Kirchheim") == "Prüfung"
    assert aufgaben_art("Pruefung: Logistikhalle in (45) Waltrop") == "Prüfung"
    assert aufgaben_art("Newsletter-Vermietung prüfen: Bauer Property") == "Newsletter-Vermietung prüfen"
    assert aufgaben_art('Gesuch "FIRMA" "Kontakt" | "Größe"') == "Sonstige"
    assert aufgaben_art(None) == "Sonstige"


def test_pruefung_wird_in_teile_aufgeteilt():
    n = AUFGABEN_PRO_TEIL + 5
    docs = _bauen([], aufgaben=[_task(i, None, "2026-09-01T08:00:00+02:00", "2026-09-01T08:00:00+02:00")
                                for i in range(n)])
    assert len(docs["pruefung/teil-01"]["aufgaben"]) == AUFGABEN_PRO_TEIL
    assert len(docs["pruefung/teil-02"]["aufgaben"]) == 5
    assert docs["meta/stand"]["pruefung_teile"] == ["teil-01", "teil-02"]


def test_volles_pruefungs_teil_bleibt_unter_der_dokumentgrenze():
    lang = "Pruefung GARBE Welle 4 Nord: Logistikhalle in (21) Hamburg-Billbrook – Bauteil C – Halle 12"
    docs = _bauen([], aufgaben=[PruefTask(id=440_000_000 + i, title=lang, done=None,
                                          original_created_at="2026-09-01T08:00:00+02:00",
                                          updated_at="2026-09-01T08:00:00+02:00",
                                          property_names=["Logistikhalle Hamburg-Billbrook Halle 12"])
                                for i in range(AUFGABEN_PRO_TEIL)])
    groesse = len(json.dumps(docs["pruefung/teil-01"], ensure_ascii=False).encode())
    assert groesse < MAX_DOKUMENT_BYTES, groesse


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
    assert docs["meta/stand"]["pruefung_teile"] == []


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
