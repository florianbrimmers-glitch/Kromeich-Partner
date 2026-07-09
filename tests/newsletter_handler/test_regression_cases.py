"""End-to-end (extract-Stub -> match -> decide) für echte Radar-Ausschnitte.

KEINE echten API-Calls: search_units wird gestubbt, extract_deals wird umgangen,
indem die erwarteten Deal-Objekte direkt gebaut werden (die Extraktion selbst wird
in test_classifier_parsing separat abgesichert)."""
import pytest

from newsletter_handler import matcher
from newsletter_handler.decision import decide
from newsletter_handler.matcher import find_unit
from newsletter_handler.models import Deal, DealTyp, MatchStatus, Tier

from .fixtures import CITYLINK_UNITS


@pytest.fixture
def live_mode(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")


@pytest.fixture
def dry_run_mode(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")


def test_fremde_transaktion_wird_ignoriert(live_mode, monkeypatch):
    """"Realterm erwirbt 25.620 m² Logistikimmobilie bei Hamburg" -> Transaktion, ignorieren."""
    monkeypatch.setattr(matcher, "search_units", lambda q: [])
    deal = Deal(deal_typ=DealTyp.TRANSAKTION, ist_vermietung=False, stadt="Hamburg",
                objekt_name="Realterm", groessen_hinweis="25620", confidence=0.9)
    # Nicht-Vermietung -> gar kein Matching, direkt NONE
    assert decide(deal, None).tier == Tier.NONE


def test_fremde_vermietung_ohne_bestand_nur_log(live_mode, monkeypatch):
    """"TCC/CBRE vermieten 10.000 m² in Schönefeld an GVS" -> Vermietung, aber kein eigener Bestand."""
    monkeypatch.setattr(matcher, "search_units", lambda q: [])
    deal = Deal(deal_typ=DealTyp.VERMIETUNG, ist_vermietung=True, stadt="Schönefeld",
                objekt_name="TCC Schönefeld", groessen_hinweis="10000",
                mieter="GVS Group", vermieter="TCC / CBRE IM", confidence=0.9)
    match = find_unit(deal)
    assert match.status == MatchStatus.NONE
    assert decide(deal, match).tier == Tier.NONE


def test_eigene_vermietung_unique_live_setzt_rented(live_mode, monkeypatch):
    """"REALOGIS Anschlussvermietung CityLink ~6.000 m² LAMPAG" trifft eigenen Bestand -> Stufe A."""
    monkeypatch.setattr(matcher, "search_units", lambda q: CITYLINK_UNITS)
    deal = Deal(deal_typ=DealTyp.VERMIETUNG, ist_vermietung=True, stadt="Dortmund",
                objekt_name="CityLink Dortmund", groessen_hinweis="6000",
                mieter="LAMPAG GmbH", vermieter="REALOGIS", confidence=0.92)
    match = find_unit(deal)
    assert match.status == MatchStatus.UNIQUE
    decision = decide(deal, match)
    assert decision.tier == Tier.A
    assert sum("rented=true" in a for a in decision.geplante_aktionen) == 1


def test_eigene_vermietung_dry_run_nur_review(dry_run_mode, monkeypatch):
    monkeypatch.setattr(matcher, "search_units", lambda q: CITYLINK_UNITS)
    deal = Deal(deal_typ=DealTyp.VERMIETUNG, ist_vermietung=True, stadt="Dortmund",
                objekt_name="CityLink Dortmund", groessen_hinweis="6000", confidence=0.92)
    match = find_unit(deal)
    assert decide(deal, match).tier == Tier.B
