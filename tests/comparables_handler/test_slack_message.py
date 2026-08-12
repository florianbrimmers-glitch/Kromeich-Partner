from comparables_handler import aggregate, normalize, slack_gateway
from comparables_handler.models import AngebotsOption, RunReport

from .fixtures import doc, mileway_bergkamen, westcore_bitterfeld


def _zeilen(plz="59192", mieten=(4.00, 4.58, 5.20)):
    angebot = mileway_bergkamen()
    angebot.plz = plz
    angebot.optionen = [
        AngebotsOption(laufzeit_monate=60 + 12 * i, kaltmiete_eur_qm=m, nebenkosten_eur_qm=2.15)
        for i, m in enumerate(mieten)
    ]
    return normalize.zu_zeilen(doc(name=f"{plz}.pdf"), angebot)


def _stats(plz="59192", mieten=(4.00, 4.58, 5.20)):
    return aggregate.aggregiere(_zeilen(plz, mieten))


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


def test_duenne_region_erscheint_als_einzelwert():
    """Bekannte Mieten sind rar – n=2 wird NICHT unterdrückt, sondern als
    Einzelwert gezeigt (ohne Median-Anspruch)."""
    text = slack_gateway.baue_nachricht(
        _stats(mieten=(4.50, 4.60)), RunReport(dateien_eindeutig=22), "August 2026",
    )
    assert "Einzelwerte" in text
    assert "kein Median" in text             # n=2 trägt keinen Median
    assert "59 4,55" in text                 # der belegte Wert selbst
    assert "n=2" in text


def test_einzelner_wert_wird_ausgewiesen():
    """n=1: der eine belegte Wert ist die wertvolle Information."""
    text = slack_gateway.baue_nachricht(
        _stats(mieten=(4.58,)), RunReport(dateien_eindeutig=22), "August 2026",
    )
    assert "Einzelwerte" in text
    assert "4,58 €/m²" in text
    assert "n=1" in text


def test_belastbare_und_duenne_regionen_getrennt():
    stats = aggregate.aggregiere(
        _zeilen("59192", (4.50, 4.60, 4.70)) + _zeilen("06749", (5.00,))
    )
    text = slack_gateway.baue_nachricht(stats, RunReport(), "August 2026")
    assert "*59 Hamm" in text                 # n=3 -> eigene Median-Zeile
    assert "Einzelwerte" in text
    assert "06 5,00 (n=1)" in text            # n=1 -> kompakt als Einzelwert
    assert text.index("*59 Hamm") < text.index("Einzelwerte")


def test_absolute_zahl_steht_vorn():
    """Die Kernaussage ist die Anzahl belegter Mieten, nicht eine Quote."""
    text = slack_gateway.baue_nachricht(
        _stats(), RunReport(dateien_eindeutig=22), "August 2026",
    )
    assert "*3 bekannte Mieten*" in text
    assert "%" not in text          # keine Abdeckungsquote als Kernaussage


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


def test_keine_pseudospanne_bei_einem_einzelwert():
    """Bei n=1 wäre "Spanne 4,58-4,58" Etikettenschwindel."""
    stats = aggregate.aggregiere(normalize.zu_zeilen(doc(), mileway_bergkamen()))
    text = slack_gateway.baue_nachricht(stats, RunReport(dateien_eindeutig=1), "August 2026")
    assert "4,58–4,58" not in text
    assert "4,58 / 4,58" not in text


def test_standort_und_datenpunkte_werden_unterschieden():
    """Laufzeitstaffel: 1 Standort, 3 Datenpunkte – beides muss im Post stehen."""
    stats = aggregate.aggregiere(normalize.zu_zeilen(doc(), westcore_bitterfeld()))
    text = slack_gateway.baue_nachricht(stats, RunReport(dateien_eindeutig=22), "August 2026")
    assert "*3 bekannte Mieten*" in text
    assert "1 Standort(en)" in text


def test_run_url_wird_angehaengt(monkeypatch):
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    text = slack_gateway.baue_nachricht(_stats(), RunReport(dateien_eindeutig=22), "August 2026")
    assert "https://github.com/org/repo/actions/runs/42" in text


def test_post_im_dry_run_unterbleibt(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    assert slack_gateway.poste("egal") is False
