"""Wochenreport-DM aus den Dashboard-Dokumenten (Propstack-Connector, ohne Keys)."""
import json
from datetime import datetime

import pytest

from weekly_report import report, wochen_dm

SINCE = datetime.fromisoformat("2026-11-03T19:03:00+01:00")
UNTIL = datetime.fromisoformat("2026-11-10T19:03:00+01:00")


def _dokumente(**extra):
    docs = {
        "meta/stand": {"fenster_von": "2026-08-12T06:17:00+02:00", "wochen": ["2026-KW45", "2026-KW46"]},
        "meta/projekte": {"projekte": {
            "100": {"titel": "Neues Projekt", "vorhanden": True, "erste_einheit": "2026-11-04T10:00:00+01:00"},
            "200": {"titel": "Altes Projekt", "vorhanden": True, "erste_einheit": "2026-09-01T10:00:00+02:00"},
            "300": {"titel": None, "vorhanden": False, "erste_einheit": "2026-11-05T10:00:00+01:00"},
        }},
        "wochen/2026-KW45": {"woche": "2026-KW45", "einheiten": [
            {"id": 1, "titel": "Halle A", "flaeche": 1200.5, "vermarktung": "RENT", "projekt_id": 100,
             "angelegt": "2026-11-04T10:00:00+01:00"},
            {"id": 2, "titel": "Halle B", "flaeche": 800, "vermarktung": "RENT", "projekt_id": 100,
             "angelegt": "2026-11-05T10:00:00+01:00"},
            {"id": 3, "titel": "Anbau", "flaeche": None, "vermarktung": "BUY", "projekt_id": 200,
             "angelegt": "2026-11-06T10:00:00+01:00"},
            {"id": 4, "titel": "Waise", "flaeche": 50, "vermarktung": None, "projekt_id": 300,
             "angelegt": "2026-11-05T10:00:00+01:00"},
            # Vor dem Fenster – gleiche Kalenderwoche, darf nicht zählen
            {"id": 5, "titel": "Zu früh", "flaeche": 10, "vermarktung": "RENT", "projekt_id": 200,
             "angelegt": "2026-11-03T19:02:59+01:00"},
        ]},
        "wochen/2026-KW46": {"woche": "2026-KW46", "einheiten": [
            # Genau am Fensterende – gehört schon zur nächsten Woche
            {"id": 6, "titel": "Zu spät", "flaeche": 10, "vermarktung": "RENT", "projekt_id": None,
             "angelegt": "2026-11-10T19:03:00+01:00"},
            {"id": 7, "titel": None, "flaeche": None, "vermarktung": None, "projekt_id": None,
             "angelegt": "2026-11-10T08:00:00+01:00"},
        ]},
        "pruefung/teil-01": {"teil": 1, "aufgaben": [
            {"id": 11, "titel": "Prüfung: Halle A", "art": "Prüfung", "erledigt": True,
             "angelegt": "2026-10-01T09:00:00+02:00", "geaendert": "2026-11-08T12:00:00+01:00", "bezug": "Halle A"},
            {"id": 12, "titel": "Prüfung: offen", "art": "Prüfung", "erledigt": False,
             "angelegt": "2026-11-04T09:00:00+01:00", "geaendert": "2026-11-08T12:00:00+01:00", "bezug": None},
            {"id": 13, "titel": "Prüfung: alt erledigt", "art": "Prüfung", "erledigt": True,
             "angelegt": "2026-09-01T09:00:00+02:00", "geaendert": "2026-10-20T12:00:00+02:00", "bezug": None},
            {"id": 14, "titel": "  ", "art": "Sonstige", "erledigt": True,
             "angelegt": None, "geaendert": "2026-11-09T12:00:00+01:00", "bezug": None},
        ]},
    }
    docs.update(extra)
    return docs


def test_fenster_und_klassifikation():
    daten = wochen_dm.baue_daten(_dokumente(), SINCE, UNTIL)
    assert [u.id for u in daten.neue_einheiten] == [7, 3, 2, 4, 1]  # neueste zuerst, 5 und 6 außerhalb
    assert [(a.project.id, a.neue_einheiten) for a in daten.neue_projekte] == [(100, 2), (300, 1)]
    assert [a.project.id for a in daten.bestehende_projekte] == [200]
    assert daten.neue_projekte[0].gesamtflaeche == 2000.5
    assert daten.neue_projekte[1].gefunden is False


def test_nur_im_fenster_abgeschlossene_pruefaufgaben():
    daten = wochen_dm.baue_daten(_dokumente(), SINCE, UNTIL)
    assert [t.id for t in daten.abgeschlossene_aufgaben] == [14, 11]
    assert daten.abgeschlossene_aufgaben[0].label() == "Aufgabe 14"


def test_daten_muessen_das_fenster_abdecken():
    docs = _dokumente()
    docs["meta/stand"]["fenster_von"] = "2026-11-05T00:00:00+01:00"
    with pytest.raises(ValueError, match="reichen nur bis"):
        wochen_dm.baue_daten(docs, SINCE, UNTIL)


def test_text_ist_standard_markdown():
    text = wochen_dm.baue_text(wochen_dm.baue_daten(_dokumente(), SINCE, UNTIL))
    assert text.startswith(":bar_chart: **Propstack-Wochenreport** · 03.11.–10.11.2026")
    assert "**Neue Projekte: 2**" in text
    assert "• **Neues Projekt** — 2 Einheiten, 2.000,5 m² · [öffnen](https://crm.propstack.de/app/portfolio/projects/100)" in text
    assert "• **Projekt 300** — 1 Einheit, 50 m² · _Projekt in Propstack nicht mehr vorhanden_" in text
    assert "• **Einheit 7** · [öffnen](https://crm.propstack.de/app/portfolio/properties/7)" in text
    assert "**Bestehende Projekte mit neuen Einheiten: 1**" in text
    assert "• **Prüfung: Halle A** — abgeschlossen 08.11., angelegt 01.10. · Halle A" in text
    assert "<http" not in text  # kein Slack-mrkdwn


def test_lange_nachricht_wird_auf_textelement_gekuerzt():
    viele = [
        {"id": 1000 + i, "titel": "Logistikhalle mit sehr langem Titel " * 3, "flaeche": 1000, "vermarktung": "RENT",
         "projekt_id": None, "angelegt": "2026-11-05T10:00:00+01:00"}
        for i in range(60)
    ]
    daten = wochen_dm.baue_daten(_dokumente(**{"wochen/2026-KW45": {"einheiten": viele}}), SINCE, UNTIL)
    text = wochen_dm.baue_text(daten)
    assert len(text) <= wochen_dm.MAX_ZEICHEN
    assert "**Neue Objekte/Einheiten: 61**" in text  # 60 + Einheit 7 aus KW46; Zahl bleibt vollständig
    assert "weitere" in text


def test_mrkdwn_bleibt_standard_fuer_build():
    daten = wochen_dm.baue_daten(_dokumente(), SINCE, UNTIL)
    text = report.build(daten)
    assert "*Neue Projekte: 2*" in text and "<https://crm.propstack.de/app/portfolio/projects/100|öffnen>" in text


def test_cli(tmp_path, monkeypatch, capsys):
    for name, body in _dokumente().items():
        p = tmp_path / "dash" / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(body), encoding="utf-8")
    out = tmp_path / "dm.md"
    monkeypatch.setattr("sys.argv", ["wochen_dm", "--daten", str(tmp_path / "dash"), "--out", str(out),
                                     "--bis", UNTIL.isoformat()])
    assert wochen_dm.main() == 0
    assert "2 neue Projekte, 5 neue Einheiten" in capsys.readouterr().out
    assert out.read_text(encoding="utf-8").startswith(":bar_chart:")
