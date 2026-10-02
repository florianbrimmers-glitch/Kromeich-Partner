"""TEMP-Diagnose (nur lesend): Auf wen legt der newsletter_handler seine Review-Aufgaben?

1. GET /brokers  -> Zuordnung ID -> Name (prüft, ob 387451 wirklich Marek ist)
2. je Broker GET /activities?item_type=reminder -> Aufgaben mit Titel
   'Newsletter-Vermietung prüfen' zählen, jüngste listen.
Keine Writes.
"""
from __future__ import annotations

import os
import time

import httpx

BASE = "https://api.propstack.de/v1"
KEY = os.environ["PROPSTACK_API_KEY"]
PREFIX = "Newsletter-Vermietung prüfen"
CONFIG_ID = 387451


def get(path: str, **params):
    for attempt in range(4):
        r = httpx.get(f"{BASE}{path}", headers={"X-API-KEY": KEY}, params=params, timeout=30)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def rows(payload):
    return payload if isinstance(payload, list) else (payload or {}).get("data", [])


def scalar(v):
    return v["value"] if isinstance(v, dict) and "value" in v else v


brokers = rows(get("/brokers"))
print("=" * 70)
print(f"{len(brokers)} Broker in Propstack:")
names = {}
for b in brokers:
    bid = b.get("id")
    name = b.get("name") or " ".join(x for x in (b.get("first_name"), b.get("last_name")) if x)
    names[bid] = name
    mark = "   <-- newsletter_handler BROKER_MAREK" if bid == CONFIG_ID else ""
    print(f"  {bid:>8}  {name}  ({b.get('email') or '-'}){mark}")
print(f"\n387451 laut Propstack: {names.get(CONFIG_ID, 'NICHT GEFUNDEN')}")

print("=" * 70)
print(f"Aufgaben mit Titel '{PREFIX}…' je Broker:")
gesamt = 0
for bid in names:
    treffer = []
    page = 1
    while True:
        batch = rows(get("/activities", item_type="reminder", broker_id=bid,
                         sort_by="created_at", order="desc", per=200, page=page))
        for t in batch:
            title = scalar(t.get("title")) or ""
            if title.startswith(PREFIX):
                treffer.append(t)
        if len(batch) < 200:
            break
        page += 1
        time.sleep(0.5)
    if treffer:
        gesamt += len(treffer)
        offen = sum(1 for t in treffer if not scalar(t.get("done")))
        print(f"\n  Broker {bid} ({names[bid]}): {len(treffer)} Aufgaben, davon {offen} offen")
        for t in treffer[:8]:
            print(f"     #{t.get('id')}  {scalar(t.get('original_created_at')) or scalar(t.get('created_at'))}"
                  f"  done={scalar(t.get('done'))}  broker_id={scalar(t.get('broker_id'))}  {scalar(t.get('title'))[:70]}")
    time.sleep(0.3)
print(f"\nGESAMT: {gesamt} Newsletter-Review-Aufgaben gefunden")
print("=" * 70)
