import pytest

from personalkarussell_handler.decision import decide_message, decide_wechsel
from personalkarussell_handler.models import (
    Classification,
    Company,
    CompanyMatch,
    Link,
    MatchStatus,
    MessageType,
    Person,
    PersonMatch,
    Tier,
    Wechsel,
)

FELIX = Person(id=1, first_name="Felix", last_name="Lorenz", company="Aquila Capital")
CENTRALIS = Company(id=200, name="Centralis Immobilien Management GmbH")
PERSON_OK = PersonMatch(status=MatchStatus.UNIQUE, person=FELIX, kandidaten=[FELIX])
FIRMA_OK = CompanyMatch(status=MatchStatus.UNIQUE, company=CENTRALIS, kandidaten=[CENTRALIS])
LINKS = [Link(relationship_id=10, company_id=100, company_name="Aquila Capital")]
WECHSEL = Wechsel(vorname="Felix", nachname="Lorenz", alte_firma="Aquila", neue_firma="Centralis")


def _cls(**kwargs) -> Classification:
    defaults = {"typ": MessageType.WECHSEL, "wechsel": [WECHSEL], "confidence": 0.95}
    defaults.update(kwargs)
    return Classification(**defaults)


@pytest.fixture
def live_mode(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")


@pytest.fixture
def dry_run_mode(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")


def test_ignorieren():
    assert decide_message(_cls(typ=MessageType.IGNORIEREN, wechsel=[])).tier == Tier.NONE


def test_linkedin_und_umfirmierung_immer_review():
    assert decide_message(_cls(typ=MessageType.LINKEDIN, wechsel=[])).tier == Tier.B
    assert decide_message(_cls(typ=MessageType.UMFIRMIERUNG, wechsel=[])).tier == Tier.B


def test_wechsel_oder_abgang_ohne_person_review():
    assert decide_message(_cls(wechsel=[])).tier == Tier.B
    assert decide_message(_cls(typ=MessageType.ABGANG, wechsel=[])).tier == Tier.B


def test_wechsel_geht_in_die_einzelentscheidung():
    assert decide_message(_cls()) is None


def test_eindeutiger_wechsel_stufe_a(live_mode):
    d = decide_wechsel(_cls(), WECHSEL, PERSON_OK, FIRMA_OK, LINKS)
    assert d.tier == Tier.A
    assert any("Aquila Capital" in a for a in d.geplante_aktionen)  # alte Verknüpfung wird entfernt


def test_dry_run_macht_alles_zu_stufe_b(dry_run_mode):
    d = decide_wechsel(_cls(), WECHSEL, PERSON_OK, FIRMA_OK, LINKS)
    assert d.tier == Tier.B
    assert d.geplante_aktionen  # vorbereitete Aktion bleibt sichtbar


def test_abgang_ohne_ziel_review(live_mode):
    w = Wechsel(vorname="Marco", nachname="Vajas", alte_firma="CTXL")
    d = decide_wechsel(_cls(typ=MessageType.ABGANG, wechsel=[w]), w, PERSON_OK, None, LINKS)
    assert d.tier == Tier.B


def test_person_unbekannt_review(live_mode):
    d = decide_wechsel(_cls(), WECHSEL, PersonMatch(status=MatchStatus.NONE), FIRMA_OK, [])
    assert d.tier == Tier.B


def test_dublette_review(live_mode):
    m = PersonMatch(status=MatchStatus.AMBIGUOUS, kandidaten=[FELIX, FELIX], grund="2 Datensätze")
    assert decide_wechsel(_cls(), WECHSEL, m, FIRMA_OK, LINKS).tier == Tier.B


def test_zielfirma_fehlt_review(live_mode):
    d = decide_wechsel(_cls(), WECHSEL, PERSON_OK, CompanyMatch(status=MatchStatus.NONE), LINKS)
    assert d.tier == Tier.B
    assert "anlegen" in d.grund


def test_zielfirma_mehrdeutig_review(live_mode):
    m = CompanyMatch(status=MatchStatus.AMBIGUOUS, kandidaten=[CENTRALIS, CENTRALIS], grund="2 Firmen")
    assert decide_wechsel(_cls(), WECHSEL, PERSON_OK, m, LINKS).tier == Tier.B


def test_widerspruch_zur_alten_firma_review(live_mode):
    w = Wechsel(vorname="Felix", nachname="Lorenz", alte_firma="Goodman", neue_firma="Centralis")
    assert decide_wechsel(_cls(wechsel=[w]), w, PERSON_OK, FIRMA_OK, LINKS).tier == Tier.B


def test_niedrige_confidence_review(live_mode):
    assert decide_wechsel(_cls(confidence=0.6), WECHSEL, PERSON_OK, FIRMA_OK, LINKS).tier == Tier.B


def test_bereits_aktuell_ohne_aktion(live_mode):
    person = Person(id=1, first_name="Felix", last_name="Lorenz", company=CENTRALIS.name)
    m = PersonMatch(status=MatchStatus.UNIQUE, person=person, kandidaten=[person])
    links = [Link(relationship_id=11, company_id=200, company_name=CENTRALIS.name)]
    d = decide_wechsel(_cls(), WECHSEL, m, FIRMA_OK, links)
    assert d.tier == Tier.A
    assert d.bereits_aktuell
    assert not d.geplante_aktionen
