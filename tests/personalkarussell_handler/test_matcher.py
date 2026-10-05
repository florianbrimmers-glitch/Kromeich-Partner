from personalkarussell_handler.matcher import (
    alte_firma_plausibel,
    eindeutig_ueber_verknuepfung,
    firmen_suchbegriff,
    alte_links,
    firma_passt,
    ist_bereits_aktuell,
    match_company,
    match_person,
    norm_name,
)
from personalkarussell_handler.models import Company, Link, MatchStatus, Person

from .fixtures import AURELIS, CENTRALIS, FELIX_LORENZ_ALT, MARQ, SWISS_LIFE, TIM_HAMACHER_DOPPELT


def test_norm_name_umlaute():
    assert norm_name("Fröhlich") == norm_name("Froehlich")
    assert norm_name("sarah berndt") == norm_name("Sarah Berndt")


def test_firma_passt_kurzname():
    assert firma_passt("arrow", "Arrow Capital Deutschland GmbH")
    assert firma_passt("Marq logistik", "Marq Logistics")
    assert firma_passt("citylink", "CityLink")


def test_firma_passt_keine_falschen_treffer():
    assert not firma_passt("Goodman", "Goodcang")
    assert not firma_passt("ID Logistics", "idealo GmbH")
    assert not firma_passt("Aquila", "Centralis Immobilien Management GmbH")


def test_match_person_eindeutig_trotz_aehnlichem_namen():
    m = match_person(FELIX_LORENZ_ALT, "Felix", "Lorenz")
    assert m.status == MatchStatus.UNIQUE
    assert m.person.id == 23052759


def test_match_person_dublette_ist_mehrdeutig():
    m = match_person(TIM_HAMACHER_DOPPELT, "Tim", "Hamacher")
    assert m.status == MatchStatus.AMBIGUOUS
    assert len(m.kandidaten) == 2


def test_match_person_umlaut_und_kleinschreibung():
    records = [{"id": 1, "first_name": "Jerome", "last_name": "Fröhlich"}]
    assert match_person(records, "jerome", "Froehlich").status == MatchStatus.UNIQUE


def test_match_person_ignoriert_firmen_datensaetze():
    records = [{"id": 2, "is_company": True, "name": "Hamacher GmbH", "last_name": "Hamacher"}]
    assert match_person(records, "Tim", "Hamacher").status == MatchStatus.NONE


def test_match_person_falsch_markierte_person_zaehlt():
    records = [{"id": 3, "is_company": True, "first_name": "Robin", "last_name": "Balsmeier"}]
    assert match_person(records, "Robin", "Balsmeier").status == MatchStatus.UNIQUE


def test_match_company_eindeutig():
    m = match_company(CENTRALIS, "Centralis")
    assert m.status == MatchStatus.UNIQUE
    assert m.company.id == 23052700  # die Person Felix Lorenz zählt nicht als Firma


def test_match_company_mehrdeutig_bei_zwei_gesellschaften():
    assert match_company(SWISS_LIFE, "Swiss life").status == MatchStatus.AMBIGUOUS
    assert match_company(AURELIS, "Aurelis").status == MatchStatus.AMBIGUOUS


def test_match_company_exakter_name_entscheidet():
    m = match_company(SWISS_LIFE, "Swiss Life Asset Managers Logistics GmbH")
    assert m.status == MatchStatus.UNIQUE
    assert m.company.id == 35208875


def test_match_company_falsch_markierte_person_ist_keine_firma():
    m = match_company(AURELIS, "Aurelis Real Estate Service")
    assert m.status == MatchStatus.UNIQUE
    assert m.company.id == 23378833


def test_match_company_rechtsform_egal():
    assert match_company(MARQ, "Marq Logistik GmbH").status == MatchStatus.UNIQUE


def test_match_company_nicht_vorhanden():
    assert match_company(MARQ, "Centralis").status == MatchStatus.NONE


PERSON = Person(id=1, first_name="Felix", last_name="Lorenz", company="Aquila Capital")
LINKS = [
    Link(relationship_id=10, company_id=100, company_name="Aquila Capital Investmentgesellschaft mbH"),
    Link(relationship_id=11, company_id=200, company_name="Centralis Immobilien Management GmbH"),
    Link(relationship_id=12, company_id=300, company_name="Log-IT Club e.V."),
]


def test_alte_links_nach_gemeldeter_alter_firma():
    assert [link.relationship_id for link in alte_links(LINKS, PERSON, "Aquila", 200)] == [10]


def test_alte_links_ohne_angabe_ueber_firmenfeld():
    assert [link.relationship_id for link in alte_links(LINKS, PERSON, None, 200)] == [10]


def test_alte_links_neue_firma_wird_nie_entfernt():
    person = Person(id=1, first_name="X", last_name="Y", company="Centralis")
    assert alte_links(LINKS, person, None, 200) == []


def test_bereits_aktuell():
    person = Person(id=1, first_name="Felix", last_name="Lorenz", company="Centralis Immobilien Management GmbH")
    ziel = Company(id=200, name="Centralis Immobilien Management GmbH")
    assert ist_bereits_aktuell(person, LINKS, ziel)
    assert not ist_bereits_aktuell(PERSON, LINKS, ziel)  # Feld steht noch auf Aquila


def test_alte_firma_plausibel():
    assert alte_firma_plausibel(PERSON, LINKS, "Aquila")
    assert alte_firma_plausibel(PERSON, LINKS, None)
    assert not alte_firma_plausibel(PERSON, LINKS, "Goodman")


def test_mehrdeutige_firma_ueber_bestehende_verknuepfung_aufgeloest():
    m = match_company(AURELIS, "Aurelis")
    links = [Link(relationship_id=1, company_id=17221995, company_name="Aurelis Real Estate GmbH")]
    aufgeloest = eindeutig_ueber_verknuepfung(m, links)
    assert aufgeloest.status == MatchStatus.UNIQUE
    assert aufgeloest.company.id == 17221995


def test_mehrdeutige_firma_bleibt_mehrdeutig_bei_zwei_verknuepfungen():
    m = match_company(SWISS_LIFE, "Swiss life")
    links = [Link(relationship_id=1, company_id=25289935, company_name="SL Deutschland"),
             Link(relationship_id=2, company_id=35208875, company_name="SL Logistics")]
    assert eindeutig_ueber_verknuepfung(m, links).status == MatchStatus.AMBIGUOUS


def test_mehrere_verknuepfungen_firmenfeld_entscheidet():
    m = match_company(SWISS_LIFE, "Swiss life")
    links = [Link(relationship_id=1, company_id=25289935, company_name="SL Deutschland"),
             Link(relationship_id=2, company_id=35208875, company_name="SL Logistics")]
    aufgeloest = eindeutig_ueber_verknuepfung(m, links, "Swiss Life Asset Managers Logistics GmbH")
    assert aufgeloest.status == MatchStatus.UNIQUE
    assert aufgeloest.company.id == 35208875


def test_suchbegriff_nur_markante_woerter():
    assert firmen_suchbegriff("Marq logistik") == "marq"
    assert firmen_suchbegriff("Swiss Life Asset Managers Logistics GmbH") == "swiss life asset managers"
    assert firmen_suchbegriff("GmbH") == "GmbH"  # nichts Markantes -> Original
