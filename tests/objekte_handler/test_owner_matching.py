"""Eigentümer-Achse – Fixtures aus den beiden am 31.07.2026 liegengebliebenen Aufgaben.

Aufgabe 142592761 "Flächenupdate abgleichen: Mileway" endete mit "23 Kandidaten,
keine eindeutige Zuordnung" und lag acht Tage unbearbeitet. Aufgabe 143382495
(Aconlog Viersen) matchte auf Unit 2778052 "Mackenstein 48" – eine leere Hülle
ohne Fläche, Status und Eigentümer. Beide Fälle sind hier als Test festgehalten.
"""
from __future__ import annotations

import pytest

from objekte_handler import matcher, owner
from objekte_handler.models import Classification, MatchStatus, MessageType, Unit
from objekte_handler.owner import normalize_company, owned_objects

# --- Kontakte, wie GET /contacts?q=Mileway sie am 31.07.2026 lieferte ----------
# 10 Treffer, darunter eine Fremdfirma: "Sarah Berndt (CityLink)" hat mit Mileway
# nichts zu tun und darf nicht ins Portfolio geraten.
MILEWAY_CONTACTS = [
    {"id": 17475856, "name": "Mileway Germany GmbH", "company": "Mileway Germany GmbH", "is_company": True},
    {"id": 31143946, "name": "Maria Meyenberg", "company": "Mileway Germany GmbH", "is_company": False},
    {"id": 22424465, "name": "Maria Drepper", "company": "Mileway Germany GmbH", "is_company": False},
    {"id": 25420917, "name": "Sarah Berndt (CityLink)", "company": "CityLink", "is_company": True},
]

ACONLOG_CONTACTS = [
    {"id": 17220059, "name": "Aconlog Projektentwicklung GmbH",
     "company": "Aconlog Projektentwicklung GmbH", "is_company": True},
    {"id": 16768585, "name": "André Büth-Stracke",
     "company": "Aconlog Projektentwicklung GmbH", "is_company": False},
]

# --- Die echten Aconlog-Einheiten am Industriering 21 -------------------------
ACONLOG_UNIT_1 = Unit(
    id=5050165, name="Logistikhallen in (41) Viersen", street="Industriering",
    house_number="21", zip_code="41751", city="Viersen", project_id=499759,
    hall_area=6729.0, property_space_value=7666.0, status_id=163674,
    status_name="Vermarktung", rented=True, free_from="Q2 2026", rs_type="INDUSTRY",
)
ACONLOG_UNIT_2 = Unit(
    id=5050187, name="Logistikhallen in (41) Viersen", street="Industriering",
    house_number="21", zip_code="41751", city="Viersen", project_id=499759,
    hall_area=9024.0, property_space_value=9024.0, status_id=163674,
    status_name="Vermarktung", rented=False, free_from="Sofort", rs_type="INDUSTRY",
)
# Der falsche Sieger des alten Matchings: gewann allein über den Ortsteilnamen.
MACKENSTEIN_HUELLE = Unit(
    id=2778052, name="Mackenstein 48  - Viersen", street="Mackenstein",
    zip_code="41751", city="Viersen", rs_type="APARTMENT", free_from="auf Anfrage",
)


def _cls(**kwargs) -> Classification:
    defaults = {"typ": MessageType.STATUS_ANWEISUNG, "confidence": 0.9}
    defaults.update(kwargs)
    return Classification(**defaults)


# ------------------------------------------------------------- normalize_company
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Mileway Germany GmbH", "mileway"),
        ("Aconlog Projektentwicklung GmbH", "aconlog"),
        ("Mileway", "mileway"),
        ("Panattoni Development Germany GmbH", "panattoni"),
        ("CityLink", "citylink"),
        # Fällt alles der Rauschliste zum Opfer, bleibt der Rohname erhalten -
        # sonst würde "Immobilien GmbH" zu einem leeren String und danach zum
        # Match auf alles.
        ("Immobilien GmbH", "immobilien gmbh"),
    ],
)
def test_normalize_company(raw, expected):
    assert normalize_company(raw) == expected


def test_find_owner_contacts_filtert_fremdfirma(monkeypatch):
    """q=Mileway liefert auch CityLink – die darf nicht ins Portfolio."""
    monkeypatch.setattr(owner, "search_contacts", lambda q: MILEWAY_CONTACTS)
    ids = {c["id"] for c in owner.find_owner_contacts("Mileway")}
    assert ids == {17475856, 31143946, 22424465}
    assert 25420917 not in ids


def test_find_owner_contacts_nimmt_personen_der_firma(monkeypatch):
    """Verknüpfungen hängen an Firma UND Person – wer nur Firmen nimmt, verliert
    Objekte (bei Aconlog war die Person Partner am selben Objekt)."""
    monkeypatch.setattr(owner, "search_contacts", lambda q: ACONLOG_CONTACTS)
    ids = {c["id"] for c in owner.find_owner_contacts("Aconlog")}
    assert ids == {17220059, 16768585}


# ------------------------------------------------------------------ owned_objects
def test_owned_objects_nur_rolle_owner(monkeypatch):
    """partner und associate sind keine Eigentümerschaft – sonst zieht man
    Fremdmandate ins Portfolio."""
    rels = [
        {"internal_name": "owner", "related_client_id": 17220059, "property_id": 5050165},
        {"internal_name": "owner", "related_client_id": 17220059, "project_id": 499759},
        {"internal_name": "partner", "related_client_id": 16768585, "property_id": 3688448},
        {"internal_name": "associate", "related_client_id": 17220059, "property_id": 9999999},
        {"internal_name": "owner", "related_client_id": 88888888, "property_id": 7777777},
    ]
    monkeypatch.setattr(owner, "all_relationships", lambda: rels)
    units, projects = owned_objects([17220059, 16768585])
    assert units == [5050165]
    assert projects == [499759]


def test_owned_objects_liest_auch_client_id(monkeypatch):
    """Geschrieben wird related_client_id, gelesen client_id – beide Formen
    kommen im Bestand vor."""
    rels = [{"internal_name": "owner", "client_id": 17475856, "property_id": 2777954}]
    monkeypatch.setattr(owner, "all_relationships", lambda: rels)
    units, _ = owned_objects([17475856])
    assert units == [2777954]


# ------------------------------------------------------------------- ist_huelle
def test_ist_huelle():
    assert MACKENSTEIN_HUELLE.ist_huelle() is True
    assert ACONLOG_UNIT_2.ist_huelle() is False


def test_kurzform_traegt_entscheidungsfelder():
    """Kandidatenlisten in Aufgaben zeigten nur Straße + Stadt + ID. Damit kann
    weder Mensch noch Modell einen leeren Datensatz erkennen."""
    zeile = ACONLOG_UNIT_2.kurzform()
    assert "Unit 5050187" in zeile
    assert "9.024 m² Halle" in zeile
    assert "Vermarktung" in zeile
    assert "nicht vermietet" in zeile


# ------------------------------------------------------- Flächenupdate Mileway
def test_flaechenupdate_liefert_portfolio(monkeypatch):
    """Der Mileway-Fall: 26 Einheiten sind der Treffer, nicht die Mehrdeutigkeit."""
    mileway_units = [
        Unit(id=uid, street="Teststraße", city="Teststadt", hall_area=1000.0,
             status_id=163674, status_name="Vermarktung")
        for uid in range(2777954, 2777954 + 26)
    ]
    monkeypatch.setattr(matcher, "resolve_owner",
                        lambda name: ([17475856], [u.id for u in mileway_units], [409116, 424355, 557014]))
    monkeypatch.setattr(matcher, "units_by_ids", lambda ids: mileway_units)

    result = matcher.find_unit(_cls(typ=MessageType.FLAECHENUPDATE, eigentuemer="Mileway"))

    assert result.status is MatchStatus.PORTFOLIO
    assert len(result.units) == 26
    assert result.achse == "eigentuemer"
    assert result.eigentuemer_project_ids == [409116, 424355, 557014]
    assert "26 Einheiten" in result.grund


# ------------------------------------------------------------ Einzelfall Aconlog
def test_eigentuemer_plus_flaeche_trifft_unit_2(monkeypatch):
    """"Vermieter Aconlog, ca. 9.150 m² vermietet" -> Unit 2 (9.024 m²).

    Die Hülle Mackenstein 48 ist im Eigentümerbestand gar nicht enthalten, weil
    sie keine Eigentümer-Verknüpfung hat – schon dadurch fällt der alte
    Fehltreffer weg."""
    units = [ACONLOG_UNIT_1, ACONLOG_UNIT_2]
    monkeypatch.setattr(matcher, "resolve_owner",
                        lambda name: ([17220059], [u.id for u in units], [499759]))
    monkeypatch.setattr(matcher, "units_by_ids", lambda ids: units)

    result = matcher.find_unit(_cls(eigentuemer="Aconlog", groessen_hinweis="9150"))

    assert result.status is MatchStatus.UNIQUE
    assert [u.id for u in result.units] == [5050187]
    assert result.achse == "eigentuemer+flaeche"


def test_huelle_wird_verworfen(monkeypatch):
    """Selbst wenn eine Hülle als Eigentümerobjekt verknüpft wäre: ein Datensatz
    ohne Fläche und ohne Status ist kein Ziel für ein Statusupdate."""
    units = [MACKENSTEIN_HUELLE, ACONLOG_UNIT_2]
    monkeypatch.setattr(matcher, "resolve_owner",
                        lambda name: ([17220059], [u.id for u in units], []))
    monkeypatch.setattr(matcher, "units_by_ids", lambda ids: units)

    result = matcher.find_unit(_cls(eigentuemer="Aconlog"))

    assert result.status is MatchStatus.UNIQUE
    assert [u.id for u in result.units] == [5050187]


def test_flaeche_ausserhalb_toleranz_bleibt_ambiguous(monkeypatch):
    """5.000 m² passt zu keiner der beiden Einheiten – dann lieber zurückstellen
    als die nächstliegende nehmen."""
    units = [ACONLOG_UNIT_1, ACONLOG_UNIT_2]
    monkeypatch.setattr(matcher, "resolve_owner",
                        lambda name: ([17220059], [u.id for u in units], []))
    monkeypatch.setattr(matcher, "units_by_ids", lambda ids: units)

    result = matcher.find_unit(_cls(eigentuemer="Aconlog", groessen_hinweis="5000"))

    # Gleiche Adresse, kein auflösbarer Flächentreffer -> ganzes Objekt
    assert result.status is MatchStatus.UNIQUE
    assert len(result.units) == 2


def test_pick_by_area_toleranz():
    assert matcher._pick_by_area([ACONLOG_UNIT_1, ACONLOG_UNIT_2], "9150").id == 5050187
    assert matcher._pick_by_area([ACONLOG_UNIT_1, ACONLOG_UNIT_2], "6700").id == 5050165
    # 8.000 liegt zu weit von beiden weg
    assert matcher._pick_by_area([ACONLOG_UNIT_1, ACONLOG_UNIT_2], "8000") is None
    # Zwei Einheiten in Toleranz -> nicht entscheidbar
    zwilling = ACONLOG_UNIT_2.model_copy(update={"id": 5050188})
    assert matcher._pick_by_area([ACONLOG_UNIT_2, zwilling], "9024") is None


# -------------------------------------------------------------------- Rückfall
def test_fallback_auf_adressachse(monkeypatch):
    """Eigentümer nicht auflösbar -> die Adress-Achse muss weiter greifen."""
    monkeypatch.setattr(matcher, "resolve_owner", lambda name: ([], [], []))
    monkeypatch.setattr(matcher, "search_units", lambda q: [ACONLOG_UNIT_2])

    result = matcher.find_unit(
        _cls(eigentuemer="Unbekannt GmbH", strasse="Industriering", hausnummer="21", stadt="Viersen")
    )

    assert result.status is MatchStatus.UNIQUE
    assert result.achse == "adresse"
    assert [u.id for u in result.units] == [5050187]
