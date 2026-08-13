"""Monatsbericht als Asana-Unteraufgabe.

Der wichtigste Fall ist die Idempotenz: der Monatslauf kann wiederholt werden
(Nachlauf, manueller Re-Run), und dabei darf keine zweite Unteraufgabe und
kein doppelter Anhang entstehen.

Alle HTTP-Aufrufe sind ersetzt – die Tests gehen nie ins Netz.
"""

import httpx
import pytest

from comparables_handler import aggregate, asana_gateway, config, kennzahlen
from comparables_handler.models import ComparableZeile, RunReport

PARENT = "1217454616756224"


def _zeile(plz: str, miete: float, adresse: str) -> ComparableZeile:
    from comparables_handler import regions
    leit = regions.leitregion(plz)
    zon = regions.zone(plz)
    return ComparableZeile(
        quelle="propstack", file_id=f"{plz}-{adresse}", datei="Objekt", objekt="Objekt",
        adresse=adresse, plz=plz, region_key=leit[0], region_label=leit[1],
        zone_key=zon[0], zone_label=zon[1],
        nutzungsart="Halle/Lager", kaltmiete_eur_qm=miete,
        miete_feld="custom_fields.intern_mietpreis_hallenflache",
    )


def _daten():
    zeilen = [_zeile("40213", 6.0 + i * 0.5, f"Weg {i}") for i in range(6)]
    stats = aggregate.aggregiere(zeilen)
    tabellen = [kennzahlen.baue_tabelle(zeilen, "Halle/Lager")]
    return stats, tabellen


class _Aufrufe:
    """Sammelt die HTTP-Aufrufe, die der Gateway machen WÜRDE."""

    def __init__(self, subtasks=(), anhaenge=()):
        self.subtasks = list(subtasks)
        self.anhaenge = list(anhaenge)
        self.requests: list[tuple[str, str, dict | None]] = []
        self.uploads: list[str] = []

    def request(self, method, url, **kw):
        pfad = url.replace(asana_gateway.ASANA_BASE_URL, "")
        self.requests.append((method, pfad, kw.get("json")))
        if method == "GET" and pfad.endswith("/subtasks"):
            daten = {"data": [{"gid": "sub1", "name": n} for n in self.subtasks]}
        elif method == "GET" and pfad == "/attachments":
            daten = {"data": [{"gid": "att1", "name": n} for n in self.anhaenge]}
        elif method == "POST" and pfad == "/tasks":
            daten = {"data": {"gid": "neu1"}}
        else:
            daten = {"data": {}}
        return httpx.Response(200, json=daten, request=httpx.Request(method, url))

    def post(self, url, **kw):
        name = kw["files"]["file"][0]
        self.uploads.append(name)
        return httpx.Response(
            200, json={"data": {"gid": f"att-{name}"}},
            request=httpx.Request("POST", url),
        )


@pytest.fixture
def scharf(monkeypatch):
    """Token gesetzt, kein Dry-Run – der Zustand im Monatslauf."""
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("ASANA_UPLOAD", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("NO_WRITE", "false")
    monkeypatch.delenv("ASANA_ATTACH_DATASET", raising=False)
    monkeypatch.setenv("ASANA_PARENT_TASK_ID", PARENT)


def _verdrahte(monkeypatch, aufrufe: _Aufrufe):
    monkeypatch.setattr(asana_gateway.httpx, "request", aufrufe.request)
    monkeypatch.setattr(asana_gateway.httpx, "post", aufrufe.post)


# --- Konfiguration ---------------------------------------------------------
def test_ohne_token_wird_uebersprungen(monkeypatch):
    """Ein fehlendes Secret darf den Report nicht scheitern lassen."""
    monkeypatch.setenv("ASANA_UPLOAD", "true")
    monkeypatch.setenv("NO_WRITE", "false")
    for name in config.ASANA_TOKEN_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    assert config.asana_aktiv() is False
    assert "Token" in config.asana_grund()

    stats, tabellen = _daten()
    assert asana_gateway.veroeffentliche(
        stats, RunReport(quelle="propstack"), "August 2026", {}, tabellen) is None


def test_asana_ist_opt_in(monkeypatch):
    """Ein gesetzter Token allein darf noch keine Aufgaben anlegen."""
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "test-token")
    monkeypatch.delenv("ASANA_UPLOAD", raising=False)
    assert config.asana_aktiv() is False
    assert "Opt-in" in config.asana_grund()

    monkeypatch.setenv("ASANA_UPLOAD", "true")
    assert config.asana_aktiv() is True


def test_dry_run_haelt_asana_nicht_auf(monkeypatch):
    """DRY_RUN gilt dem Slack-Post; das interne Asana-Archiv laeuft weiter."""
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("ASANA_UPLOAD", "true")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("NO_WRITE", "false")
    assert config.asana_aktiv() is True


def test_no_write_schaltet_asana_ab(monkeypatch):
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("ASANA_UPLOAD", "true")
    monkeypatch.setenv("NO_WRITE", "true")
    assert config.asana_aktiv() is False
    assert config.asana_grund() == "NO_WRITE"


# --- Namen (Idempotenz-Schlüssel) ------------------------------------------
def test_namen_sind_aus_dem_stand_reproduzierbar():
    assert asana_gateway.aufgaben_name("August 2026") == "Vergleichsmieten August 2026"
    assert asana_gateway.anhang_name("August 2026", config.VERTRAULICH_INTERN) \
        == "Vergleichsmieten_August_2026.pdf"
    assert asana_gateway.anhang_name("August 2026", config.VERTRAULICH_EXTERN) \
        == "Vergleichsmieten_August_2026_extern.pdf"


# --- Beschreibung ----------------------------------------------------------
def test_notiz_traegt_die_kennzahlen():
    stats, tabellen = _daten()
    notiz = asana_gateway.baue_notiz(
        stats, RunReport(quelle="propstack"), "August 2026", tabellen)

    assert "August 2026" in notiz
    assert "Halle/Lager" in notiz
    assert "6 Standorte" in notiz
    assert "Düsseldorf" in notiz
    # Die Vertraulichkeits-Ansage muss in der Aufgabe stehen, nicht nur im PDF
    assert "INTERN" in notiz
    assert "Nicht nach außen geben" in notiz


def test_notiz_sagt_wenn_es_keine_basis_gibt():
    notiz = asana_gateway.baue_notiz([], RunReport(), "August 2026", [])
    assert "Keine verwertbaren Mieten" in notiz


def test_notiz_benennt_den_fehlenden_periodenvergleich():
    stats, tabellen = _daten()
    notiz = asana_gateway.baue_notiz(
        stats, RunReport(quelle="propstack"), "August 2026", tabellen, None)
    assert "noch keine Basis" in notiz


# --- Trockenlauf -----------------------------------------------------------
def test_no_write_ruehrt_asana_nicht_an(monkeypatch, scharf):
    monkeypatch.setenv("NO_WRITE", "true")
    aufrufe = _Aufrufe()
    _verdrahte(monkeypatch, aufrufe)

    stats, tabellen = _daten()
    url = asana_gateway.veroeffentliche(
        stats, RunReport(quelle="propstack"), "August 2026",
        {config.VERTRAULICH_INTERN: "/tmp/x.pdf"}, tabellen)

    assert url is None
    assert aufrufe.requests == []
    assert aufrufe.uploads == []


# --- Anlegen und Aktualisieren --------------------------------------------
def test_neue_unteraufgabe_mit_beiden_anhaengen(monkeypatch, scharf, tmp_path):
    intern = tmp_path / "i.pdf"
    intern.write_bytes(b"%PDF-1.4 intern")
    extern = tmp_path / "e.pdf"
    extern.write_bytes(b"%PDF-1.4 extern")

    aufrufe = _Aufrufe(subtasks=["Vergleichsmieten Juli 2026"])
    _verdrahte(monkeypatch, aufrufe)

    stats, tabellen = _daten()
    url = asana_gateway.veroeffentliche(
        stats, RunReport(quelle="propstack"), "August 2026",
        {config.VERTRAULICH_INTERN: str(intern), config.VERTRAULICH_EXTERN: str(extern)},
        tabellen,
    )

    methoden = [(m, p) for m, p, _ in aufrufe.requests]
    assert ("POST", "/tasks") in methoden
    assert ("PUT", "/tasks/sub1") not in methoden      # Juli ist ein anderer Monat
    assert aufrufe.uploads == [
        "Vergleichsmieten_August_2026.pdf",
        "Vergleichsmieten_August_2026_extern.pdf",
    ]
    assert url and "neu1" in url


def test_zweiter_lauf_im_selben_monat_legt_nichts_neu_an(monkeypatch, scharf, tmp_path):
    """Der Kern: Wiederholung aktualisiert, sie dupliziert nicht."""
    pdf = tmp_path / "i.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    aufrufe = _Aufrufe(
        subtasks=["Vergleichsmieten August 2026"],
        anhaenge=["Vergleichsmieten_August_2026.pdf"],
    )
    _verdrahte(monkeypatch, aufrufe)

    stats, tabellen = _daten()
    asana_gateway.veroeffentliche(
        stats, RunReport(quelle="propstack"), "August 2026",
        {config.VERTRAULICH_INTERN: str(pdf)}, tabellen,
    )

    methoden = [(m, p) for m, p, _ in aufrufe.requests]
    assert ("POST", "/tasks") not in methoden
    assert ("PUT", "/tasks/sub1") in methoden
    assert aufrufe.uploads == [], "vorhandener Anhang darf nicht doppelt hochgeladen werden"


def test_fehlender_anhang_bricht_den_lauf_nicht_ab(monkeypatch, scharf):
    aufrufe = _Aufrufe()
    _verdrahte(monkeypatch, aufrufe)

    stats, tabellen = _daten()
    report = RunReport(quelle="propstack")
    url = asana_gateway.veroeffentliche(
        stats, report, "August 2026",
        {config.VERTRAULICH_INTERN: "/gibt/es/nicht.pdf"}, tabellen,
    )

    assert url is not None            # Aufgabe entsteht trotzdem
    assert aufrufe.uploads == []
    assert any("nicht.pdf" in f or "Anhang" in f for f in report.fehler)


def test_upload_fehler_landet_im_report(monkeypatch, scharf, tmp_path):
    pdf = tmp_path / "i.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    aufrufe = _Aufrufe()
    _verdrahte(monkeypatch, aufrufe)
    monkeypatch.setattr(
        asana_gateway.httpx, "post",
        lambda url, **kw: httpx.Response(
            403, text="Forbidden", request=httpx.Request("POST", url)),
    )

    stats, tabellen = _daten()
    report = RunReport(quelle="propstack")
    asana_gateway.veroeffentliche(
        stats, report, "August 2026", {config.VERTRAULICH_INTERN: str(pdf)}, tabellen)

    assert any("Anhang" in f for f in report.fehler)


def test_upload_setzt_keinen_json_content_type(monkeypatch, scharf, tmp_path):
    """Beim Multipart-POST muss der Content-Type fehlen, sonst 400 von Asana."""
    pdf = tmp_path / "i.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    gesehen = {}

    def _post(url, **kw):
        gesehen.update(kw.get("headers") or {})
        gesehen["_files"] = kw.get("files")
        gesehen["_data"] = kw.get("data")
        return httpx.Response(200, json={"data": {"gid": "a1"}},
                              request=httpx.Request("POST", url))

    aufrufe = _Aufrufe()
    _verdrahte(monkeypatch, aufrufe)
    monkeypatch.setattr(asana_gateway.httpx, "post", _post)

    stats, tabellen = _daten()
    asana_gateway.veroeffentliche(
        stats, RunReport(quelle="propstack"), "August 2026",
        {config.VERTRAULICH_INTERN: str(pdf)}, tabellen)

    assert "Content-Type" not in gesehen
    assert gesehen["_data"] == {"parent": "neu1"}
    assert gesehen["_files"]["file"][0] == "Vergleichsmieten_August_2026.pdf"
