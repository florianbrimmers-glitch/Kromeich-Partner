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
from html.parser import HTMLParser

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

MAX_MAIL_ZEICHEN = 30_000

_LINK = re.compile(r"<(https?://[^|>\s]+)(?:\|[^>]*)?>")
_EXPOSE = re.compile(r"expos", re.IGNORECASE)
# „bitte anlegen“ als ganze Nachricht (Marek 24.11.2026, Denise 04.10.2026) – mit oder ohne
# „Objekt“, „in Propstack“, Erwähnung davor. Alles, was mehr sagt („… und an Baaske senden“,
# „Research-Aufgaben anlegen“), entscheidet weiter die KI.
_ERWAEHNUNG = re.compile(r"<[@!#][^>]*>|(?<!\w)@[\w.äöüß-]+:?", re.IGNORECASE)
_AUFTRAG = re.compile(
    r"^(?:bitte\s+)?(?:(?:das|dieses|die|diese)\s+)?(?:objekte?|projekte?|fl(?:ä|ae)chen?|halle)?\s*"
    r"(?:(?:in|im)\s+(?:ps|propstack)\s+)?anlegen(?:\s*,?\s*bitte)?[\s.!:)-]*$",
    re.IGNORECASE,
)
ERGEBNISSE = ("angelegt", "teilweise", "existiert", "unklar")


@dataclass
class Datei:
    name: str
    mimetype: str
    url: str
    groesse: int = 0


@dataclass
class Mail:
    """Eine in den Kanal weitergeleitete E-Mail (Slack-Datei vom Typ „email“). Denise leitet
    Angebote so weiter, mit „bitte anlegen“ als Text (04.10.2026: CTPark Recklinghausen, JLL,
    BGO)."""
    betreff: str
    von: str
    text: str
    url: str | None = None          # HTML-Fassung, wenn Slack den Text nur gekürzt mitliefert
    vollstaendig: bool = True


@dataclass
class Kontext:
    text: str
    autor: str | None
    datum: str
    vorher: list[str] = field(default_factory=list)
    thread: str | None = None
    links: list[str] = field(default_factory=list)
    dateien: list[Datei] = field(default_factory=list)
    mails: list[Mail] = field(default_factory=list)
    nicht_lesbar: list[str] = field(default_factory=list)


@dataclass
class Ergebnis:
    ergebnis: str
    objekte: list[dict] = field(default_factory=list)
    offen: list[str] = field(default_factory=list)
    begruendung: str = ""
    aufrufe: list[str] = field(default_factory=list)
    fehler: list[str] = field(default_factory=list)      # technisch gescheitert – macht den Lauf rot


# --- Welche Nachrichten ---------------------------------------------------------------

def _ist_mail(f: dict) -> bool:
    return f.get("filetype") == "email" or f.get("mode") == "email"


def _ist_pdf(mimetype: str | None, name: str) -> bool:
    return mimetype == "application/pdf" or name.lower().endswith(".pdf")


def pdfs(msg: dict, mit_mail: bool = True) -> list[Datei]:
    """PDFs der Nachricht – mit mit_mail auch die, die an einer weitergeleiteten E-Mail hängen.
    Eine E-Mail ohne Text ist meist ein Eigentümer-Newsletter, kein Exposé zum Anlegen."""
    out = []
    for f in msg.get("files") or []:
        if _ist_mail(f):
            for a in (f.get("attachments") or []) if mit_mail else []:
                name = a.get("filename") or a.get("name") or "anhang.pdf"
                if _ist_pdf(a.get("mimetype"), name) and a.get("url"):
                    out.append(Datei(name=name, mimetype="application/pdf", url=a["url"], groesse=int(a.get("size") or 0)))
            continue
        name = f.get("name") or f.get("title") or "datei.pdf"
        if not _ist_pdf(f.get("mimetype"), name):
            continue
        url = f.get("url_private_download") or f.get("url_private")
        if url:
            out.append(Datei(name=name, mimetype="application/pdf", url=url, groesse=int(f.get("size") or 0)))
    return out


_SPRACHE = re.compile(r"[\s_\-(]+(de|deu|ger|deutsch|en|eng|engl|english|englisch)\)?$", re.IGNORECASE)
_DEUTSCH = ("de", "deu", "ger", "deutsch")


def ohne_doppelte_sprache(dateien: list[Datei]) -> list[Datei]:
    """Dasselbe Exposé als EN und DE (CTPark Recklinghausen, 04.10.2026: je 5 MB) nur einmal
    mitgeben, die deutsche Fassung – sonst zahlt die Anlage doppelt."""
    gruppen: dict[str, list[Datei]] = {}
    for d in dateien:
        stamm = re.sub(r"\.pdf$", "", d.name.strip(), flags=re.IGNORECASE)
        gruppen.setdefault(_SPRACHE.sub("", stamm).strip().lower(), []).append(d)
    out = []
    for gruppe in gruppen.values():
        if len(gruppe) == 1:
            out.append(gruppe[0])
            continue
        def deutsch(d: Datei) -> bool:
            m = _SPRACHE.search(re.sub(r"\.pdf$", "", d.name.strip(), flags=re.IGNORECASE))
            return bool(m) and m.group(1).lower() in _DEUTSCH
        out.append(next((d for d in gruppe if deutsch(d)), gruppe[0]))
    return out


def mails(msg: dict) -> list[Mail]:
    out = []
    for f in msg.get("files") or []:
        if not _ist_mail(f):
            continue
        von = ", ".join(a.get("name") or a.get("address") or "" for a in f.get("from") or [] if isinstance(a, dict))
        text = f.get("plain_text") or ""
        out.append(Mail(
            betreff=(f.get("subject") or f.get("title") or f.get("name") or "").strip(),
            von=von,
            text=text,
            url=f.get("url_private_download") or f.get("url_private"),
            vollstaendig=bool(text) and not f.get("has_more"),
        ))
    return out


class _NurText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.teile: list[str] = []
        self._weg = 0

    _BLOCK = ("br", "p", "div", "tr", "li", "h1", "h2", "h3", "table")

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "head"):
            self._weg += 1
        elif tag in self._BLOCK:
            self.teile.append("\n")
        elif tag in ("td", "th"):
            self.teile.append(" ")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head") and self._weg:
            self._weg -= 1
        elif tag in self._BLOCK:
            self.teile.append("\n")

    def handle_data(self, data):
        if not self._weg:
            self.teile.append(data)


def html_zu_text(html: str) -> str:
    p = _NurText()
    p.feed(html)
    zeilen = (" ".join(z.split()) for z in "".join(p.teile).splitlines())
    return "\n".join(z for z in zeilen if z)


def ist_auftrag(text: str | None) -> bool:
    """Die ganze Nachricht ist ein „bitte anlegen“ – das Objekt steht im Material daneben."""
    rest = " ".join(_ERWAEHNUNG.sub(" ", text or "").split())
    return bool(_AUFTRAG.match(rest))


def hat_material(msg: dict) -> bool:
    return bool(links(msg.get("text")) or pdfs(msg) or mails(msg))


def ist_thread_antwort(msg: dict) -> bool:
    return msg.get("thread_ts", msg.get("ts")) != msg.get("ts")


def vorher(msg: dict, nachbarn: list[dict]) -> list[dict]:
    """Die Kanal-Nachrichten desselben Autors direkt davor (höchstens 15 Minuten): „Link“ und
    „bitte anlegen“ kommen oft getrennt. Schluss bei einer Nachricht von jemand anderem und bei
    einem früheren „bitte anlegen“ – das hatte sein eigenes Material (Marek 24.11.2026: Unna
    um 10:47, Ense-Höingen um 10:49). Für eine Thread-Antwort ist der Thread der Kontext."""
    if ist_thread_antwort(msg):
        return []
    ts = float(msg["ts"])
    frueher = sorted(
        (n for n in nachbarn if not ist_thread_antwort(n) and float(n.get("ts") or 0) < ts),
        key=lambda n: float(n["ts"]), reverse=True,
    )
    out = []
    for n in frueher:
        if ts - float(n["ts"]) > VORHER_SEKUNDEN or n.get("user") != msg.get("user") or ist_auftrag(n.get("text")):
            break
        out.append(n)
    return out[::-1]


def auftrag_ohne_ki(msg: dict, nachbarn: list[dict]) -> bool:
    """„bitte anlegen“ mit Material in der Nachricht selbst oder direkt davor: anlegen, ohne die
    KI erst raten zu lassen. Am 24.11. hielt sie „bitte anlegen“ für „Objekt fehlt“, am 26.11.
    dieselbe Nachricht für „kein Objektbezug“ – sie bekam den Link davor nicht zu sehen."""
    if not ist_auftrag(msg.get("text")):
        return False
    return hat_material(msg) or any(hat_material(n) for n in vorher(msg, nachbarn))


def ist_anlagefall(msg: dict, typ: str | None) -> bool:
    """„Objekt fehlt / bitte anlegen“ – oder ein Exposé als PDF, auch ohne Text."""
    if typ == "fehlt_in_ps":
        return True
    dateien = pdfs(msg, mit_mail=False)
    if not dateien:
        return False
    if not (msg.get("text") or "").strip():
        return True
    return bool(_EXPOSE.search(msg.get("text") or "")) or any(_EXPOSE.search(d.name) for d in dateien)


def links(text: str | None) -> list[str]:
    return list(dict.fromkeys(_LINK.findall(text or "")))


def kontext(msg: dict, nachbarn: list[dict], thread: str | None) -> Kontext:
    """Material zu einer Nachricht. nachbarn: die Kanal-Nachrichten des Laufs (Thread-Parents)."""
    davor = vorher(msg, nachbarn)
    k = Kontext(
        text=(msg.get("text") or "").strip(),
        autor=msg.get("user"),
        datum=time.strftime("%d.%m.%Y %H:%M", time.gmtime(float(msg["ts"]))) + " UTC",
        vorher=[(n.get("text") or "").strip() for n in davor if (n.get("text") or "").strip()],
        thread=thread,
    )
    for quelle in [*davor, msg]:
        k.links.extend(links(quelle.get("text")))
        k.dateien.extend(pdfs(quelle))
        k.mails.extend(mails(quelle))
    k.links = list(dict.fromkeys(k.links))
    k.dateien = ohne_doppelte_sprache(k.dateien)
    return k


# --- Betreuer und Zugang ---------------------------------------------------------------

def betreuer(slack_profil: dict | None, brokers: list[dict], slack_user: str | None = None) -> tuple[int, str]:
    """Propstack-Nutzer zum Slack-Autor: erst über die feste Zuordnung (config.SLACK_ZU_PROPSTACK),
    dann über die E-Mail, dann über den vollen Namen. Ohne Treffer: Review-Sitz."""
    fest = config.SLACK_ZU_PROPSTACK.get(slack_user or "")
    if fest:
        name = next((b.get("name") for b in brokers if int(b.get("id") or 0) == fest), None)
        return fest, name or str(fest)
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

1. LESEN: Bestimme aus Exposé, weitergeleiteter E-Mail, verlinkter Seite (web_fetch) und Text: Adresse(n) mit Ort, Eigentümer bzw. Anbieter, Projektname, die Einheiten mit Hallen-, Büro- und Mezzaninefläche, Verfügbarkeit, Hallenhöhe, Tore. Preise und Provision nur, wenn sie im Material stehen.
2. PRÜFEN, BEVOR DU ANLEGST: Suche mit search_objects nach Straße und Ort, nach Ort und Eigentümer und nach dem Projektnamen; lies Treffer mit get_object bzw. get_project. Gibt es das Objekt mit diesen Einheiten schon, legst du NICHTS an (Ergebnis „existiert“). Fehlen in einem vorhandenen Projekt nur einzelne Einheiten, legst du nur diese an.
3. ANLEGEN: Projekt (bei mehreren Einheiten oder einem Park) mit create_project, je Einheit create_object mit status_id 163673 (Vorbereitung). Kein active, keine öffentlichen Preise (public_price_confirmed), kein allow_duplicate_reason. Nichts erfinden: Was nicht im Material steht, bleibt leer und gehört in „offen“. Eigentümer nur verknüpfen, wenn search_contacts genau einen passenden Kontakt findet. Lies jedes angelegte Objekt mit get_object zurück. Was ein Ergebnis unter service_hinweise meldet, gehört ebenfalls in „offen“.
4. Blockiert die Dublettenprüfung, gibt es das Objekt vermutlich schon: nicht umgehen, sondern prüfen und „existiert“ melden. Ändere keine vorhandenen Objekte.
5. Reicht das Material nicht (kein Ort, keine Fläche, Link nicht lesbar), lege nichts an: Ergebnis „unklar“ mit Begründung.

Antworte am Ende ausschließlich mit diesem JSON:
{"ergebnis": "angelegt" | "teilweise" | "existiert" | "unklar",
 "objekte": [{"id": <Propstack-ID>, "art": "projekt" | "einheit", "titel": "...", "url": "<Feld link aus dem Tool-Ergebnis>"}],
 "offen": ["was fehlt oder ein Mensch prüfen sollte"],
 "fehler": ["was am Ende nicht erledigt ist, weil ein Tool scheiterte (Überlastung, Fehlermeldung, nicht übernommen) – nicht: was im Material fehlt, und nicht die Dublettenprüfung"],
 "begruendung": "1–2 Sätze"}
Unter „objekte“ stehen bei „existiert“ die gefundenen, sonst die angelegten Datensätze."""


def _nachricht(k: Kontext, autor_name: str, permalink: str, pdf_inhalte: list[tuple[Datei, bytes]]) -> list[dict]:
    teile = [
        f"Slack-Nachricht von {autor_name} ({k.datum}): {permalink}",
        f"Text:\n{k.text or '(kein Text, nur Datei)'}",
    ]
    if k.vorher:
        teile.append("Unmittelbar davor vom selben Autor (meist das Objekt zum Auftrag):\n" + "\n---\n".join(k.vorher))
    if k.thread:
        teile.append(f"Thread:\n{k.thread}")
    if k.links:
        teile.append("Links:\n" + "\n".join(k.links))
    for m in k.mails:
        kopf = f"Weitergeleitete E-Mail – Betreff: {m.betreff}" + (f" – Von: {m.von}" if m.von else "")
        teile.append(f"{kopf}\n{m.text[:MAX_MAIL_ZEICHEN] or '(Text nicht lesbar)'}")
    if pdf_inhalte:
        teile.append("Anhänge: " + ", ".join(d.name for d, _ in pdf_inhalte))
    if k.nicht_lesbar:
        teile.append("Nicht lesbar (gehört in „offen“): " + ", ".join(k.nicht_lesbar))
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
    verbrauch = {"input_tokens": 0, "output_tokens": 0}
    for _ in range(MAX_RUNDEN):
        antwort = _client().beta.messages.create(messages=messages, **params)
        bloecke.extend(antwort.content)
        for feld in verbrauch:
            verbrauch[feld] += int(getattr(getattr(antwort, "usage", None), feld, 0) or 0)
        if antwort.stop_reason != "pause_turn":
            break
        messages = [*messages, {"role": "assistant", "content": antwort.content}]

    aufrufe, erfolgreich = _aufrufe(bloecke)
    logger.info("Connector-Aufrufe: %s", ", ".join(aufrufe) or "keine")
    logger.info("Verbrauch: %d Eingabe-, %d Ausgabe-Token", verbrauch["input_tokens"], verbrauch["output_tokens"])
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
        fehler=[str(f) for f in daten.get("fehler") or []],
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
