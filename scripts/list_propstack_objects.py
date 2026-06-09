#!/usr/bin/env python3
"""
Listet Propstack-Objekte (GET /v1/units) auf – standardmäßig Gewerbe/Industrie
im Umkreis um Glandorf. Parameter über ENV:
  REGION_RADIUS_KM (Default 80)  – 0 = kein Umkreisfilter
  ONLY_COMMERCIAL  (Default 1)   – 1 = nur Gewerbe/Industrie, 0 = alle
Nutzung: PROPSTACK_API_KEY=xxx python3 scripts/list_propstack_objects.py
"""
import os
import sys
import math
import time
import requests

BASE = "https://api.propstack.de/v1"
CENTER_LAT, CENTER_LON = 52.0815780, 8.0033646
RADIUS_KM = float(os.environ.get("REGION_RADIUS_KM", "80"))
ONLY_COMMERCIAL = os.environ.get("ONLY_COMMERCIAL", "1") == "1"


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d1 = math.radians(lat2 - lat1)
    d2 = math.radians(lon2 - lon1)
    a = math.sin(d1 / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d2 / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def fetch_units(key):
    units, page = [], 1
    while True:
        for attempt in range(4):
            try:
                r = requests.get(f"{BASE}/units",
                                 params={"api_key": key, "page": page, "per": 200, "expand": 1},
                                 headers={"Accept": "application/json"}, timeout=60)
                r.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        batch = r.json()
        batch = batch if isinstance(batch, list) else batch.get("data", [])
        if not batch:
            break
        units.extend(batch)
        if len(batch) < 200:
            break
        page += 1
        time.sleep(0.3)
    return units


def is_commercial(u):
    return (u.get("object_type") == "COMMERCIAL"
            or u.get("rs_category") == "COMMERCIAL"
            or (u.get("rs_type") or "") in {"INDUSTRY", "OFFICE", "RETAIL", "GASTRONOMY", "HALL"})


def area(u):
    for k in ("total_floor_space", "property_space_value", "usable_floor_space",
              "net_floor_space", "living_space", "plot_area"):
        v = u.get(k)
        if v not in (None, "", 0):
            try:
                return f"{float(v):,.0f}".replace(",", ".")
            except (TypeError, ValueError):
                pass
    return "—"


def main():
    key = os.environ.get("PROPSTACK_API_KEY")
    if not key:
        sys.exit("FEHLER: PROPSTACK_API_KEY nicht gesetzt.")
    print("Lade Propstack-Objekte ...", file=sys.stderr)
    units = fetch_units(key)
    print(f"Objekte gesamt: {len(units)}", file=sys.stderr)

    rows = []
    no_coords = 0
    for u in units:
        if ONLY_COMMERCIAL and not is_commercial(u):
            continue
        lat, lng = u.get("lat"), u.get("lng")
        dist = None
        if lat and lng:
            try:
                dist = haversine_km(CENTER_LAT, CENTER_LON, float(lat), float(lng))
            except (TypeError, ValueError):
                dist = None
        if RADIUS_KM > 0:
            if dist is None:
                no_coords += 1
                continue
            if dist > RADIUS_KM:
                continue
        status = u.get("property_status")
        status = status.get("name") if isinstance(status, dict) else status
        broker = u.get("broker")
        broker = broker.get("name") if isinstance(broker, dict) else broker
        rows.append({
            "id": u.get("id"),
            "dist": dist,
            "name": u.get("name") or u.get("title") or "",
            "addr": " ".join(filter(None, [u.get("street", ""), str(u.get("zip_code") or ""),
                                           u.get("city", "")])).strip(),
            "rs_type": u.get("rs_type") or u.get("object_type") or "",
            "mkt": u.get("marketing_type") or "",
            "status": status or "",
            "area": area(u),
            "broker": broker or "",
        })
    rows.sort(key=lambda x: (x["dist"] is None, x["dist"] if x["dist"] is not None else 9e9))

    label = "Gewerbe/Industrie" if ONLY_COMMERCIAL else "alle"
    scope = f"≤ {RADIUS_KM:.0f} km um Glandorf" if RADIUS_KM > 0 else "ohne Umkreisfilter"
    print(f"\n{'='*100}\nPropstack-Objekte ({label}, {scope}) — {len(rows)} Treffer")
    if RADIUS_KM > 0 and no_coords:
        print(f"(zusätzlich {no_coords} {label}-Objekte ohne Koordinaten – nicht regional zuordenbar)")
    print("=" * 100)
    print(f"{'#ID':>8} | {'km':>4} | {'Typ':<9} | {'Verm.':<5} | {'Fläche':>9} | {'Makler':<16} | Name / Adresse")
    print("-" * 100)
    for r in rows:
        d = f"{r['dist']:.0f}" if r["dist"] is not None else "?"
        nm = r["name"] if r["name"] else r["addr"]
        extra = f"  [{r['addr']}]" if r["name"] and r["addr"] and r["addr"] not in r["name"] else ""
        print(f"{r['id']:>8} | {d:>4} | {r['rs_type'][:9]:<9} | {r['mkt'][:5]:<5} | "
              f"{r['area']:>9} | {r['broker'][:16]:<16} | {nm[:40]}{extra}")


if __name__ == "__main__":
    main()
