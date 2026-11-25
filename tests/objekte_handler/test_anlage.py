"""Objekt-Anlage über den Propstack-Connector (objekte_handler/anlage.py), ohne Netz.

Die Slack-Nachrichten sind die aus #ver-objekte vom 24./25.11.2026, so wie
conversations.history sie liefert. Die Antworten der KI sind wie die der Messages-API mit
MCP-Connector aufgebaut: mcp_tool_use / mcp_tool_result / text.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest

from objekte_handler import anlage, config, main
from objekte_handler.models import Classification, MessageType, RunReport

MAREK = "U092XRXSY3X"
UNNA_LINK = {"ts": "1795513641.524429", "user": MAREK,
             "text": "<https://www.fraserspropertyindustrial.com/de/objekt/germany/unna22.html|fraserspropertyindustrial.com/de/objekt/germany/unna22.html>"}
BITTE_ANLEGEN = {"ts": "1795513645.740279", "user": MAREK, "text": "bitte anlegen"}
REMSCHEID = {
    "ts": "1795600175.387459", "user": MAREK, "text": "Exposé Objekt Remscheid - LIP Invest",
    "files": [{"id": "F0CLNJLLG75", "name": "Remscheid_Exposé.pdf", "mimetype": "application/pdf", "size": 2_831_155,
               "url_private_download": "https://files.slack.com/files-pri/T07GCS7CDTJ-F0CLNJLLG75/download/remscheid_expos_.pdf"}],
}
SCHON_ANGELEGT = {"ts": "1795600187.788809", "user": MAREK, "text": "Hab ich schon ordentlich angelegt"}
BROKERS = [
    {"id": 347158, "name": "Florian Brimmers", "email": "florian.brimmers@kromeichpartner.de"},
    {"id": 387451, "name": "Marek Zimmermann", "email": "marek.zimmermann@kromeichpartner.de"},
    {"id": 254958, "name": "Lena Klinnert", "email": "lena.klinnert@kromeichpartner.de"},
]


# --- Welche Nachrichten, welches Material ------------------------------------------------

@pytest.mark.parametrize("msg, typ, erwartet", [
    (BITTE_ANLEGEN, "fehlt_in_ps", True),
    (REMSCHEID, "fehlt_in_ps", True),
    (REMSCHEID, "ignorieren", True),                                   # Exposé erkennt man auch ohne die KI
    ({**REMSCHEID, "text": ""}, None, True),                           # nur die Datei
    ({**REMSCHEID, "text": "Mietvertrag Entwurf", "files": [{**REMSCHEID["files"][0], "name": "Vertrag.pdf"}]},
     "ignorieren", False),
    ({"ts": "1.1", "text": "Mietpreis zwischen 6 - 6,40€"}, "ignorieren", False),
])
def test_ist_anlagefall(msg, typ, erwartet):
    assert anlage.ist_anlagefall(msg, typ) is erwartet


def test_link_und_bitte_anlegen_gehoeren_zusammen():
    """24.11.2026: Marek postet den Link und 4 Sekunden später „bitte anlegen“."""
    andere = {"ts": "1795513600.000100", "user": "U0806EX3EFL", "text": "<https://example.org/fremd|fremd>"}
    alt = {"ts": "1795510000.000100", "user": MAREK, "text": "<https://example.org/alt|alt>"}   # > 15 min davor
    k = anlage.kontext(BITTE_ANLEGEN, [alt, andere, UNNA_LINK, BITTE_ANLEGEN], None)
    assert k.vorher == [UNNA_LINK["text"]]
    assert k.links == ["https://www.fraserspropertyindustrial.com/de/objekt/germany/unna22.html"]


def test_exposé_pdf_kommt_mit():
    k = anlage.kontext(REMSCHEID, [REMSCHEID, SCHON_ANGELEGT], None)
    assert [d.name for d in k.dateien] == ["Remscheid_Exposé.pdf"]
    assert k.vorher == []        # die Folgenachricht „schon angelegt“ zählt nicht als Material


# --- Betreuer und Zugang ------------------------------------------------------------------

def test_betreuer_ueber_mail_name_und_rueckfall():
    assert anlage.betreuer({"email": "Marek.Zimmermann@kromeichpartner.de"}, BROKERS) == (387451, "Marek Zimmermann")
    assert anlage.betreuer({"real_name": "Marek Zimmermann"}, BROKERS) == (387451, "Marek Zimmermann")   # ohne users:read.email
    # Oguzhan hat keinen eigenen Propstack-Nutzer – wie im Connector: Review-Sitz
    assert anlage.betreuer({"real_name": "Oguzhan Sahin"}, BROKERS) == (254958, "Lena Klinnert")
    assert anlage.betreuer({}, BROKERS) == (254958, "Lena Klinnert")


def _pruefe_token(token: str, secret: str) -> dict:
    """So muss der Connector prüfen (Anweisung im README)."""
    praefix, payload, signatur = token.split(".")
    assert praefix == "svc"
    erwartet = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), f"svc.{payload}".encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    assert hmac.compare_digest(signatur, erwartet)
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def test_service_token_traegt_nutzer_und_laeuft_ab():
    token = anlage.service_token("geheim", 387451, "1795600175.387459", jetzt=1_795_600_000)
    daten = _pruefe_token(token, "geheim")
    assert daten == {"sub": "objekte-handler", "broker_id": 387451, "ts": "1795600175.387459",
                     "iat": 1_795_600_000, "exp": 1_795_600_000 + 30 * 60}
    with pytest.raises(AssertionError):
        _pruefe_token(token, "anderes-geheimnis")


# --- Claude mit den Connector-Tools ------------------------------------------------------

def _tool(id_, name, ok=True):
    return [SimpleNamespace(type="mcp_tool_use", id=id_, name=name, server_name="propstack", input={}),
            SimpleNamespace(type="mcp_tool_result", tool_use_id=id_, is_error=not ok,
                            content=[SimpleNamespace(type="text", text="{}")])]


def _antwort(bloecke, json_text=None, stop="end_turn"):
    inhalt = list(bloecke) + ([SimpleNamespace(type="text", text=json_text)] if json_text else [])
    return SimpleNamespace(stop_reason=stop, content=inhalt)


@pytest.fixture
def ki(monkeypatch):
    """Ersetzt den Anthropic-Client; liefert der Reihe nach die vorgegebenen Antworten."""
    monkeypatch.setenv("PROPSTACK_MCP_SERVICE_SECRET", "geheim")
    aufrufe: list[dict] = []
    antworten: list = []

    def create(**kw):
        aufrufe.append(kw)
        return antworten[len(aufrufe) - 1]

    monkeypatch.setattr(anlage, "_client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create))))
    return antworten, aufrufe


def _lege_an(pdf=b"%PDF-1.7 ..."):
    k = anlage.kontext(REMSCHEID, [REMSCHEID], None)
    return anlage.lege_an(k, 387451, "Marek Zimmermann", REMSCHEID["ts"], "https://slack/p1", [(k.dateien[0], pdf)])


def test_remscheid_existiert_schon(ki):
    """25.11.2026: Das Objekt steht seit 20.03.2026 in Propstack (5159361). Gesucht, nichts angelegt."""
    antworten, aufrufe = ki
    antworten.append(_antwort(_tool("t1", "search_objects") + _tool("t2", "get_object"), json.dumps({
        "ergebnis": "existiert", "objekte": [{"id": 5159361, "art": "einheit", "titel": "Am Weidenbroich 20-22 - Remscheid"}],
        "offen": [], "begruendung": "Gleiche Adresse und Fläche, Eigentümer LIP Invest."})))
    e = _lege_an()
    assert e.ergebnis == "existiert" and [o["id"] for o in e.objekte] == [5159361]
    assert e.aufrufe == ["search_objects", "get_object"]

    kw = aufrufe[0]
    assert kw["model"] == config.ANLAGE_MODELL and config.MCP_BETA in kw["betas"]
    server = kw["mcp_servers"][0]
    assert server["name"] == "propstack" and server["url"] == config.MCP_URL_STANDARD
    assert _pruefe_token(server["authorization_token"], "geheim")["broker_id"] == 387451
    assert {"type": "mcp_toolset", "mcp_server_name": "propstack"} in kw["tools"]
    assert kw["tools"][1]["type"] == "web_fetch_20260209"
    inhalt = kw["messages"][0]["content"]
    assert inhalt[0]["type"] == "document" and inhalt[0]["source"]["media_type"] == "application/pdf"
    assert "Exposé Objekt Remscheid - LIP Invest" in inhalt[-1]["text"]


def test_angelegt_zaehlt_nur_mit_erfolgreichem_anlegeaufruf(ki):
    antworten, _ = ki
    antworten.append(_antwort(_tool("t1", "search_objects") + _tool("t2", "create_project") + _tool("t3", "create_object"),
                              json.dumps({"ergebnis": "angelegt", "objekte": [{"id": 1, "art": "projekt"}, {"id": 2, "art": "einheit"}],
                                          "offen": ["Mietpreis fehlt im Exposé"], "begruendung": "neu"})))
    assert _lege_an().ergebnis == "angelegt"


def test_behauptete_anlage_ohne_aufruf_ist_unklar(ki):
    """„Die Workflows sollen arbeiten, nicht nur so tun“ – auch die KI darf es nicht."""
    antworten, _ = ki
    antworten.append(_antwort(_tool("t1", "search_objects") + _tool("t2", "create_object", ok=False),
                              json.dumps({"ergebnis": "angelegt", "objekte": [{"id": 9}], "offen": [], "begruendung": "x"})))
    e = _lege_an()
    assert e.ergebnis == "unklar" and "kein Anlege-Aufruf war erfolgreich" in e.begruendung


def test_pause_turn_wird_fortgesetzt(ki):
    antworten, aufrufe = ki
    erste = _antwort(_tool("t1", "search_objects"), stop="pause_turn")
    antworten.extend([erste, _antwort(_tool("t2", "create_object"),
                                      json.dumps({"ergebnis": "angelegt", "objekte": [{"id": 7}], "offen": [], "begruendung": ""}))])
    e = _lege_an()
    assert e.ergebnis == "angelegt" and len(aufrufe) == 2
    assert aufrufe[1]["messages"][-1] == {"role": "assistant", "content": erste.content}


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_abbruch_der_ki_ist_unklar(ki, stop):
    antworten, _ = ki
    antworten.append(_antwort(_tool("t1", "create_object"), stop=stop))
    assert _lege_an().ergebnis == "unklar"


def test_ohne_secret_kein_lauf(monkeypatch):
    monkeypatch.delenv("PROPSTACK_MCP_SERVICE_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="PROPSTACK_MCP_SERVICE_SECRET"):
        _lege_an()


def test_antwort_im_thread():
    e = anlage.Ergebnis("angelegt", objekte=[{"id": 1, "art": "projekt", "titel": "Logistikpark Remscheid"},
                                             {"id": 2, "art": "einheit", "titel": "Halle 1"}],
                        offen=["Mietpreis fehlt"])
    text = anlage.antwort(e, "Marek Zimmermann")
    assert "Betreuer Marek Zimmermann, Status Vorbereitung" in text
    assert "• Projekt 1 – Logistikpark Remscheid" in text and "• Einheit 2 – Halle 1" in text and "• Mietpreis fehlt" in text
    assert anlage.antwort(anlage.Ergebnis("existiert", objekte=[{"id": 5159361}]), "x").startswith("Steht schon in Propstack")


# --- Im Ablauf des Handlers -------------------------------------------------------------

@pytest.fixture
def handler(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("NO_WRITE", "false")
    monkeypatch.setenv("OBJEKT_ANLAGE", "true")
    monkeypatch.setenv("PROPSTACK_MCP_SERVICE_SECRET", "geheim")
    spur: list[str] = []
    monkeypatch.setattr(main, "classify_message",
                        lambda text, ctx: Classification(typ=MessageType.FEHLT_IN_PS, confidence=0.9, objekt_name="Remscheid LIP Invest"))
    monkeypatch.setattr(main, "user_profile", lambda uid: {"real_name": "Marek Zimmermann"})
    monkeypatch.setattr(main, "_BROKERS", BROKERS)
    monkeypatch.setattr(main, "get_permalink", lambda ts: "https://slack/p1")
    monkeypatch.setattr(main, "download_file", lambda url: spur.append("pdf") or b"%PDF")
    monkeypatch.setattr(main, "add_checkmark", lambda ts: spur.append("haken") or True)
    monkeypatch.setattr(main, "post_thread_reply", lambda ts, text: spur.append(f"antwort:{text.splitlines()[0]}") or True)
    monkeypatch.setattr(main, "create_task", lambda payload: spur.append(f"aufgabe:{payload.title}") or 1)
    monkeypatch.setattr(main, "append_record", lambda record: None)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    return spur


def test_existiert_gibt_antwort_und_haken_aber_keine_aufgabe(handler, monkeypatch):
    erg = anlage.Ergebnis("existiert", objekte=[{"id": 5159361}])
    monkeypatch.setattr(main.anlage, "lege_an", lambda *a, **k: erg)
    report = RunReport()
    main._process_message(REMSCHEID, None, "lauf", report, [REMSCHEID])
    assert handler == ["pdf", "haken", "antwort:Steht schon in Propstack – nichts neu angelegt:"]
    assert report.existiert == 1 and report.stufe_b == 0 and report.fehler == []


def test_unklar_faellt_auf_die_aufgabe_zurueck(handler, monkeypatch):
    monkeypatch.setattr(main.anlage, "lege_an", lambda *a, **k: anlage.Ergebnis("unklar", begruendung="Link nicht lesbar"))
    report = RunReport()
    main._process_message(BITTE_ANLEGEN, None, "lauf", report, [UNNA_LINK, BITTE_ANLEGEN])
    assert handler[0] == "aufgabe:Objekt fehlt in Propstack: Remscheid LIP Invest" and report.stufe_b == 1


def test_fehler_beim_anlegen_macht_den_lauf_rot_ohne_haken(handler, monkeypatch):
    def kaputt(*a, **k):
        raise RuntimeError("MCP 401")
    monkeypatch.setattr(main.anlage, "lege_an", kaputt)
    report = RunReport()
    main._process_message(REMSCHEID, None, "lauf", report, [REMSCHEID])
    assert "haken" not in handler and report.fehler and "MCP 401" in report.fehler[0]


def test_no_write_ruft_die_ki_nicht_auf(handler, monkeypatch):
    monkeypatch.setenv("NO_WRITE", "true")
    monkeypatch.setattr(main.anlage, "lege_an", lambda *a, **k: pytest.fail("kein Aufruf im Lese-Lauf"))
    main._process_message(REMSCHEID, None, "lauf", RunReport(), [REMSCHEID])
    assert handler == []


def test_ausgeschaltet_bleibt_alles_wie_bisher(handler, monkeypatch):
    monkeypatch.setenv("OBJEKT_ANLAGE", "false")
    monkeypatch.setattr(main.anlage, "lege_an", lambda *a, **k: pytest.fail("Anlage ist aus"))
    main._process_message(REMSCHEID, None, "lauf", RunReport(), [REMSCHEID])
    assert handler[0].startswith("aufgabe:Objekt fehlt in Propstack")


def test_im_dry_run_nie_anlegen(monkeypatch):
    monkeypatch.setenv("OBJEKT_ANLAGE", "true")
    monkeypatch.setenv("DRY_RUN", "true")
    assert config.objekt_anlage() is False


def test_probelauf_auf_eine_nachricht_trotz_haken(monkeypatch):
    """NUR_TS: Remscheid trägt schon das ✅ vom 25.11. – der Probelauf soll sie trotzdem sehen."""
    monkeypatch.setenv("NUR_TS", REMSCHEID["ts"])
    mit_haken = {**REMSCHEID, "reactions": [{"name": "white_check_mark", "users": ["UBOT"], "count": 1}]}
    monkeypatch.setattr(main, "get_bot_user_id", lambda: "UBOT")
    monkeypatch.setattr(main, "_collect_candidates", lambda bot: [(UNNA_LINK, None), (mit_haken, None)])
    gesehen = []
    monkeypatch.setattr(main, "_process_message", lambda msg, ctx, run_id, report, nachbarn=None: gesehen.append((msg["ts"], len(nachbarn))))
    main.run_pipeline()
    assert gesehen == [(REMSCHEID["ts"], 2)]
