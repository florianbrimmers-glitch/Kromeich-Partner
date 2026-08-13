"""Interne vs. externe Fassung des PDF.

Die Mieten stammen überwiegend aus `intern_mietpreis_*`: Konditionen, die K&P
aus Mandaten und Anfragen kennt und die der Vermieter nicht veröffentlicht.
Vorgabe K&P (13.08.2026): solche Werte dürfen nicht nach außen kommuniziert
werden. Als Aggregat über viele Standorte ist das eine Marktaussage – bei n=1
ist der ausgewiesene "Median" exakt die Miete EINES Objekts.

Diese Tests nageln fest, dass die externe Fassung keine rückrechenbare Zeile
und keine Objektnamen enthält.
"""

import pytest

from comparables_handler import aggregate, config, kennzahlen, report_pdf
from comparables_handler.models import ComparableZeile


def _zeile(plz: str, miete: float, adresse: str, objekt: str) -> ComparableZeile:
    from comparables_handler import regions
    leit = regions.leitregion(plz)
    zon = regions.zone(plz)
    return ComparableZeile(
        quelle="propstack", file_id=f"{plz}-{adresse}", datei=objekt, objekt=objekt,
        adresse=adresse, plz=plz, region_key=leit[0], region_label=leit[1],
        zone_key=zon[0], zone_label=zon[1],
        nutzungsart="Halle/Lager", kaltmiete_eur_qm=miete,
        miete_feld="custom_fields.intern_mietpreis_hallenflache",
    )


def _datenbasis() -> list[ComparableZeile]:
    """Düsseldorf mit 6 Standorten (extern zeigbar), Berlin mit 2 (nicht)."""
    zeilen = [
        _zeile("40213", 6.0 + i * 0.1, f"Düsseldorfer Weg {i}", f"Objekt D{i}")
        for i in range(6)
    ]
    zeilen += [
        _zeile("10115", 9.5, "Geheimstraße 1", "Vertrauliches Objekt A"),
        _zeile("10117", 9.8, "Geheimstraße 2", "Vertrauliches Objekt B"),
    ]
    return zeilen


@pytest.fixture(autouse=True)
def _intern_als_standard(monkeypatch):
    monkeypatch.delenv("VERTRAULICHKEIT", raising=False)


# --- Konfiguration ---------------------------------------------------------
def test_standard_erzeugt_beide_fassungen():
    """Ohne gesetzte Variable entstehen interne UND externe Fassung."""
    assert config.vertraulichkeit() == config.VERTRAULICH_BEIDE
    assert config.pdf_fassungen() == (
        config.VERTRAULICH_INTERN, config.VERTRAULICH_EXTERN)


def test_einzelne_fassung_waehlbar(monkeypatch):
    monkeypatch.setenv("VERTRAULICHKEIT", "extern")
    assert config.pdf_fassungen() == (config.VERTRAULICH_EXTERN,)


def test_unbekannte_stufe_bricht_ab(monkeypatch):
    """Ein Tippfehler darf nicht stillschweigend zur internen Fassung führen."""
    monkeypatch.setenv("VERTRAULICHKEIT", "öffentlich")
    with pytest.raises(RuntimeError, match="VERTRAULICHKEIT"):
        config.vertraulichkeit()


def test_extern_schreibt_eigene_datei(monkeypatch):
    """Am Dateinamen muss sichtbar sein, welche Fassung man in der Hand hat."""
    monkeypatch.delenv("PDF_PATH", raising=False)
    assert config.pdf_path(config.VERTRAULICH_INTERN) == "comparables_report.pdf"
    assert config.pdf_path(config.VERTRAULICH_EXTERN) == "comparables_report_extern.pdf"
    monkeypatch.setenv("PDF_PATH", "/tmp/lauf/august.pdf")
    assert config.pdf_path(config.VERTRAULICH_EXTERN) == "/tmp/lauf/august_extern.pdf"


# --- Kennzahlen-Tabelle ----------------------------------------------------
def test_extern_entfernt_zeilen_unter_der_schwelle():
    tabelle = kennzahlen.baue_tabelle(_datenbasis(), "Halle/Lager")
    labels_intern = [z.label for z in tabelle.zeilen]
    assert "Berlin" in labels_intern, "intern muss Berlin (n=2) zeigen"

    extern = report_pdf.externe_kennzahlen(tabelle)
    labels = [z.label for z in extern.zeilen]
    assert "Berlin" not in labels
    assert "Düsseldorf" in labels
    assert all(z.n >= config.MIN_N_EXTERN for z in extern.zeilen)


def test_extern_laesst_die_summen_stehen():
    """Die Summenzeilen sind über mehrere Märkte gebildet und bleiben."""
    extern = report_pdf.externe_kennzahlen(
        kennzahlen.baue_tabelle(_datenbasis(), "Halle/Lager"))
    assert extern.gesamt is not None
    assert extern.gesamt.n == 8
    assert f"{config.GRUPPE_TOP} gesamt" in [z.label for z in extern.zeilen]


def test_extern_filtert_nicht_das_original():
    """Die interne Fassung im selben Lauf darf nicht beschnitten werden."""
    tabelle = kennzahlen.baue_tabelle(_datenbasis(), "Halle/Lager")
    vorher = [z.label for z in tabelle.zeilen]
    report_pdf.externe_kennzahlen(tabelle)
    assert [z.label for z in tabelle.zeilen] == vorher


def test_extern_unterdrueckt_summen_bei_zu_kleiner_basis():
    """Fünf Standorte insgesamt, aber nur zwei Werte -> nichts zeigbar."""
    schmal = [
        _zeile("10115", 9.5, "Geheimstraße 1", "Vertraulich A"),
        _zeile("10117", 9.8, "Geheimstraße 2", "Vertraulich B"),
    ]
    extern = report_pdf.externe_kennzahlen(
        kennzahlen.baue_tabelle(schmal, "Halle/Lager"))
    assert extern.zeilen == []
    assert extern.gesamt is None
    assert extern.anteile == []


# --- Regionsblock ----------------------------------------------------------
def test_extern_entfernt_einzelwerte_und_kleine_regionen():
    stats = aggregate.aggregiere(_datenbasis())
    assert aggregate.einzelwerte(stats, "Halle/Lager"), "intern gibt es Einzelwerte"

    extern = report_pdf.externe_stats(stats)
    assert aggregate.einzelwerte(extern, "Halle/Lager") == []
    for s in extern:
        assert s.ebene == "gesamt" or s.n >= config.MIN_N_EXTERN


def test_extern_behaelt_die_gesamtzeile():
    """Ohne Gesamtzeile hätte das PDF keine Datenbasis-Aussage."""
    extern = report_pdf.externe_stats(aggregate.aggregiere(_datenbasis()))
    assert aggregate.gesamt(extern) is not None
    assert aggregate.art_gesamt(extern, "Halle/Lager") is not None


# --- Das PDF selbst --------------------------------------------------------
@pytest.fixture
def _standardschriften(monkeypatch, tmp_path):
    """Erzwingt die reportlab-Standardschriften.

    Mit den eingebetteten K&P-TTFs schreibt reportlab den Text als
    CID-Hexstrings – dann ist er ohne ToUnicode-Auflösung nicht prüfbar. Mit
    Helvetica/Times stehen die Zeichenketten im Klartext im Seiten-Stream.
    Geprüft wird der INHALT des PDF, nicht seine CI-Treue.
    """
    monkeypatch.setenv("KP_DESIGN_DIR", str(tmp_path / "ohne-schriften"))


def _pdf_text(pfad: str) -> str:
    """Sichtbarer Text des PDF.

    reportlab schreibt die Seiten-Streams als ASCII85 + Flate, deshalb erst
    auspacken und dann die Zeichenketten der Textoperatoren einsammeln.
    Geprüft wird bewusst nur auf EINZELNE WÖRTER: reportlab bricht Zeilen an
    Leerzeichen um, ein mehrwortiger Suchbegriff kann deshalb über zwei
    Textblöcke verteilt sein. Umlaute stehen oktal escaped und werden nicht
    gesucht.
    """
    import base64
    import re
    import zlib

    def _aus(daten: bytes) -> bytes:
        for versuch in (
            lambda d: zlib.decompress(d),
            lambda d: zlib.decompress(base64.a85decode(
                d.strip().removesuffix(b"~>"), ignorechars=b" \n\r\t")),
        ):
            try:
                return versuch(daten)
            except Exception:
                continue
        return daten      # unkodierter Stream

    with open(pfad, "rb") as f:
        roh = f.read()

    stuecke = [
        _aus(treffer.group(1))
        for treffer in re.finditer(rb"stream\r?\n(.*?)endstream", roh, re.S)
    ]

    inhalt = b"\n".join(stuecke).decode("latin-1")
    return " ".join(re.findall(r"\((?:[^()\\]|\\.)*\)", inhalt))


def test_extern_pdf_nennt_keine_objekte(tmp_path, monkeypatch, _standardschriften):
    from comparables_handler.models import RunReport

    pytest.importorskip("reportlab")

    zeilen = _datenbasis()
    stats = aggregate.aggregiere(zeilen)
    tabellen = [kennzahlen.baue_tabelle(zeilen, "Halle/Lager")]
    pfad = str(tmp_path / "extern.pdf")

    report_pdf.erzeuge_pdf(stats, RunReport(quelle="propstack"), "August 2026",
                          pfad, tabellen, None, config.VERTRAULICH_EXTERN)
    text = _pdf_text(pfad)

    # Objektnamen und Adressen dürfen nicht auftauchen. Sie sind der Schlüssel:
    # eine Miete ist erst dann eine weitergegebene Kondition, wenn sie einem
    # Objekt zuzuordnen ist. Ein Spannen-Maximum über den Gesamtbestand ist
    # keinem Objekt zuzuordnen und bleibt deshalb stehen.
    for verboten in ("Vertrauliches", "Geheimstra", "D1", "D2"):
        assert verboten not in text, f"{verboten!r} steht im externen PDF"
    # Berlin hat n=2 – die Zeile würde die Miete auf zwei Objekte einengen
    assert "Berlin" not in text
    # Überschrift des Einzelwerte-Blocks ("… ohne belastbaren Median")
    assert "belastbaren" not in text
    assert "Adressaten" in text


def test_internes_pdf_bleibt_vollstaendig(tmp_path, monkeypatch, _standardschriften):
    from comparables_handler.models import RunReport

    pytest.importorskip("reportlab")

    zeilen = _datenbasis()
    stats = aggregate.aggregiere(zeilen)
    tabellen = [kennzahlen.baue_tabelle(zeilen, "Halle/Lager")]
    pfad = str(tmp_path / "intern.pdf")

    report_pdf.erzeuge_pdf(stats, RunReport(quelle="propstack"), "August 2026",
                          pfad, tabellen, None, config.VERTRAULICH_INTERN)
    text = _pdf_text(pfad)

    assert "Berlin" in text
    assert "Vertrauliches" in text
    assert "internen" in text
