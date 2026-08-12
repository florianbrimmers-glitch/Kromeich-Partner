from comparables_handler import aggregate, normalize, slack_gateway
from comparables_handler.models import AngebotsOption, RunReport

from .fixtures import doc, mileway_bergkamen, westcore_bitterfeld


def _stats(plz="59192", mieten=(4.00, 4.58, 5.20)):
    angebot = mileway_bergkamen()
    angebot.plz = plz
    angebot.optionen = [
        AngebotsOption(laufzeit_monate=60 + 12 * i, kaltmiete_eur_qm=m, nebenkosten_eur_qm=2.15)
        for i, m in enumerate(mieten)
    ]
    return aggregate.aggregiere(normalize.zu_zeilen(doc(), angebot))


def test_deutsche_zahlformatierung():
    assert slack_gateway.eur(4.58) == "4,58"
    assert slack_gateway.eur(4.5, "€/m²") == "4,50 €/m²"
    assert slack_gateway.eur(None) == "–"


def test_nachricht_enthaelt_median_spanne_und_n():
    text = slack_gateway.baue_nachricht(_stats(), RunReport(dateien_eindeutig=22), "August 2026")
    assert "August 2026" in text
    assert "4,58 €/m²" in text
    assert "Spanne 4,00–5,20" in text
    assert "n=3" in text
    assert "59" in text


def test_nachricht_ohne_daten_warnt_statt_zu_luegen():
    report = RunReport(dateien_eindeutig=22, zeilen_ausgeschlossen=5)
    text = slack_gateway.baue_nachricht([], report, "August 2026")
    assert "Keine verwertbaren Mieten" in text
    assert "22" in text


def test_duenne_datenlage_wird_benannt():
    """Nur n=2 in der Leitregion -> Hinweis statt stiller Auslassung."""
    text = slack_gateway.baue_nachricht(
        _stats(mieten=(4.50, 4.60)), RunReport(dateien_eindeutig=22), "August 2026",
    )
    assert "Keine Leitregion erreicht" in text
    assert "Postleitzonen" in text


def test_fussnote_zaehlt_ausschluesse_und_dubletten():
    report = RunReport(
        dateien_eindeutig=22, zeilen_ausgeschlossen=4,
        versionen_uebersprungen=2, dateien_kopien_uebersprungen=48,
    )
    text = slack_gateway.baue_nachricht(_stats(), report, "August 2026")
    assert "Ausgeschlossen: 4" in text
    assert "ältere Versionen: 2" in text
    assert "Mehrfachablagen: 48" in text


def test_fehler_werden_im_post_sichtbar():
    report = RunReport(dateien_eindeutig=22, fehler=["a.pdf: Extraktion fehlgeschlagen"])
    text = slack_gateway.baue_nachricht(_stats(), report, "August 2026")
    assert "1 Fehler" in text


def test_keine_spanne_bei_einem_einzelwert():
    stats = aggregate.aggregiere(normalize.zu_zeilen(doc(), mileway_bergkamen()))
    text = slack_gateway.baue_nachricht(stats, RunReport(dateien_eindeutig=1), "August 2026")
    assert "Spanne" not in text.split("Postleitzonen")[1]


def test_objekt_und_zeilenzahl_werden_unterschieden():
    """Laufzeitstaffel: 1 Objekt, 3 Optionen – beides muss im Post stehen."""
    stats = aggregate.aggregiere(normalize.zu_zeilen(doc(), westcore_bitterfeld()))
    text = slack_gateway.baue_nachricht(stats, RunReport(dateien_eindeutig=22), "August 2026")
    assert "1 Objekt(e)" in text
    assert "3 Laufzeit-Option(en)" in text


def test_run_url_wird_angehaengt(monkeypatch):
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    text = slack_gateway.baue_nachricht(_stats(), RunReport(dateien_eindeutig=22), "August 2026")
    assert "https://github.com/org/repo/actions/runs/42" in text


def test_post_im_dry_run_unterbleibt(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    assert slack_gateway.poste("egal") is False
