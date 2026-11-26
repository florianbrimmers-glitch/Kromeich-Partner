"""Objekte aus #ver-objekte anlegen – über den Propstack-Connector, nach dessen Regeln.

Anlass (25.11.2026): Für ein Exposé oder ein „bitte anlegen“ schrieb der Handler nur eine
Aufgabe „Objekt fehlt in Propstack“ an Lena – auch wenn es das Objekt längst gab (Remscheid,
LIP Invest, seit 20.03.2026 im Bestand). Florian: „Die Workflows sollen arbeiten, nicht nur
so tun.“

Ablauf je Nachricht:
1. Material sammeln: Text, Exposé-PDFs, Links, die Nachricht(en) desselben Autors kurz davor
   („Link“ + „bitte anlegen“ kommen oft getrennt) und den Thread.
2. Claude arbeitet mit den Tools des Propstack-Connectors (MCP-Server). Erst suchen; gibt es
   das Objekt, wird nichts angelegt. Sonst Projekt und Einheiten nach den Regeln, die der
   Connector in seinen Tool-Beschreibungen mitbringt (Feldregeln, Dublettenprüfung,
   Write-Log, Prüfaufgabe für Fehlendes).
3. Der Connector legt Objekte aus diesem Weg im Status „Vorbereitung“ an – nicht in
   „Vermarktung“, damit nichts ungesehen in Exposéversand und Website geht.
4. Antwort im Thread mit dem Ergebnis; ✅ heißt hier „erledigt“.

Zugang: ein kurzlebiges, signiertes Service-Token (HMAC, Secret PROPSTACK_MCP_SERVICE_SECRET).
Es trägt den Propstack-Nutzer, unter dem angelegt wird – wer in Slack gepostet hat –, damit
der Betreuer stimmt. Die Gegenseite im Connector prüft Signatur, Ablauf und Nutzer und lässt
nur Lese-, Anlege- und Aufgaben-Tools zu.

Eine Anlage zählt nur, wenn im Verlauf ein Anlege-Aufruf wirklich erfolgreich war. Meldet die
KI „angelegt“ ohne einen solchen Aufruf, gilt das Ergebnis als unklar – dann wie bisher eine
Aufgabe, statt eine Erledigung zu behaupten.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field

import anthropic

from . import config

logger = logging.getLogger(__name__)

MCP_NAME = "propstack"
ANLEGE_TOOLS = ("create_project", "create_object")
# Folgenachricht: „Link“ und „bitte anlegen“ als zwei Nachrichten (Marek, 24.11.2026: 4 s Abstand)
VORHER_SEKUNDEN = 15 * 60
MAX_PDF_BYTES = 30 * 1024 * 1024
MAX_RUNDEN = 6
TOKEN_GUELTIG_SEKUNDEN = 30 * 60

_LINK = re.compile(r"<(https?://[^|>\s]+)(?:\|[^>]*)?>")
_EXPOSE = re.compile(r"expos", re.IGNORECASE)
ERGEBNISSE = ("angelegt", "teilweise", "existiert", "unklar")


@dataclass
class Datei:
    name: str
    mimetype: str
    url: str
    groesse: int = 0


@dataclass
class Kontext:
    text: str
    autor: str | None
    datum: str
    vorher: list[str] = field(default_factory=list)
    thread: str | None = None
    links: list[str] = field(default_factory=list)
    dateien: list[Datei] = field(default_factory=list)


@dataclass
class Ergebnis:
    ergebnis: str
    objekte: list[dict] = field(default_factory=list)
    offen: list[str] = field(default_factory=list)
    begruendung: str = ""
    aufrufe: list[str] = field(default_factory=list)


# --- Welche Nachrichten ---------------------------------------------------------------

def pdfs(msg: dict) -> list[Datei]:
    out = []
    for f in msg.get("files") or []:
        name = f.get("name") or f.get("title") or "datei.pdf"
        if f.get("mimetype") != "application/pdf" and not name.lower().endswith(".pdf"):
            continue
        url = f.get("url_private_download") or f.get("url_private")
        if url:
            out.append(Datei(name=name, mimetype="application/pdf", url=url, groesse=int(f.get("size") or 0)))
    return out


def ist_anlagefall(msg: dict, typ: str | None) -> bool:
    """„Objekt fehlt / bitte anlegen“ – oder ein Exposé als PDF, auch ohne Text."""
    if typ == "fehlt_in_ps":
        return True
    dateien = pdfs(msg)
    if not dateien:
        return False
    if not (msg.get("text") or "").strip():
        return True
    return bool(_EXPOSE.search(msg.get("text") or "")) or any(_EXPOSE.search(d.name) for d in dateien)


def links(text: str | None) -> list[str]:
    return list(dict.fromkeys(_LINK.findall(text or "")))


def kontext(msg: dict, nachbarn: list[dict], thread: str | None) -> Kontext:
    """Material zu einer Nachricht. nachbarn: die Kanal-Nachrichten des Laufs (Thread-Parents)."""
    ts = float(msg["ts"])
    autor = msg.get("user")
    vorher = [
        n for n in nachbarn
        if n.get("user") == autor and n.get("ts") != msg["ts"]
        and 0 < ts - float(n.get("ts", "0")) <= VORHER_SEKUNDEN
        and n.get("thread_ts", n.get("ts")) == n.get("ts")          # nur Kanal-Nachrichten, keine Antworten
    ]
    vorher.sort(key=lambda n: float(n["ts"]))
    k = Kontext(
        text=(msg.get("text") or "").strip(),
        autor=autor,
        datum=time.strftime("%d.%m.%Y %H:%M", time.gmtime(ts)) + " UTC",
        vorher=[(n.get("text") or "").strip() for n in vorher if (n.get("text") or "").strip()],
        thread=thread,
    )
    for quelle in [*vorher, msg]:
        k.links.extend(links(quelle.get("text")))
        k.dateien.extend(pdfs(quelle))
    k.links = list(dict.fromkeys(k.links))
    return k


# --- Betreuer und Zugang ---------------------------------------------------------------

def betreuer(slack_profil: dict | None, brokers: list[dict]) -> tuple[int, str]:
    """Propstack-Nutzer zum Slack-Autor: erst über die E-Mail, dann über den vollen Namen.
    Ohne Treffer (z. B. Oguzhan, der keinen eigenen Propstack-Nutzer hat): Review-Sitz."""
    profil = slack_profil or {}
    mail = (profil.get("email") or "").strip().lower()
    namen = {(profil.get(k) or "").strip().lower() for k in ("real_name", "real_name_normalized", "display_name")} - {""}
    for b in brokers:
        if mail and (b.get("email") or "").strip().lower() == mail:
            return int(b["id"]), b.get("name") or mail
    for b in brokers:
        if (b.get("name") or "").strip().lower() in namen:
            return int(b["id"]), b["name"]
    return config.BROKER_REVIEW_FALLBACK, config.BROKER_REVIEW_FALLBACK_NAME


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def service_token(secret: str, broker_id: int, slack_ts: str, jetzt: float | None = None) -> str:
    """svc.<payload>.<signatur>: payload = JSON {sub, broker_id, ts, iat, exp}, HMAC-SHA256 über
    „svc.<payload>“. Die Prüfung steht im Connector (Anweisung in objekte_handler/README.md)."""
    jetzt = int(jetzt if jetzt is not None else time.time())
    payload = _b64(json.dumps({
        "sub": "objekte-handler", "broker_id": broker_id, "ts": slack_ts,
        "iat": jetzt, "exp": jetzt + TOKEN_GUELTIG_SEKUNDEN,
    }, separators=(",", ":")).encode())
    signiert = f"svc.{payload}"
    signatur = _b64(hmac.new(secret.encode(), signiert.encode(), hashlib.sha256).digest())
    return f"{signiert}.{signatur}"


# --- Claude mit den Connector-Tools ------------------------------------------------------

SYSTEM = """Du arbeitest für Kromeich & Partner, Makler für Logistikimmobilien. Aus einer Slack-Nachricht im Kanal #ver-objekte legst du ein Objekt in Propstack an – ausschließlich mit den Propstack-Tools. Ihre Beschreibungen enthalten die Regeln des Teams; halte dich genau daran.

0. Rufe als Erstes whoami auf.

1. LESEN: Bestimme aus Exposé, verlinkter Seite (web_fetch) und Text: Adresse(n) mit Ort, Eigentümer bzw. Anbieter, Projektname, die Einheiten mit Hallen-, Büro- und Mezzaninefläche, Verfügbarkeit, Hallenhöhe, Tore. Preise und Provision nur, wenn sie im Material stehen.
2. PRÜFEN, BEVOR DU ANLEGST: Suche mit search_objects nach Straße und Ort, nach Ort und Eigentümer und nach dem Projektnamen; lies Treffer mit get_object bzw. get_project. Gibt es das Objekt mit diesen Einheiten schon, legst du NICHTS an (Ergebnis „existiert“). Fehlen in einem vorhandenen Projekt nur einzelne Einheiten, legst du nur diese an.
3. ANLEGEN: Projekt (bei mehreren Einheiten oder einem Park) mit create_project, je Einheit create_object mit status_id 163673 (Vorbereitung). Kein active, keine öffentlichen Preise (public_price_confirmed), kein allow_duplicate_reason. Nichts erfinden: Was nicht im Material steht, bleibt leer und gehört in „offen“. Eigentümer nur verknüpfen, wenn search_contacts genau einen passenden Kontakt findet. Lies jedes angelegte Objekt mit get_object zurück. Was ein Ergebnis unter service_hinweise meldet, gehört ebenfalls in „offen“.
4. Blockiert die Dublettenprüfung, gibt es das Objekt vermutlich schon: nicht umgehen, sondern prüfen und „existiert“ melden. Ändere keine vorhandenen Objekte.
5. Reicht das Material nicht (kein Ort, keine Fläche, Link nicht lesbar), lege nichts an: Ergebnis „unklar“ mit Begründung.

Antworte am Ende ausschließlich mit diesem JSON:
{"ergebnis": "angelegt" | "teilweise" | "existiert" | "unklar",
 "objekte": [{"id": <Propstack-ID>, "art": "projekt" | "einheit", "titel": "...", "url": "<Feld link aus dem Tool-Ergebnis>"}],
 "offen": ["was fehlt oder ein Mensch prüfen sollte"],
 "begruendung": "1–2 Sätze"}
Unter „objekte“ stehen bei „existiert“ die gefundenen, sonst die angelegten Datensätze."""


def _nachricht(k: Kontext, autor_name: str, permalink: str, pdf_inhalte: list[tuple[Datei, bytes]]) -> list[dict]:
    teile = [
        f"Slack-Nachricht von {autor_name} ({k.datum}): {permalink}",
        f"Text:\n{k.text or '(kein Text, nur Datei)'}",
    ]
    if k.vorher:
        teile.append("Unmittelbar davor vom selben Autor:\n" + "\n---\n".join(k.vorher))
    if k.thread:
        teile.append(f"Thread:\n{k.thread}")
    if k.links:
        teile.append("Links:\n" + "\n".join(k.links))
    if pdf_inhalte:
        teile.append("Anhänge: " + ", ".join(d.name for d, _ in pdf_inhalte))
    inhalt: list[dict] = [
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                         "data": base64.standard_b64encode(daten).decode()},
         "title": datei.name}
        for datei, daten in pdf_inhalte
    ]
    inhalt.append({"type": "text", "text": "\n\n".join(teile)})
    return [{"role": "user", "content": inhalt}]


def _ergebnistext(block) -> str:
    inhalt = getattr(block, "content", None)
    if isinstance(inhalt, str):
        return inhalt
    return "".join(getattr(t, "text", "") for t in inhalt or [])


def whoami_beleg(bloecke: list, slack_ts: str) -> str | None:
    """Das Ergebnis von whoami, falls aufgerufen. Belegt, dass der Connector die Sitzung als
    Service-Sitzung führt: Es muss „objekte-handler“ und den Slack-ts zeigen."""
    ids = {b.id for b in bloecke if getattr(b, "type", None) == "mcp_tool_use" and b.name == "whoami"}
    for b in bloecke:
        if getattr(b, "type", None) == "mcp_tool_result" and getattr(b, "tool_use_id", None) in ids:
            return _ergebnistext(b)
    return None


def _aufrufe(bloecke: list) -> tuple[list[str], set[str]]:
    """Namen aller Connector-Aufrufe und die Anlege-Tools, die ohne Fehler zurückkamen."""
    namen: dict[str, str] = {}
    erfolgreich: set[str] = set()
    for b in bloecke:
        typ = getattr(b, "type", None)
        if typ == "mcp_tool_use":
            namen[b.id] = b.name
        elif typ == "mcp_tool_result":
            name = namen.get(getattr(b, "tool_use_id", ""), "")
            if name in ANLEGE_TOOLS and not getattr(b, "is_error", False):
                erfolgreich.add(name)
    return list(namen.values()), erfolgreich


def _json(text: str) -> dict:
    start, ende = text.find("{"), text.rfind("}")
    if start == -1 or ende <= start:
        raise ValueError(f"keine JSON-Antwort: {text[:120]!r}")
    return json.loads(text[start:ende + 1], strict=False)


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=config.anthropic_api_key(), timeout=600.0)


def lege_an(k: Kontext, broker_id: int, autor_name: str, slack_ts: str, permalink: str,
            pdf_inhalte: list[tuple[Datei, bytes]]) -> Ergebnis:
    secret = config.mcp_service_secret()
    if len(secret) < 32:
        # Der Connector wertet ein kürzeres Secret als „nicht gesetzt“ – dann käme nur 401 zurück.
        raise RuntimeError("PROPSTACK_MCP_SERVICE_SECRET fehlt oder ist kürzer als 32 Zeichen – Anlage über den Connector nicht möglich")
    token = service_token(secret, broker_id, slack_ts)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{token}", flush=True)   # das Token nie im Workflow-Log
    params = dict(
        model=config.ANLAGE_MODELL,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": "medium"},
        betas=[config.MCP_BETA],
        mcp_servers=[{
            "type": "url", "url": config.mcp_url(), "name": MCP_NAME,
            "authorization_token": token,
        }],
        tools=[
            {"type": "mcp_toolset", "mcp_server_name": MCP_NAME},
            {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 5},
        ],
    )
    messages = _nachricht(k, autor_name, permalink, pdf_inhalte)
    bloecke: list = []
    antwort = None
    for _ in range(MAX_RUNDEN):
        antwort = _client().beta.messages.create(messages=messages, **params)
        bloecke.extend(antwort.content)
        if antwort.stop_reason != "pause_turn":
            break
        messages = [*messages, {"role": "assistant", "content": antwort.content}]

    aufrufe, erfolgreich = _aufrufe(bloecke)
    logger.info("Connector-Aufrufe: %s", ", ".join(aufrufe) or "keine")
    beleg = whoami_beleg(bloecke, slack_ts)
    if beleg is None:
        logger.warning("whoami wurde nicht aufgerufen – kein Beleg für die Service-Sitzung")
    elif "objekte-handler" not in beleg or slack_ts not in beleg:
        raise RuntimeError(f"Connector führt die Sitzung nicht als Service-Sitzung (whoami: {beleg[:300]})")
    else:
        logger.info("whoami: %s", " ".join(beleg.split())[:300])
    if antwort is None or antwort.stop_reason in ("refusal", "max_tokens", "pause_turn"):
        grund = getattr(antwort, "stop_reason", "keine Antwort")
        return Ergebnis("unklar", begruendung=f"KI-Lauf ohne Abschluss ({grund})", aufrufe=aufrufe)

    text = "".join(getattr(b, "text", "") for b in antwort.content if getattr(b, "type", None) == "text")
    try:
        daten = _json(text)
    except ValueError as e:
        return Ergebnis("unklar", begruendung=f"Antwort nicht lesbar: {e}", aufrufe=aufrufe)

    ergebnis = daten.get("ergebnis") if daten.get("ergebnis") in ERGEBNISSE else "unklar"
    e = Ergebnis(
        ergebnis=ergebnis,
        objekte=[o for o in daten.get("objekte") or [] if isinstance(o, dict) and o.get("id")],
        offen=[str(o) for o in daten.get("offen") or []],
        begruendung=str(daten.get("begruendung") or ""),
        aufrufe=aufrufe,
    )
    if e.ergebnis in ("angelegt", "teilweise") and not erfolgreich:
        e.begruendung = f"Antwort meldet „{e.ergebnis}“, aber kein Anlege-Aufruf war erfolgreich. {e.begruendung}".strip()
        e.ergebnis = "unklar"
    if e.ergebnis == "existiert" and erfolgreich:
        e.ergebnis = "teilweise"   # angelegt wurde trotzdem etwas – das gehört in die Antwort
    return e


# --- Antwort im Thread -----------------------------------------------------------------

def _zeile(o: dict) -> str:
    titel = o.get("titel") or ""
    art = "Projekt" if o.get("art") == "projekt" else "Einheit"
    url = o.get("url")
    return f"• {art} {o['id']}" + (f" – {titel}" if titel else "") + (f" ({url})" if url else "")


def antwort(e: Ergebnis, betreuer_name: str) -> str:
    objekte = "\n".join(_zeile(o) for o in e.objekte)
    offen = "\n".join(f"• {o}" for o in e.offen)
    if e.ergebnis == "existiert":
        kopf = "Steht schon in Propstack – nichts neu angelegt:"
    elif e.ergebnis == "teilweise":
        kopf = f"Teilweise in Propstack angelegt (Betreuer {betreuer_name}, Status Vorbereitung):"
    else:
        kopf = (f"In Propstack angelegt (Betreuer {betreuer_name}, Status Vorbereitung – bitte ansehen "
                "und auf Vermarktung stellen):")
    text = f"{kopf}\n{objekte}" if objekte else kopf
    if offen:
        text += f"\nOffen:\n{offen}"
    return text
