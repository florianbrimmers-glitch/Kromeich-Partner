from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from newsletter_handler.decision import decide, due_date_plus_business_days
from newsletter_handler.models import (
    Deal,
    DealTyp,
    MatchResult,
    MatchStatus,
    Tier,
    Unit,
)

BERLIN = ZoneInfo("Europe/Berlin")
UNIT = Unit(id=1, street="Wieckesweg", house_number="12", city="Dortmund", property_space_value=6000.0)
UNIQUE = MatchResult(status=MatchStatus.UNIQUE, units=[UNIT], kandidaten=[UNIT])
AMBIGUOUS = MatchResult(status=MatchStatus.AMBIGUOUS, grund="2 Kandidaten")
NONE_MATCH = MatchResult(status=MatchStatus.NONE, grund="Keine Treffer")


def _vermietung(**kwargs) -> Deal:
    defaults = {"deal_typ": DealTyp.VERMIETUNG, "ist_vermietung": True, "confidence": 0.95}
    defaults.update(kwargs)
    return Deal(**defaults)


@pytest.fixture
def live_mode(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")


@pytest.fixture
def dry_run_mode(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")


def test_transaktion_ignoriert(live_mode):
    deal = _vermietung(deal_typ=DealTyp.TRANSAKTION, ist_vermietung=False)
    assert decide(deal, None).tier == Tier.NONE


def test_neubau_ignoriert(live_mode):
    deal = _vermietung(deal_typ=DealTyp.NEUBAU, ist_vermietung=False)
    assert decide(deal, None).tier == Tier.NONE


def test_vermietung_ohne_match_ignoriert(live_mode):
    """Fremd-Deal ohne eigenen Bestand: nur Log, kein Review-Task."""
    assert decide(_vermietung(), NONE_MATCH).tier == Tier.NONE


def test_vermietung_ambiguous_stufe_b(live_mode):
    assert decide(_vermietung(), AMBIGUOUS).tier == Tier.B


def test_vermietung_low_confidence_stufe_b(live_mode):
    assert decide(_vermietung(confidence=0.5), UNIQUE).tier == Tier.B


def test_vermietung_unique_live_stufe_a(live_mode):
    decision = decide(_vermietung(), UNIQUE)
    assert decision.tier == Tier.A
    assert any("rented=true" in a for a in decision.geplante_aktionen)


def test_vermietung_unique_dry_run_stufe_b(dry_run_mode):
    decision = decide(_vermietung(), UNIQUE)
    assert decision.tier == Tier.B
    # vorbereitete Aktionen bleiben im Log sichtbar
    assert any("rented=true" in a for a in decision.geplante_aktionen)


def test_deal_none_stufe_b(live_mode):
    assert decide(None, None).tier == Tier.B


@pytest.mark.parametrize("weekday_iso,expected_weekday", [
    ("2026-07-06", 2),  # Montag + 2 Werktage -> Mittwoch
    ("2026-07-09", 0),  # Donnerstag + 2 Werktage -> Montag (Sa/So übersprungen)
    ("2026-07-10", 1),  # Freitag + 2 Werktage -> Dienstag
])
def test_due_date_ueberspringt_wochenende(weekday_iso, expected_weekday):
    now = datetime.fromisoformat(f"{weekday_iso}T09:00:00").replace(tzinfo=BERLIN)
    due = datetime.fromisoformat(due_date_plus_business_days(2, now=now))
    assert due.weekday() == expected_weekday
    assert due.hour == 10
