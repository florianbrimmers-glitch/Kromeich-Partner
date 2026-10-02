"""EINMAL-Migration: offene 'Newsletter-Vermietung prüfen'-Aufgaben von Marek (387451)
auf Lena Klinnert (254958) umhängen. Vom User am 02.10.2026 freigegeben ("die 73").

Achtung: /activities liefert Activity-IDs; die Task-ID für PUT /tasks/:id steht in
'activatable_id' (verifiziert: GET /tasks/<id> -> 404, GET /tasks/<activatable_id> -> 200).

Sicherungen: strenger Filter, Plausibilitätsgrenze, erst EINE Aufgabe umhängen und
zurücklesen, dann den Rest; am Ende Gegenzählung."""
from __future__ import annotations

import os
import sys
import time

import httpx

BASE = "https://api.propstack.de/v1"
KEY = os.environ["PROPSTACK_API_KEY"]
PREFIX = "Newsletter-Vermietung prüfen"
VON, NACH = 387451, 254958
ERWARTET = 73
H = {"X-API-KEY": KEY, "Content-Type": "application/json", "Accept": "application/json"}


def req(method, path, **kw):
    for attempt in range(4):
        r = httpx.request(method, f"{BASE}{path}", headers=H, timeout=30, **kw)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        if r.status_code >= 400:
            print(f"FEHLER {method} {path}: HTTP {r.status_code} {r.text[:300]}")
            r.raise_for_status()
        return r
    r.raise_for_status()


def rows(p):
    return p if isinstance(p, list) else (p or {}).get("data", [])


def s(v):
    return v["value"] if isinstance(v, dict) and "value" in v else v


def offene(broker):
    out, page = [], 1
    while True:
        batch = rows(req("GET", "/activities", params={
            "item_type": "reminder", "broker_id": broker,
            "sort_by": "created_at", "order": "desc", "per": 200, "page": page}).json())
        for t in batch:
            if (s(t.get("title")) or "").startswith(PREFIX) and not s(t.get("done")) \
                    and s(t.get("broker_id")) == broker:
                out.append(t)
        if len(batch) < 200:
            return out
        page += 1


def umhaengen(task_id) -> int | None:
    r = req("PUT", f"/tasks/{task_id}", json={"task": {"broker_id": NACH}})
    body = r.json() if r.content else {}
    return s((body.get("task") if isinstance(body.get("task"), dict) else body).get("broker_id"))


kandidaten = offene(VON)
print(f"Kandidaten auf {VON}: {len(kandidaten)} (erwartet {ERWARTET})")
if not (ERWARTET - 5 <= len(kandidaten) <= ERWARTET + 5):
    sys.exit("ABBRUCH: Anzahl weicht zu stark ab – nichts geändert.")

ohne_id = [t["id"] for t in kandidaten if not t.get("activatable_id")]
if ohne_id:
    sys.exit(f"ABBRUCH: {len(ohne_id)} Kandidaten ohne activatable_id – nichts geändert.")

lena_vorher = len(offene(NACH))

# 1. Probe mit genau einer Aufgabe
probe = kandidaten[0]
ret = umhaengen(probe["activatable_id"])
time.sleep(1)
noch_bei_marek = {t["activatable_id"] for t in offene(VON)}
if probe["activatable_id"] in noch_bei_marek:
    sys.exit(f"ABBRUCH: Probe Task {probe['activatable_id']} liegt weiterhin bei {VON} (PUT-Antwort broker_id={ret}). "
             "Nur diese eine Aufgabe wurde versucht.")
print(f"Probe ok: Task {probe['activatable_id']} '{s(probe.get('title'))}' -> {NACH} (Antwort broker_id={ret})")

# 2. Rest
ok, fehler = 1, []
for t in kandidaten[1:]:
    try:
        umhaengen(t["activatable_id"])
        ok += 1
    except Exception as e:  # weiter, aber protokollieren
        fehler.append((t["activatable_id"], str(e)))
    time.sleep(0.4)

# 3. Gegenzählung
time.sleep(2)
rest_marek = offene(VON)
lena_nachher = len(offene(NACH))
print("=" * 60)
print(f"umgehängt:                 {ok}/{len(kandidaten)}")
print(f"Fehler:                    {len(fehler)} {fehler[:5]}")
print(f"offen bei Marek danach:    {len(rest_marek)}")
print(f"offen bei Lena vorher/nach: {lena_vorher} -> {lena_nachher}")
print("=" * 60)
if fehler or rest_marek:
    sys.exit(1)
