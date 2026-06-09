#!/usr/bin/env python3
"""
Holt einzelne Propstack-Objekte per ID im Detail (GET /v1/units/{id}?expand=1)
und gibt die für den Abgleich relevanten Felder aus.

Nutzung: PROPSTACK_API_KEY=xxx python3 scripts/fetch_propstack_units.py 2778398 5032898 2777954
oder IDs über UNIT_IDS="2778398,5032898,2777954".
"""
import os
import sys
import json
import requests

BASE = "https://api.propstack.de/v1"
FIELDS = ["id", "name", "title", "street", "house_number", "zip_code", "city",
          "lat", "lng", "marketing_type", "rs_category", "rs_type", "object_type",
          "plot_area", "total_floor_space", "net_floor_space", "usable_floor_space",
          "property_space_value", "living_space", "industrial_area", "hall_height",
          "ramp", "crane_runway", "construction_year", "broker", "public_expose_url"]


def main():
    key = os.environ.get("PROPSTACK_API_KEY")
    if not key:
        sys.exit("FEHLER: PROPSTACK_API_KEY nicht gesetzt.")
    ids = [a for a in sys.argv[1:] if a.strip()]
    if not ids and os.environ.get("UNIT_IDS"):
        ids = [x.strip() for x in os.environ["UNIT_IDS"].split(",") if x.strip()]
    if not ids:
        sys.exit("Keine IDs übergeben.")

    for uid in ids:
        try:
            r = requests.get(f"{BASE}/units/{uid}", params={"api_key": key, "expand": 1},
                             headers={"Accept": "application/json"}, timeout=60)
            r.raise_for_status()
            u = r.json()
        except requests.RequestException as e:
            print(f"\n#{uid}: FEHLER {e}")
            continue
        print("\n" + "=" * 60)
        print(f"Propstack-Objekt #{uid}")
        print("=" * 60)
        for f in FIELDS:
            v = u.get(f)
            if isinstance(v, dict):
                v = v.get("name") or v.get("id") or json.dumps(v, ensure_ascii=False)
            if v not in (None, "", [], {}):
                print(f"  {f:22}: {v}")


if __name__ == "__main__":
    main()
