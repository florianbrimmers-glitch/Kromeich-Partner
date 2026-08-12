import types

from comparables_handler import extractor
from comparables_handler.models import Mietangebot

from .fixtures import doc

MILEWAY_JSON = """{
  "ist_mietangebot": true,
  "objekt": "Mileway Bergkamen",
  "adresse": "Industriestraße 12",
  "plz": "59192",
  "ort": "Bergkamen",
  "anbieter": "Mileway",
  "empfaenger": "Kromeich & Partner",
  "datum": "2026-04-07",
  "flaeche_qm": 5000,
  "nutzungsart": "Logistik",
  "sicherheit": "3 Monatsmieten",
  "indexierung": "VPI 100%",
  "eigenes_angebot": false,
  "ist_vorlage": false,
  "ist_eigenmiete": false,
  "ist_anlage": false,
  "optionen": [
    {"laufzeit_monate": 60, "kaltmiete_eur_qm": 4.58, "kaltmiete_absolut_eur": null,
     "nebenkosten_eur_qm": 2.15, "mietfreie_monate": 3, "flaeche_qm": null, "hinweis": null}
  ],
  "confidence": 0.92,
  "begruendung": "Indikatives Mietangebot"
}"""


def _patch(monkeypatch, text: str):
    msg = types.SimpleNamespace(content=[types.SimpleNamespace(text=text)])
    client = types.SimpleNamespace(messages=types.SimpleNamespace(create=lambda **kw: msg))
    monkeypatch.setattr(extractor, "_get_client", lambda: client)


def test_referenzantwort_wird_geparst(monkeypatch):
    _patch(monkeypatch, MILEWAY_JSON)
    angebot = extractor.extract_angebot([{"type": "text", "text": "x"}])
    assert angebot is not None
    assert angebot.ist_mietangebot
    assert angebot.optionen[0].kaltmiete_eur_qm == 4.58
    assert angebot.optionen[0].nebenkosten_eur_qm == 2.15
    assert angebot.plz == "59192"


def test_fenced_json_wird_geparst(monkeypatch):
    _patch(monkeypatch, f"```json\n{MILEWAY_JSON}\n```")
    angebot = extractor.extract_angebot([{"type": "text", "text": "x"}])
    assert angebot is not None
    assert angebot.objekt == "Mileway Bergkamen"


def test_vorgeplaudertes_json_wird_geparst(monkeypatch):
    _patch(monkeypatch, f"Hier das Ergebnis:\n{MILEWAY_JSON}\nSoweit die Extraktion.")
    assert extractor.extract_angebot([{"type": "text", "text": "x"}]) is not None


def test_unparsebare_antwort_gibt_none(monkeypatch):
    """None = Retry im nächsten Lauf, kein stiller Datenverlust."""
    _patch(monkeypatch, "Ich konnte das Dokument nicht lesen.")
    assert extractor.extract_angebot([{"type": "text", "text": "x"}]) is None


def test_unbekannte_felder_werden_ignoriert(monkeypatch):
    _patch(monkeypatch, '{"ist_mietangebot": true, "confidence": 0.8, "quatsch": 1, "optionen": []}')
    angebot = extractor.extract_angebot([{"type": "text", "text": "x"}])
    assert angebot is not None
    assert angebot.optionen == []


def test_staffel_mit_drei_optionen(monkeypatch):
    """Westcore Bitterfeld: 4,50 / 4,30 / 4,05 je Laufzeit."""
    _patch(monkeypatch, """{
      "ist_mietangebot": true, "plz": "06749", "confidence": 0.9,
      "optionen": [
        {"laufzeit_monate": 60, "kaltmiete_eur_qm": 4.50},
        {"laufzeit_monate": 84, "kaltmiete_eur_qm": 4.30},
        {"laufzeit_monate": 120, "kaltmiete_eur_qm": 4.05}
      ]
    }""")
    angebot = extractor.extract_angebot([{"type": "text", "text": "x"}])
    assert [o.kaltmiete_eur_qm for o in angebot.optionen] == [4.50, 4.30, 4.05]


def test_pdf_wird_als_dokumentblock_gesendet():
    """PDFs gehen direkt an Claude – liest auch gescannte Angebote."""
    content = extractor.build_content(doc(), b"%PDF-1.4 fake", None)
    assert content is not None
    assert content[0]["type"] == "document"
    assert content[0]["source"]["media_type"] == "application/pdf"
    assert "Mileway Indikatives Mietangebot" in content[1]["text"]


def test_zu_grosses_pdf_wird_abgelehnt(monkeypatch):
    monkeypatch.setattr(extractor.config, "MAX_PDF_BYTES", 10)
    assert extractor.build_content(doc(), b"x" * 100, None) is None


def test_text_dokument_wird_als_textblock_gesendet():
    content = extractor.build_content(
        doc(name="Angebot.gdoc", mime_type="application/vnd.google-apps.document"),
        None, "Kaltmiete 4,58 EUR/m2",
    )
    assert content is not None
    assert content[0]["type"] == "text"
    assert "4,58" in content[0]["text"]


def test_leerer_text_gibt_keinen_content():
    content = extractor.build_content(
        doc(name="leer.gdoc", mime_type="application/vnd.google-apps.document"), None, "   ",
    )
    assert content is None


def test_ordnername_wird_als_kontext_mitgegeben():
    content = extractor.build_content(doc(pfad_hinweis="03. Leasing"), b"%PDF fake", None)
    assert "03. Leasing" in content[1]["text"]


def test_parse_json_ohne_klammern():
    try:
        extractor.parse_extraction_json("kein json")
    except Exception as e:
        assert e.__class__.__name__ == "JSONDecodeError"
    else:
        raise AssertionError("hätte scheitern müssen")


def test_modell_toleriert_string_zahlen():
    """Claude liefert gelegentlich '4.58' statt 4.58."""
    angebot = Mietangebot.model_validate({
        "ist_mietangebot": True, "confidence": "0.9",
        "optionen": [{"laufzeit_monate": "60", "kaltmiete_eur_qm": "4.58"}],
    })
    assert angebot.optionen[0].kaltmiete_eur_qm == 4.58
    assert angebot.optionen[0].laufzeit_monate == 60
