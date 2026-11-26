"""Sichtet die offenen Prüfaufgaben der Slack-Handler und schließt die überflüssigen.

Stand 19.11.2026 (nur gelesen): 609 offene Aufgaben über alle Nutzer, davon 510 am
Review-Sitz 254958. In 91 Tagen kamen dort 213 dazu, 26 wurden erledigt. Drei Gruppen
sind ohne inhaltliche Prüfung überflüssig:

  gegenstandslos   „Newsletter-Vermietung prüfen“, deren Einheiten in Propstack schon
                   vermietet, „Abgeschlossen“ (Status 163676) oder archiviert sind.
  dublette         „Newsletter-Vermietung prüfen“, zu deren Einheit es eine ältere
                   offene Aufgabe mit derselben Meldung gibt. Die älteste bleibt offen;
                   eine Aufgabe mit anderem Objektnamen zur selben Einheit auch.
  vollzugsmeldung  Aufgaben des #objekte-Handlers („Objekt fehlt in Propstack“,
                   „Flächenupdate abgleichen“, „Slack #objekte prüfen“), die auf einen
                   Bericht über Erledigtes antworten: „neues Objekt angelegt …“ oder
                   ein Bericht aus einer Claude-Sitzung („Gesendet mit Claude“).

Am 19.11.2026 waren das 40 + 41 + 47 = 128 Aufgaben. Alles andere bleibt unangetastet –
auch Newsletter-Aufgaben ohne verknüpfte Einheit und alle von Hand angelegten Aufgaben.

Liest standardmäßig nur und druckt die Liste. Mit --apply werden die gelisteten
Aufgaben als erledigt markiert (PUT /v1/tasks/:id, done=true). Gelöscht wird nichts.
Zuerst wird EINE Aufgabe geschlossen und zurückgelesen; erscheint sie danach nicht als
erledigt, bricht das Skript ab. Jede geschlossene Aufgabe steht im Protokoll (JSON),
mit --undo <Protokoll> --apply werden genau diese wieder geöffnet (ohne --apply nur gezeigt).

Die Schreibform ist live erprobt: Am 19.11.2026 wurden damit 34 Dubletten geschlossen
(Protokoll: scripts/pruefaufgaben_geschlossen_2026-11-19.json). Die Probe mit einer einzelnen
Aufgabe bleibt trotzdem – sie kostet nichts und fängt eine geänderte Schnittstelle ab.

Zweiter Weg, --urteile: Am 19.11.2026 wurden alle 129 offenen Newsletter-Aufgaben einzeln
gelesen (scripts/radar_vorpruefung_2026-11-19.json). Geschlossen werden dann genau die dort
genannten Aufgaben der gewählten Gruppen – nicht nach Regel, sondern nach Urteil. Jede bekommt
das Urteil als erste Zeile in den Text („Vorprüfung 19.11.2026: …“), damit am Objekt steht,
warum sie zu ist; --undo nimmt die Zeile wieder heraus. Für die Gruppe „erledigt“ wird vor dem
Schließen noch einmal gelesen, ob die genannten Einheiten wirklich geschlossen sind.

Am 20.11.2026 mit Freigabe ausgeführt: 96 Aufgaben (erledigt, betrifft uns nicht, schwache Spur),
danach die „eintragen“-Aufgaben, nachdem die Vermietungen über den Connector eingetragen waren.
Die zweite Datei scripts/radar_nachpruefung_2026-11-20.json hält fest, was die Nachprüfung der
„klären“-Vorgänge an öffentlichen Quellen ergeben hat (Florian: „Nicht nachfragen – entweder
wissen oder nicht“). Die Schreibform mit Text ist damit live erprobt.

Am 21.11.2026 mit Freigabe: 46 Antworten auf Vollzugsmeldungen, jetzt mit Vermerk („Aufgeräumt …“) –
--nur vollzugsmeldung --ausser 158526533 (die P3-Aufgabe blieb auf Ansage offen). Protokoll:
scripts/pruefaufgaben_geschlossen_2026-11-21.json.

Dritter Weg, --einzeln: genau die Aufgaben einer Liste (Task-ID und Grund), z. B. auf Ansage nach
einer Einzelprüfung. Nur, was heute noch offen ist; jede bekommt „Aufgeräumt <Datum>: <Grund>“ als
erste Zeile. Am 26.11.2026 mit Freigabe (Florian: „ja, schließen“): vier „Objekt fehlt“-Aufgaben vom
25.11., deren Objekte in Propstack stehen – scripts/pruefaufgaben_einzeln_2026-11-26.json.

Aufruf:   python scripts/pruefaufgaben_aufraeumen.py                 # nur lesen
          python scripts/pruefaufgaben_aufraeumen.py --urteile scripts/radar_vorpruefung_2026-11-19.json [--gruppen erledigt,fremd] [--apply]
          python scripts/pruefaufgaben_aufraeumen.py --apply [--limit N] [--nur gegenstandslos|dublette|vollzugsmeldung] [--ausser ID,ID]
          python scripts/pruefaufgaben_aufraeumen.py --einzeln scripts/pruefaufgaben_einzeln_2026-11-26.json [--apply]
          python scripts/pruefaufgaben_aufraeumen.py --undo pruefaufgaben_geschlossen_<Zeit>.json --apply
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


def _je_aufgabe_einmal(aufgaben: list[dict]) -> list[dict]:
    """Jede Aufgabe nur einmal. Die Liste wird seitenweise gelesen, während Leute arbeiten –
    eine Zeile kann zweimal kommen und gälte sonst als Dublette ihrer selbst."""
    gesehen: dict[int, dict] = {}
    for a in aufgaben:
        task_id = a.get("activatable_id")
        if task_id and task_id not in gesehen:
            gesehen[task_id] = a
    return list(gesehen.values())


def offene_newsletter_aufgaben(aufgaben: list[dict]) -> list[dict]:
    """Nur offene Aufgaben dieser Art, älteste zuerst."""
    eigene = [
        a for a in _je_aufgabe_einmal(aufgaben)
        if not _scalar(a.get("done"))
        and str(_scalar(a.get("title")) or "").startswith(TITEL_PRAEFIX)
    ]
    return sorted(eigene, key=lambda a: str(a.get("original_created_at") or ""))


# Wörter, die in fast jedem Titel stehen und nichts über das Objekt sagen
_ALLGEMEIN = {
    "park", "logistik", "logistikpark", "logistikzentrum", "logistikhalle", "logistikneubau", "industrial",
    "neubau", "neubaufläche", "gmbh", "real", "estate", "deutschland", "germany", "unternehmerpark",
    "gewerbepark", "projekt", "halle", "brownfield", "der", "die", "das", "und", "von", "bei", "des", "the",
}


def _namenswoerter(titel: str | None) -> set[str]:
    name = str(titel or "").split(":", 1)[-1].lower()
    return {w for w in re.findall(r"[a-zäöüß0-9]{3,}", name)} - _ALLGEMEIN


def gleiche_meldung(titel_a: str | None, titel_b: str | None) -> bool:
    """Meinen zwei Aufgaben zur selben Einheit dieselbe Meldung? Der Titel nennt das Objekt
    so, wie der Radar es nannte: „Garbe“ und „Garbe Industrial“ sind dasselbe, „Ixocon“ und
    „Prologis Park Hamburg-Steinwerder“ nicht – dann hat die KI zwei verschiedene Meldungen
    derselben Einheit zugeordnet, und genau das soll ein Mensch sehen."""
    a, b = _namenswoerter(titel_a), _namenswoerter(titel_b)
    if a & b:
        return True
    kompakt = [re.sub(r"[^a-zäöüß0-9]", "", str(t or "").split(":", 1)[-1].lower()) for t in (titel_a, titel_b)]
    return bool(kompakt[0]) and bool(kompakt[1]) and (kompakt[0] in kompakt[1] or kompakt[1] in kompakt[0])


def plane(aufgaben: list[dict], einheiten: dict[int, dict]) -> list[dict]:
    """Welche Aufgaben können zu? Gibt je Aufgabe {task_id, titel, angelegt, grund, units, behalten} zurück.

    aufgaben:  Zeilen aus GET /v1/activities?item_type=reminder (alle Nutzer)
    einheiten: Unit-ID -> Zeile aus GET /v1/units?expand=1. Fehlt eine Einheit dort,
               gilt sie als offen (lieber eine Aufgabe zu viel offen lassen).

    Dublette ist eine Aufgabe nur, wenn zu JEDER ihrer Einheiten eine ältere offene Aufgabe
    mit derselben Meldung bleibt (gleiche_meldung). Eine zweite Aufgabe zur selben Einheit
    mit anderem Objektnamen bleibt offen.
    """
    plan: list[dict] = []
    bleibt_je_einheit: dict[int, list[tuple[int, str]]] = {}  # Unit-ID -> [(Task-ID, Titel)], die offen bleiben
    for aufgabe in offene_newsletter_aufgaben(aufgaben):
        task_id = aufgabe["activatable_id"]
        titel = str(_scalar(aufgabe.get("title")) or "")
        units = [u for u in (aufgabe.get("property_ids") or []) if isinstance(u, int)]
        if not units:
            continue  # ohne Einheit keine Aussage möglich
        eintrag = {
            "task_id": task_id,
            "titel": titel,
            "angelegt": str(aufgabe.get("original_created_at") or "")[:10],
            "units": units,
        }
        if all(u in einheiten and einheit_abgeschlossen(einheiten[u]) for u in units):
            plan.append({**eintrag, "grund": GEGENSTANDSLOS, "behalten": None})
            continue
        gleiche = [
            next((tid for tid, t in bleibt_je_einheit.get(u, []) if tid != task_id and gleiche_meldung(titel, t)), None)
            for u in units
        ]
        if all(gleiche):
            plan.append({**eintrag, "grund": DUBLETTE, "behalten": gleiche[0]})
            continue
        for u in units:
            bleibt_je_einheit.setdefault(u, []).append((task_id, titel))
    return plan


def offene_objekte_aufgaben(aufgaben: list[dict]) -> list[dict]:
    """Offene Aufgaben des #objekte-Handlers, älteste zuerst."""
    eigene = [
        a for a in _je_aufgabe_einmal(aufgaben)
        if not _scalar(a.get("done"))
        and str(_scalar(a.get("title")) or "").startswith(OBJEKTE_PRAEFIXE)
    ]
    return sorted(eigene, key=lambda a: str(a.get("original_created_at") or ""))


def zitierte_nachricht(body: str | None) -> str:
    """Die Slack-Nachricht, auf die eine Handler-Aufgabe antwortet (steht als Zitat im Text)."""
    m = re.search(r"<blockquote>(.*?)</blockquote>", body or "", re.S)
    if not m:
        return ""
    return html.unescape(re.sub(r"<br\s*/?>", "\n", m.group(1))).strip()


def plane_vollzug(aufgaben: list[dict], texte: dict[int, str | None], stand: str | None = None) -> list[dict]:
    """Aufgaben des #objekte-Handlers, die auf eine Vollzugsmeldung antworten.

    texte: Task-ID -> Text der Aufgabe (GET /v1/tasks/:id, Feld body). Fehlt der Text
    oder enthält er kein Zitat, bleibt die Aufgabe offen.
    stand: Datum für den Vermerk. Mit stand bekommt jede Aufgabe eine erste Zeile, warum sie
    zu ist (seit 21.11.2026; die 34 Dubletten vom 19.11. gingen noch ohne Vermerk zu)."""
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
            **({"vermerk": vollzug_vermerk(stand)} if stand else {}),
        })
    return plan


def vollzug_vermerk(stand: str) -> str:
    return html.escape(f"Aufgeräumt {stand}: Antwort auf eine Vollzugsmeldung – kein Auftrag, "
                       "das Gemeldete ist in Propstack schon erledigt.", quote=False) + VERMERK_ENDE


def plane_einzeln(aufgaben: list[dict], liste: list[dict], stand: str) -> tuple[list[dict], list[str]]:
    """Schließplan aus einer Liste [{task_id, grund}]: nur Aufgaben, die heute noch offen sind.
    Was nicht (mehr) offen oder unbekannt ist, steht in den Hinweisen statt im Plan."""
    offen = {a["activatable_id"]: a for a in _je_aufgabe_einmal(aufgaben) if not _scalar(a.get("done"))}
    plan: list[dict] = []
    hinweise: list[str] = []
    for eintrag in liste:
        task_id = int(eintrag["task_id"])
        aufgabe = offen.get(task_id)
        if aufgabe is None:
            hinweise.append(f"Task {task_id} ist nicht (mehr) offen – ausgelassen")
            continue
        plan.append({
            "task_id": task_id,
            "titel": _scalar(aufgabe.get("title")),
            "angelegt": str(aufgabe.get("original_created_at") or "")[:10],
            "units": [u for u in (aufgabe.get("property_ids") or []) if isinstance(u, int)],
            "grund": "einzeln",
            "behalten": None,
            "hinweis": eintrag["grund"],
            "vermerk": html.escape(f"Aufgeräumt {stand}: {eintrag['grund']}", quote=False) + VERMERK_ENDE,
        })
    return plan, hinweise


URTEIL_WORT = {
    "erledigt": "erledigt – die gemeinte Einheit ist in Propstack geschlossen",
    "eintragen": "eingetragen – die Einheit steht jetzt auf vermietet und Abgeschlossen",
    "fremd": "betrifft uns nicht",
    "teil": "Teilvermietung – am Objekt vermerkt, Status unverändert",
    "schwach": "schwache Spur, nicht weiter verfolgt",
    "unbestimmt": "nicht bestimmbar, nicht weiter verfolgt",
}
# Gruppen, deren Urteil daran hängt, dass bestimmte Einheiten geschlossen sind – und welche Rolle das ist.
# „eintragen“ lässt sich also erst schließen, wenn die Vermietung wirklich eingetragen ist.
PRUEF_ROLLE = {"erledigt": "zu", "eintragen": "eintragen"}
VERMERK_ENDE = "<br><br>"


def vermerk_html(stand: str, gruppe: str, urteil: str) -> str:
    """Erste Zeile im Aufgabentext. Schlicht gehalten (Text + Zeilenumbrüche), so wie die
    Handler ihre Texte schreiben – das übersteht das Speichern unverändert."""
    return html.escape(f"Vorprüfung {stand}: {URTEIL_WORT.get(gruppe, gruppe)}. {urteil}", quote=False) + VERMERK_ENDE


def plane_urteile(aufgaben: list[dict], vorpruefung: dict, gruppen: set[str],
                  einheiten: dict[int, dict]) -> tuple[list[dict], list[str]]:
    """Schließplan aus einer Vorprüfung: nur Aufgaben, die dort stehen UND heute noch offene
    Newsletter-Aufgaben sind. Ein Vorgang der Gruppen „erledigt“ und „eintragen“ wird
    ausgelassen, wenn eine der dafür maßgeblichen Einheiten (PRUEF_ROLLE) heute offen ist
    oder sich nicht lesen ließ – dann stimmt das Urteil nicht (mehr)."""
    offen = {a["activatable_id"]: a for a in offene_newsletter_aufgaben(aufgaben)}
    plan: list[dict] = []
    hinweise: list[str] = []
    for fall in vorpruefung.get("faelle", []):
        gruppe = fall.get("gruppe")
        if gruppe not in gruppen:
            continue
        if gruppe in PRUEF_ROLLE:
            zu = [e["id"] for e in fall.get("einheiten", []) if e.get("rolle") == PRUEF_ROLLE[gruppe]]
            geplatzt = [u for u in zu if u not in einheiten or not einheit_abgeschlossen(einheiten[u])]
            if geplatzt or not zu:
                hinweise.append(f"{fall.get('ort')}: ausgelassen – Einheit(en) {geplatzt or 'fehlen'} "
                                "sind heute nicht (mehr) geschlossen")
                continue
        for genannt in fall.get("aufgaben", []):
            aufgabe = offen.get(genannt["id"])
            if aufgabe is None:
                hinweise.append(f"Task {genannt['id']} ({fall.get('ort')}): nicht mehr offen – übersprungen")
                continue
            plan.append({
                "task_id": genannt["id"], "grund": gruppe, "behalten": None,
                "titel": aufgabe.get("title"),
                "angelegt": str(aufgabe.get("original_created_at") or "")[:10],
                "units": [u for u in (aufgabe.get("property_ids") or []) if isinstance(u, int)],
                "vermerk": vermerk_html(vorpruefung.get("stand", ""), gruppe, fall.get("urteil", "")),
            })
    return plan, hinweise


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

    def text(self, task_id: int) -> str:
        """Aufgabentext; ein Lesefehler wird NICHT geschluckt – wer den Text nicht kennt,
        darf ihn nicht überschreiben."""
        data = self._request("GET", f"/tasks/{task_id}").json()
        task = data.get("task") if isinstance(data.get("task"), dict) else data
        return _scalar(task.get("body")) or ""

    def schliesse_mit_vermerk(self, task_id: int, vermerk: str) -> None:
        alt = self.text(task_id)
        neu = alt if alt.startswith(vermerk) else vermerk + alt
        self._request("PUT", f"/tasks/{task_id}", json={"task": {"done": True, "body": neu}})

    def oeffne_ohne_vermerk(self, task_id: int, vermerk: str) -> bool:
        """Wieder öffnen und den Vermerk entfernen. False, wenn der Text nicht mehr mit dem
        Vermerk beginnt (jemand hat ihn geändert) – dann wird nur geöffnet."""
        alt = self.text(task_id)
        if alt.startswith(vermerk):
            self._request("PUT", f"/tasks/{task_id}", json={"task": {"done": False, "body": alt[len(vermerk):]}})
            return True
        self.setze_erledigt(task_id, False)
        return False


def _drucke(plan: list[dict]) -> None:
    for grund, ueberschrift in ((GEGENSTANDSLOS, "Gegenstandslos (Einheit schon vermietet/abgeschlossen)"),
                                (DUBLETTE, "Dublette (ältere offene Aufgabe zur selben Einheit bleibt)"),
                                (VOLLZUG, "Antwort auf eine Vollzugsmeldung (#objekte)")):
        _drucke_gruppe(plan, grund, ueberschrift)
    for grund, wort in URTEIL_WORT.items():
        if any(e["grund"] == grund for e in plan):
            _drucke_gruppe(plan, grund, f"Vorprüfung: {wort}")
    if any(e["grund"] == "einzeln" for e in plan):
        _drucke_gruppe(plan, "einzeln", "Auf Ansage (Liste)")


def _drucke_gruppe(plan: list[dict], grund: str, ueberschrift: str) -> None:
    zeilen = [e for e in plan if e["grund"] == grund]
    print(f"\n{ueberschrift}: {len(zeilen)}")
    for e in zeilen:
        zusatz = f" – bleibt offen: Task {e['behalten']}" if e["behalten"] else ""
        print(f"  Task {e['task_id']}  {e['angelegt']}  {e['titel']}  (Units {e['units']}){zusatz}")


def _undo(ps: Propstack, datei: str, apply: bool) -> int:
    """Die im Protokoll genannten Aufgaben wieder öffnen – schreibt nur mit --apply,
    und auch dann erst eine Aufgabe als Probe mit Gegenlesen."""
    protokoll = json.loads(Path(datei).read_text(encoding="utf-8"))
    task_ids = list(protokoll.get("geschlossen", [])) + list(protokoll.get("unklar", []))
    if not apply:
        print(f"Würde {len(task_ids)} Aufgaben wieder öffnen: {task_ids[:10]}{' …' if len(task_ids) > 10 else ''}")
        print("Nur gelesen. Zum Öffnen: --undo <Protokoll> --apply")
        return 0
    if not task_ids:
        return 0
    vermerke = {int(k): v for k, v in (protokoll.get("vermerke") or {}).items()}
    geaendert: list[int] = []

    def oeffne(task_id: int) -> None:
        if task_id in vermerke:
            if not ps.oeffne_ohne_vermerk(task_id, vermerke[task_id]):
                geaendert.append(task_id)
        else:
            ps.setze_erledigt(task_id, False)

    oeffne(task_ids[0])
    time.sleep(1.5)
    if ps.ist_erledigt(task_ids[0]) is not False:
        print(f"ABBRUCH: Probe Task {task_ids[0]} erscheint nach dem Schreiben nicht als offen. "
              "Nur diese eine Aufgabe wurde angefasst.", file=sys.stderr)
        return 1
    print(f"Probe ok: Task {task_ids[0]} ist wieder offen.")
    for task_id in task_ids[1:]:
        oeffne(task_id)
        time.sleep(0.4)
    print(f"{len(task_ids)} Aufgaben wieder geöffnet.")
    if geaendert:
        print(f"Vermerk nicht entfernt (Text wurde inzwischen geändert): {geaendert}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="gelistete Aufgaben als erledigt markieren (schreibt!)")
    ap.add_argument("--limit", type=int, help="höchstens so viele Aufgaben schließen")
    ap.add_argument("--nur", choices=[GEGENSTANDSLOS, DUBLETTE, VOLLZUG], help="nur diese Gruppe")
    ap.add_argument("--undo", metavar="PROTOKOLL", help="die in diesem Protokoll genannten Aufgaben wieder öffnen")
    ap.add_argument("--urteile", metavar="VORPRUEFUNG", help="statt der drei Regeln: Aufgaben aus dieser Vorprüfung")
    ap.add_argument("--gruppen", default="erledigt,fremd", help="Gruppen der Vorprüfung (Standard: erledigt,fremd)")
    ap.add_argument("--ausser", default="", help="Task-IDs, die offen bleiben (Komma-getrennt)")
    ap.add_argument("--einzeln", metavar="LISTE", help="genau diese Aufgaben (JSON: [{task_id, grund}])")
    args = ap.parse_args()
    ausser = {int(t) for t in args.ausser.replace(" ", "").split(",") if t}

    key = os.environ.get("PROPSTACK_API_KEY") or os.environ.get("PROPSTACK_API_V1")
    if not key:
        print("PROPSTACK_API_KEY bzw. PROPSTACK_API_V1 fehlt.", file=sys.stderr)
        return 2
    ps = Propstack(key)
    if args.undo:
        return _undo(ps, args.undo, args.apply)

    aufgaben = ps.aufgaben()
    alle_offenen = [a for a in aufgaben if not _scalar(a.get("done"))]
    offene = offene_newsletter_aufgaben(aufgaben)
    objekte = offene_objekte_aufgaben(aufgaben)
    unit_ids = sorted({u for a in offene for u in (a.get("property_ids") or []) if isinstance(u, int)})
    hinweise: list[str] = []
    if args.einzeln:
        liste = json.loads(Path(args.einzeln).read_text(encoding="utf-8"))["aufgaben"]
        plan, hinweise = plane_einzeln(aufgaben, liste, f"{datetime.now():%d.%m.%Y}")
    elif args.urteile:
        vorpruefung = json.loads(Path(args.urteile).read_text(encoding="utf-8"))
        gruppen = {g.strip() for g in args.gruppen.split(",") if g.strip()}
        zu_pruefen = sorted({e["id"] for f in vorpruefung.get("faelle", []) if f.get("gruppe") in gruppen
                             for e in f.get("einheiten", []) if e.get("rolle") == PRUEF_ROLLE.get(f.get("gruppe"))})
        plan, hinweise = plane_urteile(aufgaben, vorpruefung, gruppen, ps.einheiten(zu_pruefen))
    else:
        plan = plane(aufgaben, ps.einheiten(unit_ids))
        plan += plane_vollzug(aufgaben, ps.texte([a["activatable_id"] for a in objekte]), f"{datetime.now():%d.%m.%Y}")
        if args.nur:
            plan = [e for e in plan if e["grund"] == args.nur]
    if ausser:
        bleiben = [e["task_id"] for e in plan if e["task_id"] in ausser]
        plan = [e for e in plan if e["task_id"] not in ausser]
        print(f"Bleiben auf Ansage offen: {bleiben}")

    print(f"{len(aufgaben)} Aufgaben über alle Nutzer, {len(alle_offenen)} offen – davon {len(offene)} "
          f"„{TITEL_PRAEFIX}“ und {len(objekte)} aus #objekte.")
    _drucke(plan)
    for hinweis in hinweise:
        print(f"  Hinweis: {hinweis}")
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
    unklar: list[int] = []  # Schreiben gescheitert, Ausgang offen (Timeout, 5xx) – --undo öffnet sie mit

    vermerke: dict[str, str] = {}

    def sichere() -> None:
        protokoll.write_text(json.dumps({"geschlossen": geschlossen, "unklar": unklar, "vermerke": vermerke},
                                        ensure_ascii=False, indent=1), encoding="utf-8")

    def schliesse(eintrag: dict) -> None:
        if eintrag.get("vermerk"):
            vermerke[str(eintrag["task_id"])] = eintrag["vermerk"]
            sichere()  # vor dem Schreiben: auch ein Abbruch mittendrin bleibt zurücknehmbar
            ps.schliesse_mit_vermerk(eintrag["task_id"], eintrag["vermerk"])
        else:
            ps.setze_erledigt(eintrag["task_id"], True)

    probe = plan[0]
    schliesse(probe)
    geschlossen.append(probe["task_id"])
    sichere()
    time.sleep(1.5)
    stand = ps.ist_erledigt(probe["task_id"])
    if stand is True and probe.get("vermerk") and not ps.text(probe["task_id"]).startswith(probe["vermerk"]):
        print(f"ABBRUCH: Probe Task {probe['task_id']} ist erledigt, der Vermerk steht aber nicht so im Text, "
              f"wie er geschrieben wurde. Nur diese eine Aufgabe wurde angefasst. Protokoll: {protokoll}", file=sys.stderr)
        return 1
    if stand is not True:
        print(f"ABBRUCH: Probe Task {probe['task_id']} erscheint nach dem Schreiben nicht als erledigt "
              f"(gelesen: {stand}). Nur diese eine Aufgabe wurde angefasst. Protokoll: {protokoll}", file=sys.stderr)
        return 1
    print(f"Probe ok: Task {probe['task_id']} ist erledigt.")

    fehler: list[tuple[int, str]] = []
    for eintrag in plan[1:]:
        try:
            schliesse(eintrag)
            geschlossen.append(eintrag["task_id"])
            sichere()
        except httpx.HTTPError as e:
            fehler.append((eintrag["task_id"], str(e)))
            unklar.append(eintrag["task_id"])
            sichere()
        time.sleep(0.4)

    print(f"Geschlossen: {len(geschlossen)} von {len(plan)}. Fehler: {len(fehler)} {fehler[:5]}")
    print(f"Protokoll: {protokoll}  (zurücknehmen mit --undo {protokoll})")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
