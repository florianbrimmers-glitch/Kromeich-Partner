from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from objekte_handler import config
from objekte_handler.decision import decide, due_date_plus_business_days
from objekte_handler.models import (
    AktionsTyp,
    Classification,
    MatchResult,
    MatchStatus,
    MessageType,
    Tier,
    Unit,
)

BERLIN = ZoneInfo("Europe/Berlin")
UNIT = Unit(id=1, street="Hamburgring", house_number="48", city="Mönchengladbach")
UNIQUE = MatchResult(status=MatchStatus.UNIQUE, units=[UNIT], kandidaten=[UNIT])
AMBIGUOUS = MatchResult(status=MatchStatus.AMBIGUOUS, grund="5 Treffer")
NONE_MATCH = MatchResult(status=MatchStatus.NONE, grund="Keine Treffer")


def _cls(**kwargs) -> Classification:
    defaults = {
        "typ": MessageType.STATUS_ANWEISUNG,
        "aktion": AktionsTyp.VERMIETET,
        "confidence": 0.95,
    }
    defaults.update(kwargs)
    return Classification(**defaults)


@pytest.fixture
def live_mode(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")


@pytest.fixture
def dry_run_mode(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")


def test_ignorieren(live_mode):
    assert decide(_cls(typ=MessageType.IGNORIEREN, aktion=None), None).tier == Tier.NONE


def test_fehlt_in_ps_immer_stufe_b(live_mode):
    decision = decide(_cls(typ=MessageType.FEHLT_IN_PS, aktion=None), None)
    assert decision.tier == Tier.B
    assert str(config.BROKER_REVIEW_FALLBACK) in decision.geplante_aktionen[0]


def test_fehlt_in_ps_nennt_aktuellen_fallback_namen(live_mode):
    """Die Aktion landet über main.py im Propstack-Aufgabentext und in der
    Slack-Antwort – dort darf kein veralteter Name stehen.

    Der Sitz 254958 lief früher auf Oguzhan Sahin und ist auf Lena Klinnert umgestellt.
    Name und ID standen in verschiedenen Dateien und liefen deshalb auseinander; dieser
    Test hält sie beim nächsten Sitzwechsel zusammen."""
    aktion = decide(_cls(typ=MessageType.FEHLT_IN_PS, aktion=None), None).geplante_aktionen[0]
    assert config.BROKER_REVIEW_FALLBACK_NAME in aktion
    assert "Oguzhan" not in aktion


def test_flaechenupdate_immer_stufe_b(live_mode):
    assert decide(_cls(typ=MessageType.FLAECHENUPDATE, aktion=None), UNIQUE).tier == Tier.B


def test_vermietet_eindeutig_stufe_a(live_mode):
    decision = decide(_cls(), UNIQUE)
    assert decision.tier == Tier.A
    assert any("rented=true" in a for a in decision.geplante_aktionen)


def test_dry_run_zwingt_auf_stufe_b(dry_run_mode):
    decision = decide(_cls(), UNIQUE)
    assert decision.tier == Tier.B
    assert "DRY_RUN" in decision.grund


def test_update_aktion_stufe_b(live_mode):
    assert decide(_cls(aktion=AktionsTyp.UPDATE), UNIQUE).tier == Tier.B


def test_ambiguous_match_stufe_b(live_mode):
    assert decide(_cls(), AMBIGUOUS).tier == Tier.B


def test_kein_match_stufe_b(live_mode):
    assert decide(_cls(), NONE_MATCH).tier == Tier.B


def test_niedrige_confidence_stufe_b(live_mode):
    assert decide(_cls(confidence=0.5), UNIQUE).tier == Tier.B


def test_unklassifizierbar_stufe_b(live_mode):
    assert decide(None, None).tier == Tier.B


@pytest.mark.parametrize(
    ("start", "expected_date"),
    [
        # Mittwoch 08.07.2026 -> Freitag 10.07.
        (datetime(2026, 7, 8, 14, 0, tzinfo=BERLIN), "2026-07-10"),
        # Freitag 10.07.2026 -> Dienstag 14.07.
        (datetime(2026, 7, 10, 9, 0, tzinfo=BERLIN), "2026-07-14"),
        # Samstag 11.07.2026 -> Dienstag 14.07.
        (datetime(2026, 7, 11, 9, 0, tzinfo=BERLIN), "2026-07-14"),
    ],
)
def test_due_date_plus_business_days(start, expected_date):
    due = due_date_plus_business_days(2, now=start)
    assert due.startswith(f"{expected_date}T10:00:00")
    assert "+02:00" in due  # Europe/Berlin Sommerzeit
