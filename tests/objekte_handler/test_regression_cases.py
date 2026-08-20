"""Die 5 Regressions-Testfälle aus dem Briefing (08.07.2026) – als gestubbte
Classification-Objekte (erwartete Claude-Ausgabe) durch Matcher + Decision.
KEINE echten API-Calls: die Fälle wurden am 08.07. bereits manuell ausgeführt."""
import pytest

from objekte_handler import matcher
from objekte_handler.decision import decide
from objekte_handler.matcher import find_unit
from objekte_handler.models import (
    AktionsTyp,
    Classification,
    MatchStatus,
    MessageType,
    Tier,
)

from .fixtures import HAMBURGRING_UNITS, VIERSEN_UNITS


@pytest.fixture
def live_mode(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")


def test_fall_1_hamburgring_48(monkeypatch, live_mode):
    """"Hamburgring 48, Mönchengladbach ist vermietet – Objekt inaktiv, Deals absagen"
    -> Units 5263216 + 5263218 rented=true (Stufe A)"""
    monkeypatch.setattr(matcher, "search_units", lambda q: HAMBURGRING_UNITS)
    cls = Classification(
        typ=MessageType.STATUS_ANWEISUNG,
        aktion=AktionsTyp.VERMIETET,
        strasse="Hamburgring",
        hausnummer="48",
        stadt="Mönchengladbach",
        confidence=0.95,
    )
    match = find_unit(cls)
    assert match.status == MatchStatus.UNIQUE
    assert {u.id for u in match.units} == {5263216, 5263218}

    decision = decide(cls, match)
    assert decision.tier == Tier.A
    assert sum("rented=true" in a for a in decision.geplante_aktionen) == 2


def test_fall_2_viersen_kleine_einheit(monkeypatch, live_mode):
    """"Viersen Aconlog – die kleine Einheit ist vermietet"
    -> nur die kleinere Unit 5050165 (7.666 m² vs. 9.024 m²), Stufe A"""
    monkeypatch.setattr(matcher, "search_units", lambda q: VIERSEN_UNITS)
    cls = Classification(
        typ=MessageType.STATUS_ANWEISUNG,
        aktion=AktionsTyp.VERMIETET,
        objekt_name="Viersen Aconlog",
        groessen_hinweis="kleinste",
        confidence=0.9,
    )
    match = find_unit(cls)
    assert match.status == MatchStatus.UNIQUE
    assert [u.id for u in match.units] == [5050165]

    decision = decide(cls, match)
    assert decision.tier == Tier.A
    # Unit 2 bleibt unangetastet
    assert not any("5050166" in a for a in decision.geplante_aktionen)


def test_fall_3_landau_fehlt_in_ps(live_mode):
    """"Das Objekt Landau von Nvelop fehlt in Propstack" -> Aufgabe an den
    Review-Fallback (Sitz 254958, heute Lena Klinnert)"""
    cls = Classification(
        typ=MessageType.FEHLT_IN_PS,
        objekt_name="Landau von Nvelop",
        confidence=0.9,
    )
    decision = decide(cls, None)
    assert decision.tier == Tier.B
    assert "254958" in decision.geplante_aktionen[0]


def test_fall_4_prodac_castrop_update(monkeypatch, live_mode):
    """"Update prodac Castrop – bitte Bilder ablegen und PS aktualisieren"
    -> Stufe B (Bilder kann die API nicht ablegen), auch bei eindeutigem Match"""
    from objekte_handler.models import Unit

    prodac = [Unit(id=6000001, name="prodac Castrop", street="Industriestraße",
                   house_number="1", city="Castrop-Rauxel")]
    monkeypatch.setattr(matcher, "search_units", lambda q: prodac)
    cls = Classification(
        typ=MessageType.STATUS_ANWEISUNG,
        aktion=AktionsTyp.UPDATE,
        objekt_name="prodac Castrop",
        confidence=0.9,
    )
    match = find_unit(cls)
    decision = decide(cls, match)
    assert decision.tier == Tier.B


def test_fall_5_linkedin_link(live_mode):
    """LinkedIn-Link von Denise -> ignorieren, keine Aktion"""
    cls = Classification(typ=MessageType.IGNORIEREN, confidence=0.95)
    decision = decide(cls, None)
    assert decision.tier == Tier.NONE
    assert decision.geplante_aktionen == []
