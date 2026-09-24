"""Slack-Nachricht: Zahlenformat, Nullfälle, Kürzung langer Blöcke."""
from weekly_report import report
from weekly_report.models import NewUnit, ProjectActivity, ProjectInfo, PruefTask, ReportData

FENSTER = {"since": "2026-08-13T19:00:00+02:00", "until": "2026-08-20T19:00:00+02:00"}


def test_deutsche_zahlenformatierung():
    assert report._de_number(10197.0) == "10.197"
    assert report._de_number(12400.5) == "12.400,5"
    assert report._de_number(999.0) == "999"
    assert report._de_number(None) is None


def test_kopfzeile_zeigt_zeitraum():
    text = report.build(ReportData(**FENSTER))
    assert text.startswith(":bar_chart: *Propstack-Wochenreport* · 13.08.–20.08.2026")


def test_leere_bloecke_zeigen_sichtbare_null():
    """Eine sichtbare 0 ist die Information, dass nichts passiert ist."""
    text = report.build(ReportData(**FENSTER))
    assert "*Neue Projekte: 0*" in text
    assert "*Neue Objekte/Einheiten: 0*" in text
    assert "*Abgeschlossene Prüfaufgaben: 0*" in text
    assert "_Keine im Berichtszeitraum abgeschlossen._" in text


def test_einheiten_zeile_mit_flaeche_und_link():
    data = ReportData(
        **FENSTER,
        neue_einheiten=[NewUnit(
            id=5802066, title="Lagerhalle in (89) Giengen an der Brenz",
            property_space_value=10197.0, marketing_type="BUY",
        )],
    )
    text = report.build(data)
    assert "*Neue Objekte/Einheiten: 1*" in text
    assert "• *Lagerhalle in (89) Giengen an der Brenz* — 10.197 m², BUY" in text
    assert "<https://crm.propstack.de/app/portfolio/properties/5802066|öffnen>" in text


def test_projektzeile_mit_einheitenzahl_und_link():
    data = ReportData(
        **FENSTER,
        neue_projekte=[ProjectActivity(
            project=ProjectInfo(id=570215, title="Logistikflächen in (41) Kaarst"),
            neue_einheiten=3, gesamtflaeche=12400.5, ist_neu=True,
        )],
    )
    text = report.build(data)
    assert "• *Logistikflächen in (41) Kaarst* — 3 Einheiten, 12.400,5 m²" in text
    assert "<https://crm.propstack.de/app/portfolio/projects/570215|öffnen>" in text


def test_singular_bei_einer_einheit():
    data = ReportData(
        **FENSTER,
        neue_projekte=[ProjectActivity(
            project=ProjectInfo(id=1, title="Solo"), neue_einheiten=1, ist_neu=True,
        )],
    )
    assert "— 1 Einheit ·" in report.build(data)


def test_aufgabenzeile_nennt_abschluss_und_anlage():
    data = ReportData(
        **FENSTER,
        abgeschlossene_aufgaben=[PruefTask(
            id=447177220, title="Flächenupdate abgleichen: Panattoni", done=True,
            original_created_at="2026-07-21T07:22:53+02:00",
            updated_at="2026-08-17T14:52:15+02:00",
            property_names=["Panattoni Park Friedewald"],
        )],
    )
    text = report.build(data)
    assert "*Abgeschlossene Prüfaufgaben: 1*" in text
    assert "• *Flächenupdate abgleichen: Panattoni* — abgeschlossen 17.08., angelegt 21.07." in text
    assert "· Panattoni Park Friedewald" in text


def test_lange_liste_wird_gekuerzt():
    data = ReportData(
        **FENSTER,
        neue_einheiten=[NewUnit(id=i, title=f"Halle {i}") for i in range(1, 32)],
    )
    text = report.build(data)
    assert "*Neue Objekte/Einheiten: 31*" in text
    assert "… und 21 weitere" in text
    assert text.count("• *Halle") == 10


def test_bestehende_projekte_nur_wenn_vorhanden():
    ohne = report.build(ReportData(**FENSTER))
    assert "Bestehende Projekte mit neuen Einheiten" not in ohne

    mit = report.build(ReportData(
        **FENSTER,
        bestehende_projekte=[ProjectActivity(
            project=ProjectInfo(id=554679, title="Halle in (44) Bochum"),
            neue_einheiten=1, ist_neu=False,
        )],
    ))
    assert "*Bestehende Projekte mit neuen Einheiten: 1*" in mit


def test_bearbeitet_block_nur_wenn_gefuellt():
    ohne = report.build(ReportData(**FENSTER))
    assert "Bearbeitet, aber offen" not in ohne

    mit = report.build(ReportData(
        **FENSTER,
        bearbeitete_aufgaben=[PruefTask(
            id=2, title="Logicor: Hallenhoehe fehlt",
            original_created_at="2026-08-10T10:00:00+02:00",
            updated_at="2026-08-13T10:24:00+02:00",
        )],
    ))
    assert "*Bearbeitet, aber offen: 1*" in mit
    assert "— bearbeitet 13.08., angelegt 10.08." in mit


def test_fussnote_erklaert_projekt_datierung():
    """Die Einschränkung muss in der Nachricht stehen, nicht nur im Code."""
    text = report.build(ReportData(**FENSTER))
    assert "früheste Einheit datiert" in text
    assert "ohne Einheit erscheinen daher nicht" in text


def test_einheit_ohne_flaeche_bleibt_lesbar():
    data = ReportData(**FENSTER, neue_einheiten=[NewUnit(id=7, title="Nur ein Titel")])
    assert "• *Nur ein Titel* · <" in report.build(data)


def test_label_fallback_ohne_titel():
    assert NewUnit(id=42).label() == "Einheit 42"
    assert NewUnit(id=42, address="Musterweg 1").label() == "Musterweg 1"


def test_geloeschtes_projekt_ohne_toten_link():
    """Ein 404-Projekt darf keinen Deep-Link bekommen – lieber benennen als ins Leere führen."""
    data = ReportData(
        **FENSTER,
        neue_projekte=[ProjectActivity(
            project=ProjectInfo(id=570742), neue_einheiten=2, gesamtflaeche=68.0,
            ist_neu=True, gefunden=False,
        )],
    )
    text = report.build(data)
    assert "• *Projekt 570742* — 2 Einheiten, 68 m²" in text
    assert "_Projekt in Propstack nicht mehr vorhanden_" in text
    assert "portfolio/projects/570742" not in text
