"""Telefonnummern im Kontakt-Import – dieselben Fälle wie im Propstack-Connector
(propstack-mcp/test/phone.test.ts), damit beide Wege gleich schreiben.

Befund Florian, 13.11.2026: „Wenn die +49 oder andere Ländervorwahlen eingegeben werden,
kommt trotzdem noch eine 0 danach. So können wir die nicht anwählen.“ 8 der 12 so
geschriebenen Nummern unter den 600 neuesten Kontakten kamen aus dem täglichen Import.
"""
import pytest

from src.phone import UNBEKANNT, country_calling_code, format_phone


@pytest.mark.parametrize("eingabe,erwartet", [
    # „(0)“ nach der Ländervorwahl – in allen Schreibweisen, die im Konto vorkommen
    ("+49 (0) 151 12345678", "+49 151 12345678"),
    ("+49 (0)162 1234567", "+49 162 1234567"),
    ("+49(0)2151 1234 5678", "+49 2151 1234 5678"),
    ("+49 (0) 761-12345678", "+49 761-12345678"),
    ("  +49 ( 0 ) 171 3920055 ", "+49 171 3920055"),
    ("+44 (0)20 7946 0958", "+44 20 7946 0958"),
    ("+31 (0)6 12345678", "+31 6 12345678"),
    ("+43 (0) 1 2345678", "+43 1 2345678"),
    ("+61 (0)2 9876 5432", "+61 2 9876 5432"),  # Land nicht in der Liste: die Klammer sagt es selbst
    # 0 ohne Klammern, wo nach der Ländervorwahl nie eine 0 folgt
    ("+49 0171 3920055", "+49 171 3920055"),
    ("+4901713920055", "+491713920055"),
    ("+49-0221-4710199", "+49-221-4710199"),
    ("+49 (0171) 3920055", "+49 (171) 3920055"),
    ("+41 044 123 45 67", "+41 44 123 45 67"),
    ("+420 0601 123 456", "+420 601 123 456"),
    # Italien u. a.: die 0 gehört zur Nummer, nur die Klammer fällt weg
    ("+39 06 1234567", "+39 06 1234567"),
    ("+39061234567", "+39061234567"),
    ("+39 (0)6 1234567", "+39 06 1234567"),
    ("+225 07 12 34 56 78", "+225 07 12 34 56 78"),
    # „00“ wird zu „+“
    ("0049 171 3920055", "+49 171 3920055"),
    ("0049 (0) 171 3920055", "+49 171 3920055"),
    ("0049 0221 4710199", "+49 221 4710199"),
    ("0031 6 12345678", "+31 6 12345678"),
    ("00 7 495 1234567", "+7 495 1234567"),
    # ohne Ländervorwahl und ohne Landesangabe: deutsch
    ("0171 3920055", "+49 171 3920055"),
    ("0221 4710199", "+49 221 4710199"),
    ("0221/4710-199", "+49 221/4710-199"),
    ("02214710199", "+49 2214710199"),
    ("(0221) 4710199", "+49 221 4710199"),
    ("(0 22 1) 47 10 199", "+49 22 1 47 10 199"),
    (" 0171 3920055 ", "+49 171 3920055"),
])
def test_format_phone(eingabe, erwartet):
    assert format_phone(eingabe) == erwartet


@pytest.mark.parametrize("nummer", [
    "+49 171 3920055", "+49 221 4710-198", "+1 212 555 0100", "+49 30 12345678",
    "+7 0495 1234567", "+70495 1234567",
])
def test_richtig_geschriebene_nummern_bleiben(nummer):
    assert format_phone(nummer) == nummer


@pytest.mark.parametrize("land", ["Deutschland", "deutschland", "DE", "Germany", " DEU "])
def test_deutschland_in_allen_schreibweisen(land):
    assert format_phone("0171 3920055", land) == "+49 171 3920055"


@pytest.mark.parametrize("nummer,land,erwartet", [
    ("0664 1234567", "Österreich", "+43 664 1234567"),
    ("044 123 45 67", "Schweiz", "+41 44 123 45 67"),
    ("06 12345678", "Niederlande", "+31 6 12345678"),
    ("020 7946 0958", "UK", "+44 20 7946 0958"),
    ("06 1234567", "Italien", "+39 06 1234567"),      # in Italien bleibt die 0
    ("(06) 1234567", "Italien", "+39 06 1234567"),
    # unbekanntes Land: lieber unverändert als eine falsche Vorwahl
    ("0495 1234567", "Russland", "0495 1234567"),
    ("021 1234567", "Südafrika", "021 1234567"),
])
def test_land_bestimmt_die_vorwahl(nummer, land, erwartet):
    assert format_phone(nummer, land) == erwartet


def test_country_calling_code():
    assert country_calling_code("Russland") is UNBEKANNT
    assert country_calling_code("") is None
    assert country_calling_code(None) is None
    assert country_calling_code("Österreich") == "43"


@pytest.mark.parametrize("text", ["171 3920055", "Zentrale", "-22", "", "0", "00"])
def test_was_keine_nummer_ist_bleibt(text):
    assert format_phone(text) == text


def test_none_bleibt_none():
    assert format_phone(None) is None
