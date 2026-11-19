"""Ablauf des täglichen Kontakt-Imports (src/main.py) und seiner Bausteine – ohne Netz.

Anlass ist das Produktionslog vom 19.11.2026 (Lauf grün, „Fehler: 0“):
- Apollo wies jeden der 11 Aufrufe mit 401 ab (Schlüssel im Body statt im Header).
- 18 von 19 erkannten Kontakten waren längst in Propstack – jeder lief vorher durch
  Extraktion, Apollo und Kategorisierung mit Websuche.
- Ein Postfach lieferte „Found 50 emails“ – die Obergrenze, der Rest fiel still weg.
- Zwei Antworten der KI ließen sich nicht lesen und zählten als „kein Kontakt“.
Dazu die Wochenlücke: Der Lauf kam Mo–Fr und las 24 h, der Freitag wurde nie gelesen.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from src import apollo_client, contact_extractor, gmail_client, main, problems, slack_client
from src.models import ContactData, ContactResult, ContactStatus, EmailData, EnrichmentResult, PipelineReport


@pytest.fixture(autouse=True)
def _sauber(monkeypatch):
    problems.leeren()
    monkeypatch.setattr(main, "DRY_RUN", False)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    yield
    problems.leeren()


def _mail(sender_email: str, name: str = "Max Muster", message_id: str = "m1") -> EmailData:
    return EmailData(message_id=message_id, sender=f"{name} <{sender_email}>", sender_email=sender_email,
                     subject="Anfrage", body="Text\n-- \nSignatur", date="")


class _Welt:
    """Ersetzt alles, was der Ablauf nach außen ruft, und merkt sich die Reihenfolge."""

    def __init__(self, monkeypatch, mails, *, in_propstack=(), kontakte=None, apollo=None, anlage=None):
        self.aufrufe: list[str] = []
        self.gesendet: list[PipelineReport] = []
        self.in_propstack = set(in_propstack)
        self.kontakte = kontakte or {}
        self.anlage = anlage
        self.verknuepft: list[tuple[int, int]] = []

        def check_duplicate(adresse):
            self.aufrufe.append(f"propstack?{adresse}")
            return None if adresse == "kaputt@x.de" else adresse in self.in_propstack

        def extract_contact(mail):
            self.aufrufe.append(f"ki:{mail.sender_email}")
            antwort = self.kontakte.get(mail.message_id, self.kontakte.get(mail.sender_email))
            if isinstance(antwort, Exception):
                raise antwort
            return antwort

        def enrich_contact(contact):
            self.aufrufe.append(f"apollo:{contact.email}")
            return apollo(contact) if apollo else None

        def categorize_contact(contact, subject, body):
            self.aufrufe.append(f"kategorie:{contact.email}")
            return ["c09cc4c2f4"]

        def create_contact(contact, group_ids=None):
            self.aufrufe.append(f"anlegen:{contact.email}")
            if self.anlage:
                return self.anlage(contact)
            self.in_propstack.add(contact.email)
            return {"id": 1000 + len(self.aufrufe)}

        monkeypatch.setattr(main, "search_recent_emails", lambda hours: list(mails))
        monkeypatch.setattr(main, "check_duplicate", check_duplicate)
        monkeypatch.setattr(main, "extract_contact", extract_contact)
        monkeypatch.setattr(main, "enrich_contact", enrich_contact)
        monkeypatch.setattr(main, "categorize_contact", categorize_contact)
        monkeypatch.setattr(main, "create_contact", create_contact)
        monkeypatch.setattr(main, "find_or_create_company", lambda contact: 77)
        monkeypatch.setattr(main, "link_contact_to_company", lambda p, c: self.verknuepft.append((p, c)) or True)
        monkeypatch.setattr(main, "send_summary", lambda report: self.gesendet.append(report))


def _kontakt(email, **kw):
    felder = {"first_name": "Max", "last_name": "Muster", "company": "Muster Logistik GmbH"}
    felder.update(kw)
    return ContactData(email=email, **felder)


# --- Reihenfolge: erst prüfen, dann die teuren Aufrufe ----------------------------

def test_bekannter_absender_kostet_keinen_ki_aufruf(monkeypatch):
    welt = _Welt(monkeypatch, [_mail("bekannt@firma.de")], in_propstack={"bekannt@firma.de"})
    report = main.run_pipeline()

    assert welt.aufrufe == ["propstack?bekannt@firma.de"]
    assert [r.email for r in report.contacts_skipped_duplicate] == ["bekannt@firma.de"]
    assert report.errors == []


def test_zwei_mails_desselben_bekannten_absenders_eine_pruefung(monkeypatch):
    mails = [_mail("bekannt@firma.de", message_id="m1"), _mail("bekannt@firma.de", message_id="m2")]
    welt = _Welt(monkeypatch, mails, in_propstack={"bekannt@firma.de"})
    report = main.run_pipeline()

    assert welt.aufrufe == ["propstack?bekannt@firma.de"]
    assert report.contacts_skipped_session_duplicate == 1


def test_neuer_kontakt_wird_angelegt_und_verknuepft(monkeypatch):
    welt = _Welt(monkeypatch, [_mail("neu@firma.de")], kontakte={"neu@firma.de": _kontakt("neu@firma.de")})
    report = main.run_pipeline()

    assert welt.aufrufe == [
        "propstack?neu@firma.de", "ki:neu@firma.de", "apollo:neu@firma.de",
        "kategorie:neu@firma.de", "anlegen:neu@firma.de",
    ]
    assert [r.email for r in report.contacts_created] == ["neu@firma.de"]
    assert len(welt.verknuepft) == 1 and welt.verknuepft[0][1] == 77
    assert report.errors == []


def test_signatur_nennt_andere_bekannte_adresse(monkeypatch):
    """Assistenz schreibt für die Chefin: Der Absender ist neu, die Adresse der Signatur bekannt."""
    welt = _Welt(monkeypatch, [_mail("assistenz@firma.de")], in_propstack={"chefin@firma.de"},
                 kontakte={"assistenz@firma.de": _kontakt("chefin@firma.de")})
    report = main.run_pipeline()

    assert welt.aufrufe == ["propstack?assistenz@firma.de", "ki:assistenz@firma.de", "propstack?chefin@firma.de"]
    assert [r.email for r in report.contacts_skipped_duplicate] == ["chefin@firma.de"]
    assert report.contacts_created == []


def test_dublettenpruefung_scheitert_dann_wird_nicht_angelegt(monkeypatch):
    welt = _Welt(monkeypatch, [_mail("kaputt@x.de")])
    report = main.run_pipeline()

    assert welt.aufrufe == ["propstack?kaputt@x.de"]
    assert len(report.errors) == 1 and "Duplikat-Prüfung" in report.errors[0].error


def test_anlage_scheitert_zweite_mail_versucht_es_erneut(monkeypatch):
    """Früher galt die Adresse schon vor der Anlage als verarbeitet – die zweite Mail fiel weg."""
    versuche = []

    def anlage(contact):
        versuche.append(contact.email)
        return None if len(versuche) == 1 else {"id": 5}

    mails = [_mail("neu@firma.de", message_id="m1"), _mail("neu@firma.de", message_id="m2")]
    kontakt = _kontakt("neu@firma.de")
    welt = _Welt(monkeypatch, mails, kontakte={"m1": kontakt, "m2": kontakt.model_copy()}, anlage=anlage)
    report = main.run_pipeline()

    assert versuche == ["neu@firma.de", "neu@firma.de"]
    assert len(report.contacts_created) == 1
    assert [e.error for e in report.errors] == ["Propstack create failed"]


# --- Fehler bleiben nicht im Log -------------------------------------------------

def test_claude_fehler_zaehlt_als_fehler_nicht_als_kein_kontakt(monkeypatch):
    fehler = RuntimeError("401 authentication_error")
    welt = _Welt(monkeypatch, [_mail("neu@firma.de")], kontakte={"neu@firma.de": fehler})
    report = main.run_pipeline()

    assert report.contacts_skipped_no_email == 0
    assert len(report.errors) == 1 and "401" in report.errors[0].error
    assert welt.gesendet == [report]  # Slack-Meldung auch ohne Neuanlage


def test_probleme_aus_den_bausteinen_landen_im_report(monkeypatch):
    def apollo(contact):
        problems.melde("Apollo-Anreicherung fehlgeschlagen", "HTTP 401")
        return None

    mails = [_mail("a@firma.de", message_id="m1"), _mail("b@firma.de", message_id="m2")]
    kontakte = {"m1": _kontakt("a@firma.de"), "m2": _kontakt("b@firma.de")}
    welt = _Welt(monkeypatch, mails, kontakte=kontakte, apollo=apollo)
    report = main.run_pipeline()

    assert len(report.contacts_created) == 2  # angelegt wird trotzdem
    assert [e.error for e in report.errors] == ["Apollo-Anreicherung fehlgeschlagen (2×): HTTP 401"]


def test_gmail_suche_scheitert_ganz(monkeypatch):
    welt = _Welt(monkeypatch, [])

    def kaputt(hours):
        raise RuntimeError("invalid_grant")

    monkeypatch.setattr(main, "search_recent_emails", kaputt)
    report = main.run_pipeline()
    assert any("Gmail-Suche fehlgeschlagen" in e.error for e in report.errors)


def test_fenster_ist_48_stunden(monkeypatch):
    monkeypatch.delenv("SCAN_HOURS", raising=False)
    assert main.scan_hours() == 48
    monkeypatch.setenv("SCAN_HOURS", "")  # nicht belegter workflow_dispatch-Input
    assert main.scan_hours() == 48
    monkeypatch.setenv("SCAN_HOURS", "168")
    assert main.scan_hours() == 168


# --- Gmail: blättern, Obergrenze melden, eine kaputte Mail kostet nicht das Postfach --

class _GmailService:
    def __init__(self, seiten, kaputt=()):
        self.seiten = seiten          # Liste von ID-Listen
        self.kaputt = set(kaputt)
        self.list_aufrufe: list[dict] = []

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, **kw):
        self.list_aufrufe.append(kw)
        index = int(kw.get("pageToken") or 0)
        seite = {"messages": [{"id": i} for i in self.seiten[index]]}
        if index + 1 < len(self.seiten):
            seite["nextPageToken"] = str(index + 1)
        return SimpleNamespace(execute=lambda: seite)

    def get(self, userId, id, format):
        def execute():
            if id in self.kaputt:
                raise RuntimeError("backendError")
            return {"payload": {"headers": [
                {"name": "From", "value": f"Kontakt {id} <{id}@extern.de>"},
                {"name": "Subject", "value": "Anfrage"},
            ], "body": {}}}
        return SimpleNamespace(execute=execute)


def test_gmail_blaettert_ueber_alle_seiten(monkeypatch):
    service = _GmailService([[f"a{i}" for i in range(100)], [f"b{i}" for i in range(20)]])
    monkeypatch.setattr(gmail_client, "_get_gmail_service", lambda *a: service)

    mails = gmail_client._fetch_emails_for_account("t", "id", "secret", "Postfach", hours=48)
    assert len(mails) == 120
    assert service.list_aufrufe[0]["q"] == "newer_than:2d -in:sent"
    assert problems.zusammenfassung() == []


def test_gmail_meldet_die_obergrenze(monkeypatch):
    service = _GmailService([[f"a{i}" for i in range(100)]] * 5)
    monkeypatch.setattr(gmail_client, "_get_gmail_service", lambda *a: service)

    mails = gmail_client._fetch_emails_for_account("t", "id", "secret", "Postfach", hours=48, limit=300)
    assert len(mails) == 300
    assert any("Obergrenze" in z for z in problems.zusammenfassung())


def test_gmail_eine_kaputte_mail_kostet_nicht_das_postfach(monkeypatch):
    service = _GmailService([["a1", "a2", "a3"]], kaputt={"a2"})
    monkeypatch.setattr(gmail_client, "_get_gmail_service", lambda *a: service)

    mails = gmail_client._fetch_emails_for_account("t", "id", "secret", "Postfach")
    assert [m.message_id for m in mails] == ["a1", "a3"]
    assert any("Mails nicht lesbar" in z for z in problems.zusammenfassung())


def test_postfach_mit_abgelaufenem_token_wird_gemeldet(monkeypatch):
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "t1")
    for nr in (2, 3, 4, 5):
        monkeypatch.delenv(f"GOOGLE_REFRESH_TOKEN_{nr}", raising=False)

    def kaputt(*a, **k):
        raise RuntimeError("invalid_grant: Token has been expired or revoked")

    monkeypatch.setattr(gmail_client, "_fetch_emails_for_account", kaputt)
    assert gmail_client.search_recent_emails() == []
    assert any("Postfach nicht lesbar" in z and "invalid_grant" in z for z in problems.zusammenfassung())


# --- Apollo -------------------------------------------------------------------------

class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload, self.status_code = payload, status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=self)


def test_apollo_schluessel_steht_im_header(monkeypatch):
    gesendet = {}

    def post(url, json=None, headers=None, **kw):
        gesendet.update(url=url, json=json, headers=headers)
        return _Resp({"person": None})

    monkeypatch.setenv("APOLLO_API_KEY", "geheim")
    monkeypatch.setattr(apollo_client.httpx, "post", post)
    assert apollo_client.enrich_contact(ContactData(email="a@b.de")) is None

    assert gesendet["url"] == "https://api.apollo.io/api/v1/people/match"
    assert gesendet["headers"]["x-api-key"] == "geheim"
    assert "api_key" not in gesendet["json"]


def test_apollo_401_wird_gemeldet(monkeypatch):
    monkeypatch.setenv("APOLLO_API_KEY", "geheim")
    monkeypatch.setattr(apollo_client.httpx, "post", lambda url, **kw: _Resp({}, status_code=401))
    assert apollo_client.enrich_contact(ContactData(email="a@b.de")) is None
    assert problems.zusammenfassung() == ["Apollo-Anreicherung fehlgeschlagen: HTTP 401"]


def _apollo_person():
    return {"person": {"title": "Head of Logistics", "organization": {
        "name": "Muster AG", "street_address": "Leopoldstraße 4", "city": "München", "postal_code": "80802"}}}


def test_apollo_adresse_wird_nicht_mit_der_signatur_gemischt(monkeypatch):
    """Signatur nennt nur „Hamburg“, Apollo den Hauptsitz: früher „Leopoldstraße 4, 80802 Hamburg“."""
    monkeypatch.setenv("APOLLO_API_KEY", "geheim")
    monkeypatch.setattr(apollo_client.httpx, "post", lambda url, **kw: _Resp(_apollo_person()))

    result = apollo_client.enrich_contact(ContactData(email="a@b.de", city="Hamburg"))
    assert result.enriched_fields == ["company", "position"]
    assert result.street is None and result.zip_code is None


def test_apollo_adresse_als_ganzes_wenn_die_signatur_keine_nennt(monkeypatch):
    monkeypatch.setenv("APOLLO_API_KEY", "geheim")
    monkeypatch.setattr(apollo_client.httpx, "post", lambda url, **kw: _Resp(_apollo_person()))

    result = apollo_client.enrich_contact(ContactData(email="a@b.de"))
    assert (result.street, result.house_number, result.zip_code, result.city) == ("Leopoldstraße", "4", "80802", "München")


# --- Antworten der KI lesen ---------------------------------------------------------

@pytest.mark.parametrize("antwort", [
    '{"first_name": "Max", "zip_code": "51373"}',
    'Hier ist das Ergebnis:\n{"first_name": "Max", "zip_code": "51373"}\nIch hoffe, das hilft.',
    '```json\n{"first_name": "Max", "zip_code": "51373"}\n```',
    '{"first_name": "Max",\n "zip_code": "51373"}',
])
def test_json_objekt_wird_aus_der_antwort_gelesen(antwort):
    assert contact_extractor._json_object(antwort) == {"first_name": "Max", "zip_code": "51373"}


def test_zeilenumbruch_in_einem_wert_macht_die_antwort_nicht_unlesbar():
    assert contact_extractor._json_object('{"reasoning": "Zeile 1\nZeile 2"}') == {"reasoning": "Zeile 1\nZeile 2"}


def test_antwort_ohne_json_ist_kein_kontakt_aber_kein_fehler():
    with pytest.raises(contact_extractor.KeinJson):
        contact_extractor._json_object("Diese E-Mail enthält keine Signatur.")


def test_zahl_statt_text_verwirft_den_kontakt_nicht():
    assert contact_extractor._text_or_none(51373) == "51373"
    assert contact_extractor._text_or_none(" 12a ") == "12a"
    assert contact_extractor._text_or_none("") is None
    assert contact_extractor._text_or_none(None) is None


def _antwort(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def _client(antwort=None, fehler=None, gesendet=None):
    def create(**kw):
        if gesendet is not None:
            gesendet.append(kw)
        if fehler:
            raise fehler
        return antwort
    return SimpleNamespace(messages=SimpleNamespace(create=create))


def test_extraktion_mit_vorgeplaenkel_und_zahl(monkeypatch):
    text = 'Gerne:\n{"first_name": "Max", "last_name": "Muster", "email": "Max@Firma.de", "zip_code": 51373, "house_number": 12}'
    monkeypatch.setattr(contact_extractor, "_get_client", lambda: _client(_antwort(text)))
    contact = contact_extractor.extract_contact(_mail("max@firma.de"))
    assert (contact.email, contact.zip_code, contact.house_number) == ("max@firma.de", "51373", "12")


def test_extraktion_ohne_json_ist_kein_kontakt(monkeypatch):
    monkeypatch.setattr(contact_extractor, "_get_client", lambda: _client(_antwort("Keine Signatur vorhanden.")))
    assert contact_extractor.extract_contact(_mail("max@firma.de")) is None
    assert problems.zusammenfassung() == []


def test_extraktion_reicht_api_fehler_durch(monkeypatch):
    fehler = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    monkeypatch.setattr(contact_extractor, "_get_client", lambda: _client(fehler=fehler))
    with pytest.raises(anthropic.APIError):
        contact_extractor.extract_contact(_mail("max@firma.de"))


def test_kategorie_textbloecke_werden_ohne_trenner_zusammengesetzt():
    """Mit Websuche teilt die API den Text an Zitatgrenzen; die Grenze kann in einem Wert liegen."""
    bloecke = ['Recherche abgeschlossen. {"categories": ["Logistiker"], "reasoning": "Die Firma ', "betreibt Lager", ' in Köln."}']
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text=b) for b in bloecke])
    data = contact_extractor._json_object(contact_extractor._extract_json_from_blocks(response))
    assert data == {"categories": ["Logistiker"], "reasoning": "Die Firma betreibt Lager in Köln."}


def test_visitenkarte_png_geht_als_png_an_die_api(monkeypatch):
    gesendet = []
    text = '{"first_name": "Max", "last_name": "Muster"}'
    monkeypatch.setattr(contact_extractor, "_get_client", lambda: _client(_antwort(text), gesendet=gesendet))
    contact = contact_extractor.extract_contact_from_image(b"\x89PNG", "image/png")
    assert contact.last_name == "Muster"
    assert gesendet[0]["messages"][0]["content"][0]["source"]["media_type"] == "image/png"


def test_visitenkarte_in_fremdem_format_wird_gemeldet(monkeypatch):
    monkeypatch.setattr(contact_extractor, "_get_client", lambda: pytest.fail("kein API-Aufruf erwartet"))
    assert contact_extractor.extract_contact_from_image(b"....", "image/heic") is None
    assert any("image/heic" in z for z in problems.zusammenfassung())


# --- Slack-Zusammenfassung -----------------------------------------------------------

def _slack(monkeypatch):
    gesendet = []
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setattr(slack_client.httpx, "post", lambda url, json=None, **kw: gesendet.append(json) or _Resp({"ok": True}))
    return gesendet


def test_slack_meldet_probleme_auch_ohne_neuanlage(monkeypatch):
    gesendet = _slack(monkeypatch)
    report = PipelineReport(errors=[ContactResult(email="Lauf", status=ContactStatus.ERROR,
                                                  error="Apollo-Anreicherung fehlgeschlagen (11×): HTTP 401")])
    slack_client.send_summary(report)

    text = gesendet[0]["text"]
    assert "Keine neuen Kontakte angelegt." in text
    assert "1 Problem(e)" in text and "Apollo-Anreicherung fehlgeschlagen (11×): HTTP 401" in text
    # Der Visitenkarten-Import erkennt die eigene Zusammenfassung an diesen zwei Wörtern
    assert "KI-Scan" in text and "Neue Kontakte" in text


def test_slack_schweigt_wenn_nichts_war(monkeypatch):
    gesendet = _slack(monkeypatch)
    slack_client.send_summary(PipelineReport())
    assert gesendet == []


def test_slack_nennt_die_quelle(monkeypatch):
    gesendet = _slack(monkeypatch)
    report = PipelineReport(contacts_created=[ContactResult(email="a@b.de", name="Max Muster", status=ContactStatus.CREATED)])
    slack_client.send_summary(report, quelle="Visitenkarte")
    assert "via Visitenkarte" in gesendet[0]["text"]
    assert json.dumps(gesendet[0]["text"]).count("Problem") == 0


# --- Visitenkarten-Import (src/slack_import.py) ---------------------------------------

def _karten_welt(monkeypatch, nachrichten, bilder, kontakte, in_propstack=()):
    from src import slack_import

    aufrufe: list[str] = []
    monkeypatch.setattr(slack_import, "DRY_RUN", False)
    monkeypatch.setattr(slack_import.time, "sleep", lambda s: None)
    monkeypatch.setattr(slack_import, "fetch_recent_messages", lambda hours, latest_hours=0: list(nachrichten))
    monkeypatch.setattr(slack_import, "has_images", lambda msg: True)
    monkeypatch.setattr(slack_import, "get_message_images", lambda msg: list(bilder))

    def extract(image_data, media_type):
        aufrufe.append(f"ki:{media_type}")
        antwort = kontakte[image_data]
        if isinstance(antwort, Exception):
            raise antwort
        return antwort

    monkeypatch.setattr(slack_import, "extract_contact_from_image", extract)
    monkeypatch.setattr(slack_import, "check_duplicate", lambda email: aufrufe.append(f"propstack?{email}") or email in in_propstack)
    monkeypatch.setattr(slack_import, "enrich_contact", lambda c: aufrufe.append(f"apollo:{c.email}") or None)
    monkeypatch.setattr(slack_import, "categorize_contact", lambda c, s, b: aufrufe.append(f"kategorie:{c.email}") or ["c09cc4c2f4"])
    monkeypatch.setattr(slack_import, "create_contact", lambda c, g=None, quelle="": aufrufe.append(f"anlegen:{c.email}:{quelle}") or {"id": 9})
    monkeypatch.setattr(slack_import, "find_or_create_company", lambda c: None)
    monkeypatch.setattr(slack_import, "send_summary", lambda report, quelle="": None)
    return slack_import, aufrufe


def test_visitenkarte_bekannter_kontakt_ohne_apollo_und_kategorie(monkeypatch):
    """Bei 2 Tagen Rückblick wird jede Karte zweimal gesehen – das zweite Mal darf nur die Prüfung kosten."""
    karte = ContactData(email="max@firma.de", first_name="Max", last_name="Muster")
    slack_import, aufrufe = _karten_welt(monkeypatch, [{"text": ""}], [(b"k1", "image/jpeg")], {b"k1": karte},
                                         in_propstack={"max@firma.de"})
    report = slack_import.run_pipeline()

    assert aufrufe == ["ki:image/jpeg", "propstack?max@firma.de"]
    assert len(report.contacts_skipped_duplicate) == 1 and report.errors == []


def test_visitenkarte_ein_kaputtes_bild_kostet_nicht_die_anderen(monkeypatch):
    karte = ContactData(email="max@firma.de", first_name="Max", last_name="Muster")
    bilder = [(b"kaputt", "image/png"), (b"k1", "image/png")]
    slack_import, aufrufe = _karten_welt(monkeypatch, [{"text": ""}], bilder,
                                         {b"kaputt": RuntimeError("400 invalid image"), b"k1": karte})
    report = slack_import.run_pipeline()

    assert "anlegen:max@firma.de:Visitenkarte" in aufrufe
    assert len(report.contacts_created) == 1
    assert any("Visitenkarte nicht auswertbar" in e.error for e in report.errors)
