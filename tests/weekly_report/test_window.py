"""Zeitfenster und der Sommer-/Winterzeit-Guard.

Der Workflow feuert zweimal (17:03 und 18:03 UTC), weil GitHub-Actions-Cron nur UTC
kennt. Genau ein Lauf darf durchkommen – und zwar unabhängig davon, wie spät GitHub
ihn startet (in diesem Account 4–6 h)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from weekly_report.main import berechne_fenster, darf_laufen, geplanter_zeitpunkt

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


SOMMER_CRON = "3 17 * * 2"  # 19:03 Berlin während CEST
WINTER_CRON = "3 18 * * 2"  # 19:03 Berlin während CET


def _berlin(jahr, monat, tag, stunde, minute=0):
    return datetime(jahr, monat, tag, stunde, minute, tzinfo=BERLIN)


def test_sommer_nur_der_17_uhr_cron():
    jetzt = _berlin(2026, 9, 22, 19, 3)
    assert darf_laufen(SOMMER_CRON, jetzt, 19) is True
    assert darf_laufen(WINTER_CRON, jetzt, 19) is False


def test_winter_nur_der_18_uhr_cron():
    jetzt = _berlin(2026, 12, 15, 19, 3)
    assert darf_laufen(WINTER_CRON, jetzt, 19) is True
    assert darf_laufen(SOMMER_CRON, jetzt, 19) is False


def test_verspaeteter_start_wird_nicht_abgewiesen():
    """Regression: GitHub startet Crons in diesem Account 4–6 h zu spät (Objekte-Handler
    Soll 02:00, Ist 07:20–07:42 UTC). Der alte Guard verglich die Wanduhr mit 19 Uhr und
    hätte bei Start gegen Mitternacht BEIDE Trigger abgewiesen – kein Report, nie."""
    for verspaetung_h in (0, 1, 3, 5, 6, 8):
        start = _berlin(2026, 9, 22, 19, 3) + timedelta(hours=verspaetung_h)
        treffer = [c for c in (SOMMER_CRON, WINTER_CRON) if darf_laufen(c, start, 19)]
        assert treffer == [SOMMER_CRON], f"{verspaetung_h} h Verspätung: {treffer}"


def test_je_saison_genau_ein_trigger_auch_mit_verspaetung():
    """Keine Saison ohne Report, keine mit doppeltem – für jede realistische Verspätung."""
    for tag in (_berlin(2026, 8, 18, 19, 3), _berlin(2026, 12, 15, 19, 3)):
        for verspaetung_h in range(0, 9):
            start = tag + timedelta(hours=verspaetung_h)
            treffer = [c for c in (SOMMER_CRON, WINTER_CRON) if darf_laufen(c, start, 19)]
            assert len(treffer) == 1, f"{tag:%d.%m.} +{verspaetung_h} h: {treffer}"


def test_manueller_lauf_und_abgeschalteter_guard_laufen_immer():
    assert darf_laufen(None, _berlin(2026, 9, 24, 3), 19) is True
    assert darf_laufen(SOMMER_CRON, _berlin(2026, 12, 15, 3), None) is True


def test_fenster_endet_am_geplanten_zeitpunkt_nicht_am_start():
    """Start Mittwoch 00:40 (5,6 h zu spät) – das Fenster endet trotzdem Dienstag 19:03."""
    start = _berlin(2026, 9, 23, 0, 40)
    assert geplanter_zeitpunkt(start, SOMMER_CRON) == _berlin(2026, 9, 22, 19, 3)


def test_puenktlicher_start_endet_exakt_am_start():
    start = _berlin(2026, 9, 22, 19, 3)
    assert geplanter_zeitpunkt(start, SOMMER_CRON) == start


def test_winterzeit_anker():
    start = _berlin(2026, 12, 16, 0, 10)  # Mittwoch, 5 h nach 18:03 UTC
    assert geplanter_zeitpunkt(start, WINTER_CRON) == _berlin(2026, 12, 15, 19, 3)


def test_wochenfenster_schliessen_trotz_schwankender_verspaetung_aneinander():
    """Zwei Läufe mit 4 bzw. 6 h Verspätung: das zweite Fenster beginnt exakt, wo das
    erste endete – keine Lücke, keine Doppelzählung."""
    lauf1 = _berlin(2026, 9, 15, 23, 3)  # Di 15.09. +4 h
    lauf2 = _berlin(2026, 9, 23, 1, 3)   # Di 22.09. +6 h
    _, ende1 = berechne_fenster(geplanter_zeitpunkt(lauf1, SOMMER_CRON), 168)
    beginn2, _ = berechne_fenster(geplanter_zeitpunkt(lauf2, SOMMER_CRON), 168)
    assert ende1 == beginn2


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
