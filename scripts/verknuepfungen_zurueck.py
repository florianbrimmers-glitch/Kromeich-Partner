"""Dreht die Umbeschriftung vom 12.11.2026 zurück (Liste: verknuepfungen_korrektur_2026-11-12.json).

Am 12.11.2026 wurden 190 Verknüpfungen Person <-> Firma irrtümlich umbeschriftet.
Richtig ist: Zeile der Person "Mitarbeiter" (erscheint an der Firma), Zeile der
Firma "Firma" (erscheint an der Person).

Liest standardmäßig nur. Mit --apply werden nur Paare aus der Liste geändert, die
noch genau im Stand vom 12.11. sind; jedes Paar wird davor und danach gelesen.

Aufruf:  python scripts/verknuepfungen_zurueck.py [--apply [--limit N]]
Umgebung: PROPSTACK_API_V2 (wird nie ausgegeben).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

V2 = "https://api.propstack.de/v2/relationships"
LISTE = Path(__file__).with_name("verknuepfungen_korrektur_2026-11-12.json")


def labels(client: httpx.Client, person_id: int, firma_id: int) -> dict:
    out = {}
    for cid in (person_id, firma_id):
        for attempt in range(5):
            r = client.get(V2, params={"client_id": cid, "internal_name": "associate", "per": 100})
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 * (attempt + 1))
                continue
            break
        r.raise_for_status()
        for row in r.json().get("data") or []:
            if {row.get("client_id"), row.get("related_client_id")} == {person_id, firma_id}:
                out[row.get("id")] = row.get("name")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="zurückdrehen (schreibt!)")
    ap.add_argument("--limit", type=int, help="höchstens so viele Paare ändern")
    ap.add_argument("--only", type=int, help="nur das Paar mit dieser Zeile der Person")
    args = ap.parse_args()
    key = os.environ.get("PROPSTACK_API_V2")
    if not key:
        print("PROPSTACK_API_V2 fehlt.", file=sys.stderr)
        return 2
    pairs = json.loads(LISTE.read_text(encoding="utf-8"))["paare"]
    if args.only:
        pairs = [e for e in pairs if e["zeile_person"] == args.only]
    counts = {"noch verkehrt": 0, "schon richtig": 0, "abweichend": 0, "zurückgedreht": 0}
    headers = {"X-API-KEY": key, "User-Agent": "kontakt-import/1.0", "Content-Type": "application/json"}
    with httpx.Client(timeout=30.0, headers=headers) as client:
        for e in pairs:
            zp, zf = e["zeile_person"], e["zeile_firma"]
            now = labels(client, e["person_id"], e["firma_id"])
            if now == {zp: "Mitarbeiter", zf: "Firma"}:
                counts["schon richtig"] += 1
                continue
            if now != {zp: "Firma", zf: "Mitarbeiter"}:
                counts["abweichend"] += 1
                print(f"  abweichend, nicht angefasst: {zp}/{zf}: {now}")
                continue
            if not args.apply or (args.limit is not None and counts["zurückgedreht"] >= args.limit):
                counts["noch verkehrt"] += 1
                continue
            for row_id, name in ((zp, "Mitarbeiter"), (zf, "Firma")):
                r = client.put(f"{V2}/{row_id}", json={"name": name})
                if r.status_code != 200:
                    print(f"  PUT {row_id}: {r.status_code} – Abbruch")
                    return 1
            if labels(client, e["person_id"], e["firma_id"]) != {zp: "Mitarbeiter", zf: "Firma"}:
                print(f"  {zp}/{zf}: nach dem Schreiben unerwartet – Abbruch")
                return 1
            counts["zurückgedreht"] += 1
    for k, v in counts.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
