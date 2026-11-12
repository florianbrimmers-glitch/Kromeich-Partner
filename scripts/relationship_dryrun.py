"""Probelauf: verkehrt herum beschriftete Verknüpfungen Person <-> Firma finden.

Liest nur (GET). Ändert nichts in Propstack.

Bis 12.11.2026 hat der Kontakt-Import die Zeile der Person mit "Mitarbeiter"
angelegt (richtig: "Firma"); die Gegenzeile an der Firma heißt dadurch "Firma"
(richtig: "Mitarbeiter"). Das Skript sucht diese Paare und meldet Sonderfälle.

Aufruf:  python scripts/relationship_dryrun.py [--out bericht.json]
Umgebung: PROPSTACK_API_V1, PROPSTACK_API_V2 (werden nie ausgegeben).
Der Bericht enthält Namen von Kontakten – nicht ins Repository legen.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict

import httpx

V1 = "https://api.propstack.de/v1"
V2 = "https://api.propstack.de/v2"
USER_AGENT = "kontakt-import/1.0"
WRONG_PERSON_LABEL = "Mitarbeiter"   # steht an der Zeile der Person, gehört an die Firma
WRONG_COMPANY_LABEL = "Firma"        # steht an der Zeile der Firma, gehört an die Person


def _get(client: httpx.Client, url: str, key: str, params: dict | None = None):
    for attempt in range(5):
        r = client.get(url, params=params, headers={"X-API-KEY": key, "User-Agent": USER_AGENT})
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def fetch_relationships(client: httpx.Client, key: str) -> list[dict]:
    rows, page = [], 1
    while True:
        body = _get(client, f"{V2}/relationships", key,
                    {"internal_name": "associate", "per": 100, "page": page})
        data = (body or {}).get("data") or []
        rows.extend(data)
        if len(data) < 100:
            return rows
        page += 1


def kind(contact: dict | None) -> str:
    """'firma', 'person' oder 'fehlt'. Personen, die fälschlich als Firma markiert
    sind, haben einen Vornamen und zählen als Person."""
    if not contact:
        return "fehlt"
    return "firma" if contact.get("is_company") and not contact.get("first_name") else "person"


def analyse(rows: list[dict], lookup) -> dict:
    by_pair = defaultdict(list)
    for r in rows:
        by_pair[(r.get("client_id"), r.get("related_client_id"))].append(r)

    candidates = [r for r in rows
                  if r.get("name") == WRONG_PERSON_LABEL and r.get("relationship_category_id") is None]
    pairs, special = [], []
    for r in candidates:
        a, b = r.get("client_id"), r.get("related_client_id")
        ca, cb = lookup(a), lookup(b)
        entry = {
            "zeile_person": r.get("id"), "person_id": a, "firma_id": b,
            "person": (ca or {}).get("name"), "firma": (cb or {}).get("name"),
        }
        problems = []
        if kind(ca) != "person" or kind(cb) != "firma":
            problems.append(f"Richtung unklar: client_id ist {kind(ca)}, related_client_id ist {kind(cb)}")
        if len(by_pair[(a, b)]) > 1:
            problems.append("mehrere Zeilen Person -> Firma: " +
                            ", ".join(f"{x.get('id')} ({x.get('name')})" for x in by_pair[(a, b)]))
        back = by_pair.get((b, a), [])
        if not back:
            problems.append("Gegenzeile Firma -> Person fehlt")
        elif len(back) > 1:
            problems.append("mehrere Gegenzeilen: " +
                            ", ".join(f"{x.get('id')} ({x.get('name')})" for x in back))
        else:
            entry["zeile_firma"] = back[0].get("id")
            entry["gegenzeile_name"] = back[0].get("name")
            entry["gegenzeile_kategorie"] = back[0].get("relationship_category_id")
            if back[0].get("name") != WRONG_COMPANY_LABEL:
                problems.append(f"Gegenzeile heißt \"{back[0].get('name')}\" statt \"{WRONG_COMPANY_LABEL}\"")
        if problems:
            entry["probleme"] = problems
            special.append(entry)
        else:
            pairs.append(entry)
    return {
        "zeilen_gesamt": len(rows),
        "namen": dict(Counter(
            f"{r.get('name')} / Kategorie {r.get('relationship_category_id') or 'leer'}" for r in rows
        ).most_common()),
        "kandidaten": len(candidates),
        "eindeutig_vertauscht": pairs,
        "sonderfaelle": special,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", help="Bericht als JSON speichern (enthält Namen)")
    args = ap.parse_args()
    k1, k2 = os.environ.get("PROPSTACK_API_V1"), os.environ.get("PROPSTACK_API_V2")
    if not k1 or not k2:
        print("PROPSTACK_API_V1 / PROPSTACK_API_V2 fehlen.", file=sys.stderr)
        return 2
    with httpx.Client(timeout=30.0) as client:
        rows = fetch_relationships(client, k2)
        cache: dict = {}

        def lookup(cid):
            if cid not in cache:
                cache[cid] = _get(client, f"{V1}/contacts/{cid}", k1)
            return cache[cid]

        report = analyse(rows, lookup)
    print(f"Zeilen gesamt: {report['zeilen_gesamt']}")
    for name, n in report["namen"].items():
        print(f"  {n:5d}  {name}")
    print(f"Kandidaten (\"{WRONG_PERSON_LABEL}\" ohne Kategorie): {report['kandidaten']}")
    print(f"Eindeutig vertauschte Paare: {len(report['eindeutig_vertauscht'])}")
    print(f"Sonderfälle: {len(report['sonderfaelle'])}")
    for e in report["eindeutig_vertauscht"][:5]:
        print(f"  Beispiel: {e['person']} ({e['person_id']}) <-> {e['firma']} ({e['firma_id']}), "
              f"Zeilen {e['zeile_person']} / {e['zeile_firma']}")
    for e in report["sonderfaelle"]:
        print(f"  Sonderfall: {e['person']} ({e['person_id']}) <-> {e['firma']} ({e['firma_id']}), "
              f"Zeile {e['zeile_person']}: {'; '.join(e['probleme'])}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
