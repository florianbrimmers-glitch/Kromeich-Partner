"""Telefonnummern – dieselben Fälle wie im Connector (propstack-mcp/test/phone.test.ts).

Befund 13.11.2026: In Propstack standen Nummern wie "+49 (0) 151 …", so wie sie in
E-Mail-Signaturen stehen. Sie lassen sich nicht anwählen. 8 der 12 jüngsten Fälle
kamen aus dem täglichen Import."""
import pytest

from src import propstack_client as ps
from src.models import ContactData
from src.phone import format_phone, format_phone_for_contact, is_german_mobile_national


@pytest.mark.parametrize("roh, erwartet", [
    ("+49 (0) 151 12345678", "+49 151 12345678"),
    ("+49 (0)162 1234567", "+49 162 1234567"),
    ("+49(0)2151 1234 5678", "+49 2151 1234 5678"),
    ("+49 (0) 761-12345678", "+49 761-12345678"),
    ("  +49 ( 0 ) 171 3920055 ", "+49 171 3920055"),
    ("+44 (0)20 7946 0958", "+44 20 7946 0958"),
    ("+31 (0)6 12345678", "+31 6 12345678"),
    ("+43 (0) 1 2345678", "+43 1 2345678"),
    ("+61 (0)2 9876 5432", "+61 2 9876 5432"),
    # 0 ohne Klammern
    ("+49 0171 3920055", "+49 171 3920055"),
    ("+4901713920055", "+491713920055"),
    ("+49-0221-4710199", "+49-221-4710199"),
    ("+49 (0171) 3920055", "+49 (171) 3920055"),
    ("+41 044 123 45 67", "+41 44 123 45 67"),
    ("+420 0601 123 456", "+420 601 123 456"),
    # Italien & Co.: die 0 gehört zur Nummer
    ("+39 06 1234567", "+39 06 1234567"),
    ("+39061234567", "+39061234567"),
    ("+39 (0)6 1234567", "+39 06 1234567"),
    ("+225 07 12 34 56 78", "+225 07 12 34 56 78"),
    # schon richtig
    ("+49 171 3920055", "+49 171 3920055"),
    ("+49 221 4710-198", "+49 221 4710-198"),
    ("+1 212 555 0100", "+1 212 555 0100"),
    ("+7 0495 1234567", "+7 0495 1234567"),
    ("+70495 1234567", "+70495 1234567"),
    # 00 wird zu +
    ("0049 171 3920055", "+49 171 3920055"),
    ("0049 (0) 171 3920055", "+49 171 3920055"),
    ("0049 0221 4710199", "+49 221 4710199"),
    ("0031 6 12345678", "+31 6 12345678"),
    ("00 7 495 1234567", "+7 495 1234567"),
    # ohne Ländervorwahl, ohne Land: deutsch
    ("0171 3920055", "+49 171 3920055"),
    ("0221/4710-199", "+49 221/4710-199"),
    ("02214710199", "+49 2214710199"),
    ("(0221) 4710199", "+49 221 4710199"),
    ("(0 22 1) 47 10 199", "+49 22 1 47 10 199"),
    (" 0171 3920055 ", "+49 171 3920055"),
    # keine Nummer mit 0 oder +
    ("171 3920055", "171 3920055"), ("Zentrale", "Zentrale"), ("-22", "-22"), ("", ""), ("0", "0"), ("00", "00"),
])
def test_format_phone(roh, erwartet):
    assert format_phone(roh) == erwartet


@pytest.mark.parametrize("roh, land, erwartet", [
    ("0171 3920055", "Deutschland", "+49 171 3920055"),
    ("0171 3920055", " DEU ", "+49 171 3920055"),
    ("0664 1234567", "Österreich", "+43 664 1234567"),
    ("044 123 45 67", "Schweiz", "+41 44 123 45 67"),
    ("06 12345678", "Niederlande", "+31 6 12345678"),
    ("020 7946 0958", "UK", "+44 20 7946 0958"),
    ("06 1234567", "Italien", "+39 06 1234567"),
    ("(06) 1234567", "Italien", "+39 06 1234567"),
    # unbekanntes Land: lieber unverändert als eine falsche Vorwahl
    ("0495 1234567", "Russland", "0495 1234567"),
    ("021 1234567", "Südafrika", "021 1234567"),
])
def test_format_phone_with_country(roh, land, erwartet):
    assert format_phone(roh, land) == erwartet


def test_format_phone_none():
    assert format_phone(None) is None


class _Resp:
    status_code = 200

    def json(self):
        return {"id": 1}

    def raise_for_status(self):
        pass


def test_create_contact_writes_dialable_numbers(monkeypatch):
    monkeypatch.setenv("PROPSTACK_API_KEY", "v1")
    posts = []
    monkeypatch.setattr(ps.httpx, "post", lambda url, json=None, **kw: posts.append(json) or _Resp())
    monkeypatch.setattr(ps.httpx, "put", lambda url, **kw: _Resp())
    ps.create_contact(ContactData(email="a@b.de", first_name="A", last_name="B",
                                  phone="+49 (0) 221 4710199", mobile="0171 3920055"))
    client = posts[0]["client"]
    assert client["office_phone"] == "+49 221 4710199"
    assert client["office_cell"] == "+49 171 3920055"


def test_german_mobile_at_foreign_contact_is_not_guessed():
    # Kontakt in Österreich mit deutscher Handynummer: nicht +43 davorsetzen
    assert format_phone_for_contact("0171 3920057", "Österreich") == "0171 3920057"
    assert format_phone_for_contact("(0151) 12345678", "Schweiz") == "(0151) 12345678"
    # in Deutschland oder ohne Land: +49
    assert format_phone_for_contact("0171 3920057", "Deutschland") == "+49 171 3920057"
    assert format_phone_for_contact("0171 3920057") == "+49 171 3920057"
    # österreichisches Mobil / Festnetz im Ausland wird weiter umgestellt
    assert format_phone_for_contact("0664 1234567", "Österreich") == "+43 664 1234567"
    assert format_phone_for_contact("015 2123456", "Niederlande") == "+31 15 2123456"
    # mit Ländervorwahl ist nichts mehrdeutig
    assert format_phone_for_contact("+49 (0) 171 3920057", "Österreich") == "+49 171 3920057"


@pytest.mark.parametrize("text, erwartet", [
    ("0171 3920057", True), ("(0171) 3920057", True), ("0151 12345678", True), ("0176/12345678", True),
    ("+49 171 3920057", False), ("0049 171 3920057", False),
    ("015 2123456", False), ("01 71 39 20 05", False), ("0664 1234567", False), ("0221 4710199", False),
])
def test_is_german_mobile_national(text, erwartet):
    assert is_german_mobile_national(text) is erwartet
