"""Sichtet die offenen Prüfaufgaben der Slack-Handler und schließt die überflüssigen.

Stand 19.11.2026 (nur gelesen): 609 offene Aufgaben über alle Nutzer, davon 510 am
Review-Sitz 254958. In 91 Tagen kamen dort 213 dazu, 26 wurden erledigt. Drei Gruppen
sind ohne inhaltliche Prüfung überflüssig:

  gegenstandslos   „Newsletter-Vermietung prüfen“, deren Einheiten in Propstack schon
                   vermietet, „Abgeschlossen“ (Status 163676) oder archiviert sind.
  dublette         „Newsletter-Vermietung prüfen“, zu deren Einheit es eine ältere
                   offene Aufgabe derselben Art gibt. Die älteste bleibt offen.
  vollzugsmeldung  Aufgaben des #objekte-Handlers („Objekt fehlt in Propstack“,
                   „Flächenupdate abgleichen“, „Slack #objekte prüfen“), die auf einen
                   Bericht über Erledigtes antworten: „neues Objekt angelegt …“ oder
                   ein Bericht aus einer Claude-Sitzung („Gesendet mit Claude“).

Am 19.11.2026 waren das 40 + 41 + 48 = 129 Aufgaben. Alles andere bleibt unangetastet –
auch Newsletter-Aufgaben ohne verknüpfte Einheit und alle von Hand angelegten Aufgaben.

Liest standardmäßig nur und druckt die Liste. Mit --apply werden die gelisteten
Aufgaben als erledigt markiert (PUT /v1/tasks/:id, done=true). Gelöscht wird nichts.
Zuerst wird EINE Aufgabe geschlossen und zurückgelesen; erscheint sie danach nicht als
erledigt, bricht das Skript ab. Jede geschlossene Aufgabe steht im Protokoll (JSON),
mit --undo <Protokoll> werden genau diese wieder geöffnet.

ACHTUNG: Die Schreibform done=true ist nicht live erprobt (am 19.11.2026 wurde nur
gelesen). Erprobt ist PUT /v1/tasks/:id mit broker_id (Migration vom 02.10.2026). Genau
deshalb die Probe mit einer einzelnen Aufgabe.

Aufruf:   python scripts/pruefaufgaben_aufraeumen.py                 # nur lesen
          python scripts/pruefaufgaben_aufraeumen.py --apply [--limit N] [--nur gegenstandslos|dublette|vollzugsmeldung]
          python scripts/pruefaufgaben_aufraeumen.py --undo pruefaufgaben_geschlossen_<Zeit>.json
Umgebung: PROPSTACK_API_KEY oder PROPSTACK_API_V1 (wird nie ausgegeben).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from objekte_handler.vollzug import vollzugsmeldung  # noqa: E402 – dieselbe Regel wie im Handler

BASE = "https://api.propstack.de/v1"
TITEL_PRAEFIX = "Newsletter-Vermietung prüfen"
OBJEKTE_PRAEFIXE = ("Objekt fehlt in Propstack", "Flächenupdate abgleichen", "Slack #objekte prüfen")
STATUS_ABGESCHLOSSEN = 163676

GEGENSTANDSLOS = "gegenstandslos"
DUBLETTE = "dublette"
VOLLZUG = "vollzugsmeldung"


def _scalar(value):
    return value["value"] if isinstance(value, dict) and "value" in value else value


def _rows(payload) -> list[dict]:
    rows = payload if isinstance(payload, list) else (payload or {}).get("data", [])
    return [r for r in rows if isinstance(r, dict)]


def einheit_abgeschlossen(unit: dict) -> bool:
    """Vermietet, Status „Abgeschlossen“ oder archiviert (Zeile aus GET /v1/units?expand=1)."""
    status = unit.get("property_status")
    status_id = status.get("id") if isinstance(status, dict) else None
    return (
        _scalar(unit.get("rented")) is True
        or _scalar(unit.get("archived")) is True
        or status_id == STATUS_ABGESCHLOSSEN
    )


def offene_newsletter_aufgaben(aufgaben: list[dict]) -> list[dict]:
    """Nur offene Aufgaben dieser Art, älteste zuerst."""
    eigene = [
        a for a in aufgaben
        if not _scalar(a.get("done"))
        and str(_scalar(a.get("title")) or "").startswith(TITEL_PRAEFIX)
        and a.get("activatable_id")
    ]
    return sorted(eigene, key=lambda a: str(a.get("original_created_at") or ""))


def plane(aufgaben: list[dict], einheiten: dict[int, dict]) -> list[dict]:
    """Welche Aufgaben können zu? Gibt je Aufgabe {task_id, titel, angelegt, grund, units, behalten} zurück.

    aufgaben:  Zeilen aus GET /v1/activities?item_type=reminder (alle des Sitzes)
    einheiten: Unit-ID -> Zeile aus GET /v1/units?expand=1. Fehlt eine Einheit dort,
               gilt sie als offen (lieber eine Aufgabe zu viel offen lassen).
    """
    plan: list[dict] = []
    erste_je_einheit: dict[int, int] = {}  # Unit-ID -> Task-ID der ältesten Aufgabe, die offen bleibt
    for aufgabe in offene_newsletter_aufgaben(aufgaben):
        task_id = aufgabe["activatable_id"]
        units = [u for u in (aufgabe.get("property_ids") or []) if isinstance(u, int)]
        if not units:
            continue  # ohne Einheit keine Aussage möglich
        eintrag = {
            "task_id": task_id,
            "titel": _scalar(aufgabe.get("title")),
            "angelegt": str(aufgabe.get("original_created_at") or "")[:10],
            "units": units,
        }
        if all(u in einheiten and einheit_abgeschlossen(einheiten[u]) for u in units):
            plan.append({**eintrag, "grund": GEGENSTANDSLOS, "behalten": None})
            continue
        if all(u in erste_je_einheit for u in units):
            plan.append({**eintrag, "grund": DUBLETTE, "behalten": erste_je_einheit[units[0]]})
            continue
        for u in units:
            erste_je_einheit.setdefault(u, task_id)
    return plan


def offene_objekte_aufgaben(aufgaben: list[dict]) -> list[dict]:
    """Offene Aufgaben des #objekte-Handlers, älteste zuerst."""
    eigene = [
        a for a in aufgaben
        if not _scalar(a.get("done"))
        and str(_scalar(a.get("title")) or "").startswith(OBJEKTE_PRAEFIXE)
        and a.get("activatable_id")
    ]
    return sorted(eigene, key=lambda a: str(a.get("original_created_at") or ""))


def zitierte_nachricht(body: str | None) -> str:
    """Die Slack-Nachricht, auf die eine Handler-Aufgabe antwortet (steht als Zitat im Text)."""
    m = re.search(r"<blockquote>(.*?)</blockquote>", body or "", re.S)
    if not m:
        return ""
    return html.unescape(re.sub(r"<br\s*/?>", "\n", m.group(1))).strip()


def plane_vollzug(aufgaben: list[dict], texte: dict[int, str | None]) -> list[dict]:
    """Aufgaben des #objekte-Handlers, die auf eine Vollzugsmeldung antworten.

    texte: Task-ID -> Text der Aufgabe (GET /v1/tasks/:id, Feld body). Fehlt der Text
    oder enthält er kein Zitat, bleibt die Aufgabe offen."""
    plan: list[dict] = []
    for aufgabe in offene_objekte_aufgaben(aufgaben):
        task_id = aufgabe["activatable_id"]
        grund = vollzugsmeldung(zitierte_nachricht(texte.get(task_id)))
        if not grund:
            continue
        plan.append({
            "task_id": task_id,
            "titel": _scalar(aufgabe.get("title")),
            "angelegt": str(aufgabe.get("original_created_at") or "")[:10],
            "units": [u for u in (aufgabe.get("property_ids") or []) if isinstance(u, int)],
            "grund": VOLLZUG,
            "behalten": None,
            "hinweis": grund,
        })
    return plan


class Propstack:
    def __init__(self, key: str) -> None:
        self.client = httpx.Client(
            timeout=40.0,
            headers={"X-API-KEY": key, "Content-Type": "application/json", "Accept": "application/json"},
        )

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        response = None
        for attempt in range(4):
            response = self.client.request(method, f"{BASE}{path}", **kw)
            if response.status_code == 429 or (response.status_code >= 500 and method == "GET"):
                time.sleep(2 ** attempt)
                continue
            break
        response.raise_for_status()
        return response

    def nutzer(self) -> list[int]:
        return [b["id"] for b in _rows(self._request("GET", "/brokers").json()) if isinstance(b.get("id"), int)]

    def aufgaben(self) -> list[dict]:
        """Alle Aufgaben aller Nutzer: Review-Aufgaben liegen nicht nur am Review-Sitz,
        Status-Meldungen gehen an den Betreuer der Einheit."""
        out: list[dict] = []
        for broker_id in self.nutzer():
            page = 1
            while True:
                batch = _rows(self._request("GET", "/activities", params={
                    "item_type": "reminder", "broker_id": broker_id,
                    "sort_by": "updated_at", "order": "desc", "per": 200, "page": page,
                }).json())
                out.extend(batch)
                if len(batch) < 200:
                    break
                page += 1
                time.sleep(0.5)
        return out

    def texte(self, task_ids: list[int]) -> dict[int, str | None]:
        """GET /tasks/:id – die Liste der Aktivitäten liefert den Text nicht mit."""
        out: dict[int, str | None] = {}
        for task_id in task_ids:
            try:
                data = self._request("GET", f"/tasks/{task_id}").json()
            except httpx.HTTPError:
                out[task_id] = None
                continue
            task = data.get("task") if isinstance(data.get("task"), dict) else data
            out[task_id] = _scalar(task.get("body"))
            time.sleep(0.25)
        return out

    def einheiten(self, unit_ids: list[int]) -> dict[int, dict]:
        out: dict[int, dict] = {}
        for start in range(0, len(unit_ids), 50):
            params = [("expand", 1), ("per", 100), ("archived", -1)]
            params += [("property_ids[]", u) for u in unit_ids[start:start + 50]]
            for unit in _rows(self._request("GET", "/units", params=params).json()):
                out[unit["id"]] = unit
            time.sleep(0.5)
        return out

    def ist_erledigt(self, task_id: int) -> bool | None:
        """Steht die Aufgabe jetzt als erledigt in der Liste des Sitzes? None = nicht gefunden."""
        for aufgabe in self.aufgaben():
            if aufgabe.get("activatable_id") == task_id:
                return bool(_scalar(aufgabe.get("done")))
        return None

    def setze_erledigt(self, task_id: int, erledigt: bool) -> None:
        self._request("PUT", f"/tasks/{task_id}", json={"task": {"done": erledigt}})


def _drucke(plan: list[dict]) -> None:
    for grund, ueberschrift in ((GEGENSTANDSLOS, "Gegenstandslos (Einheit schon vermietet/abgeschlossen)"),
                                (DUBLETTE, "Dublette (ältere offene Aufgabe zur selben Einheit bleibt)"),
                                (VOLLZUG, "Antwort auf eine Vollzugsmeldung (#objekte)")):
        zeilen = [e for e in plan if e["grund"] == grund]
        print(f"\n{ueberschrift}: {len(zeilen)}")
        for e in zeilen:
            zusatz = f" – bleibt offen: Task {e['behalten']}" if e["behalten"] else ""
            print(f"  Task {e['task_id']}  {e['angelegt']}  {e['titel']}  (Units {e['units']}){zusatz}")


def _undo(ps: Propstack, datei: str) -> int:
    protokoll = json.loads(Path(datei).read_text(encoding="utf-8"))
    for task_id in protokoll["geschlossen"]:
        ps.setze_erledigt(task_id, False)
        print(f"wieder geöffnet: Task {task_id}")
        time.sleep(0.4)
    print(f"{len(protokoll['geschlossen'])} Aufgaben wieder geöffnet.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="gelistete Aufgaben als erledigt markieren (schreibt!)")
    ap.add_argument("--limit", type=int, help="höchstens so viele Aufgaben schließen")
    ap.add_argument("--nur", choices=[GEGENSTANDSLOS, DUBLETTE, VOLLZUG], help="nur diese Gruppe")
    ap.add_argument("--undo", metavar="PROTOKOLL", help="die in diesem Protokoll genannten Aufgaben wieder öffnen")
    args = ap.parse_args()

    key = os.environ.get("PROPSTACK_API_KEY") or os.environ.get("PROPSTACK_API_V1")
    if not key:
        print("PROPSTACK_API_KEY bzw. PROPSTACK_API_V1 fehlt.", file=sys.stderr)
        return 2
    ps = Propstack(key)
    if args.undo:
        return _undo(ps, args.undo)

    aufgaben = ps.aufgaben()
    alle_offenen = [a for a in aufgaben if not _scalar(a.get("done"))]
    offene = offene_newsletter_aufgaben(aufgaben)
    objekte = offene_objekte_aufgaben(aufgaben)
    unit_ids = sorted({u for a in offene for u in (a.get("property_ids") or []) if isinstance(u, int)})
    plan = plane(aufgaben, ps.einheiten(unit_ids))
    plan += plane_vollzug(aufgaben, ps.texte([a["activatable_id"] for a in objekte]))
    if args.nur:
        plan = [e for e in plan if e["grund"] == args.nur]

    print(f"{len(aufgaben)} Aufgaben über alle Nutzer, {len(alle_offenen)} offen – davon {len(offene)} "
          f"„{TITEL_PRAEFIX}“ und {len(objekte)} aus #objekte.")
    _drucke(plan)
    print(f"\nKönnen zu: {len(plan)} von {len(alle_offenen)} offenen. Offen bleiben {len(alle_offenen) - len(plan)}.")

    if not args.apply:
        print("Nur gelesen. Zum Schließen: --apply (vorher die Liste ansehen).")
        return 0
    if args.limit:
        plan = plan[:args.limit]
    if not plan:
        return 0

    protokoll = Path(f"pruefaufgaben_geschlossen_{datetime.now():%Y%m%d-%H%M%S}.json")
    geschlossen: list[int] = []

    def sichere() -> None:
        protokoll.write_text(json.dumps({"geschlossen": geschlossen}, indent=1), encoding="utf-8")

    probe = plan[0]
    ps.setze_erledigt(probe["task_id"], True)
    geschlossen.append(probe["task_id"])
    sichere()
    time.sleep(1.5)
    stand = ps.ist_erledigt(probe["task_id"])
    if stand is not True:
        print(f"ABBRUCH: Probe Task {probe['task_id']} erscheint nach dem Schreiben nicht als erledigt "
              f"(gelesen: {stand}). Nur diese eine Aufgabe wurde angefasst. Protokoll: {protokoll}", file=sys.stderr)
        return 1
    print(f"Probe ok: Task {probe['task_id']} ist erledigt.")

    fehler: list[tuple[int, str]] = []
    for eintrag in plan[1:]:
        try:
            ps.setze_erledigt(eintrag["task_id"], True)
            geschlossen.append(eintrag["task_id"])
            sichere()
        except httpx.HTTPError as e:
            fehler.append((eintrag["task_id"], str(e)))
        time.sleep(0.4)

    print(f"Geschlossen: {len(geschlossen)} von {len(plan)}. Fehler: {len(fehler)} {fehler[:5]}")
    print(f"Protokoll: {protokoll}  (zurücknehmen mit --undo {protokoll})")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
