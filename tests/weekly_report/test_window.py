"""Zeitfenster und der Sommer-/Winterzeit-Guard.

Der Workflow feuert zweimal (17:03 und 18:03 UTC), weil GitHub-Actions-Cron nur UTC
kennt. Genau ein Lauf darf durchkommen, damit der Report ganzjährig um 19 Uhr
Berliner Zeit ankommt."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from weekly_report.main import berechne_fenster, darf_laufen

BERLIN = ZoneInfo("Europe/Berlin")
UTC = ZoneInfo("UTC")


def test_fenster_ist_genau_sieben_tage():
    jetzt = datetime(2026, 8, 20, 19, 3, tzinfo=BERLIN)
    since, until = berechne_fenster(jetzt, 168)
    assert until == jetzt
    assert until - since == timedelta(days=7)
    assert since == datetime(2026, 8, 13, 19, 3, tzinfo=BERLIN)


def test_fenster_respektiert_report_hours():
    jetzt = datetime(2026, 8, 20, 19, 3, tzinfo=BERLIN)
    since, _ = berechne_fenster(jetzt, 2400)
    assert jetzt - since == timedelta(hours=2400)


def test_guard_laesst_sommerzeit_lauf_durch():
    """CEST: 17:03 UTC ist 19:03 Berlin -> laufen. 18:03 UTC ist 20:03 -> überspringen."""
    sommer_treffer = datetime(2026, 8, 20, 17, 3, tzinfo=UTC).astimezone(BERLIN)
    sommer_zweitschlag = datetime(2026, 8, 20, 18, 3, tzinfo=UTC).astimezone(BERLIN)
    assert sommer_treffer.hour == 19
    assert darf_laufen(sommer_treffer, 19) is True
    assert darf_laufen(sommer_zweitschlag, 19) is False


def test_guard_laesst_winterzeit_lauf_durch():
    """CET: 18:03 UTC ist 19:03 Berlin -> laufen. 17:03 UTC ist 18:03 -> überspringen."""
    winter_treffer = datetime(2026, 12, 15, 18, 3, tzinfo=UTC).astimezone(BERLIN)
    winter_frueh = datetime(2026, 12, 15, 17, 3, tzinfo=UTC).astimezone(BERLIN)
    assert winter_treffer.hour == 19
    assert darf_laufen(winter_treffer, 19) is True
    assert darf_laufen(winter_frueh, 19) is False


def test_guard_abschaltbar_fuer_lokale_laeufe():
    assert darf_laufen(datetime(2026, 8, 20, 3, 0, tzinfo=BERLIN), None) is True


def test_beide_crons_treffen_je_saison_genau_einmal():
    """Regressionsschutz: keine Saison ohne Report, keine Saison mit doppeltem Report."""
    for tag in (datetime(2026, 8, 20), datetime(2026, 12, 15)):
        treffer = [
            stunde
            for stunde in (17, 18)
            if darf_laufen(tag.replace(hour=stunde, minute=3, tzinfo=UTC).astimezone(BERLIN), 19)
        ]
        assert len(treffer) == 1, f"{tag:%Y-%m-%d}: {treffer}"


def test_leere_env_werte_fallen_auf_default_zurueck(monkeypatch):
    """GitHub Actions reicht nicht belegte workflow_dispatch-Inputs als "" durch –
    bei Cron-Läufen ist REPORT_RECIPIENT genau das. Regression zu einem Bug, der die
    DM an eine leere channel-ID geschickt hätte."""
    from weekly_report import config

    monkeypatch.setenv("REPORT_RECIPIENT", "")
    monkeypatch.setenv("REPORT_HOURS", "")
    monkeypatch.setenv("PRUEFER_BROKER_IDS", "")
    assert config.report_recipient() == config.REPORT_RECIPIENT
    assert config.report_hours() == 168
    assert config.pruefer_broker_ids() == [254958]


def test_env_werte_werden_beachtet_wenn_gesetzt(monkeypatch):
    from weekly_report import config

    monkeypatch.setenv("REPORT_RECIPIENT", "U0TEST")
    monkeypatch.setenv("REPORT_HOURS", "2400")
    monkeypatch.setenv("PRUEFER_BROKER_IDS", "254958, 387451")
    monkeypatch.setenv("RUN_HOUR_BERLIN", "")
    assert config.report_recipient() == "U0TEST"
    assert config.report_hours() == 2400
    assert config.pruefer_broker_ids() == [254958, 387451]
    assert config.run_hour_berlin() is None
