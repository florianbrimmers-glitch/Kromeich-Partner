#!/usr/bin/env python3
"""
Sucht Hallen-Objekte (Lager/Logistik/Produktion) innerhalb einer OSM-Verwaltungsfläche
und berechnet die Gebäude-Grundfläche.

Nutzung: python3 scripts/osm_halls_in_area.py <osm_relation_id> <Label> [min_m2]
Beispiel: python3 scripts/osm_halls_in_area.py 62385 "Mülheim an der Ruhr" 1000
"""
import json
import math
import sys
import time
import requests

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HALL_TYPES = "warehouse|industrial|logistics|distribution|manufacture|storage|hall"
GENERIC_OK = {"yes", "hall", "shed", "hangar", "commercial"}


def build_query(rel_id):
    area = 3600000000 + int(rel_id)
    return f"""
[out:json][timeout:300];
area(id:{area})->.a;
// A: explizit getaggte Hallen
(
  way(area.a)["building"~"{HALL_TYPES}"];
  relation(area.a)["building"~"{HALL_TYPES}"];
);
out tags geom;
// B: Gebäude in Industrie-/Gewerbeflächen (fängt building=yes-Hallen)
(
  way(area.a)["landuse"~"industrial|commercial|logistics|port"];
  relation(area.a)["landuse"~"industrial|commercial|logistics|port"];
);
map_to_area->.zones;
(
  way(area.a)(area.zones)["building"];
);
out tags geom;
"""


def ring_area_m2(geom, ref_lat):
    if len(geom) < 3:
        return 0.0
    R = 6371000.0
    cl = math.cos(math.radians(ref_lat))
    pts = [(math.radians(c["lon"]) * R * cl, math.radians(c["lat"]) * R) for c in geom]
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def way_area(el):
    g = el.get("geometry")
    if not g:
        return 0.0, None, None
    lat = sum(p["lat"] for p in g) / len(g)
    lon = sum(p["lon"] for p in g) / len(g)
    return ring_area_m2(g, lat), lat, lon


def relation_area(el):
    outer = inner = 0.0
    la = lo = 0.0
    cnt = 0
    for m in el.get("members", []):
        for p in (m.get("geometry") or []):
            la += p["lat"]; lo += p["lon"]; cnt += 1
    if not cnt:
        return 0.0, None, None
    ref = la / cnt
    for m in el.get("members", []):
        g = m.get("geometry")
        if not g or len(g) < 3:
            continue
        a = ring_area_m2(g, ref)
        if m.get("role") == "inner":
            inner += a
        else:
            outer += a
    return max(outer - inner, 0.0), ref, lo / cnt


def fetch(query):
    last = None
    for url in OVERPASS_URLS:
        for attempt in range(3):
            try:
                print(f"  Overpass {url} (Versuch {attempt+1}) ...", file=sys.stderr)
                r = requests.post(url, data={"data": query}, timeout=320,
                                  headers={"User-Agent": "KromeichPartner-Research/1.0"})
                if r.status_code == 200:
                    return r.json()
                last = f"HTTP {r.status_code}: {r.text[:200]}"
            except Exception as e:
                last = str(e)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Overpass fehlgeschlagen: {last}")


def main():
    rel_id = sys.argv[1]
    label = sys.argv[2]
    min_m2 = float(sys.argv[3]) if len(sys.argv) > 3 else 1000.0

    data = fetch(build_query(rel_id))
    seen = {}
    for el in data.get("elements", []):
        key = f'{el["type"]}/{el["id"]}'
        if key in seen:
            continue
        tags = el.get("tags", {})
        b = tags.get("building", "")
        # generische Gebäude nur, wenn plausibler Hallentyp
        if b not in GENERIC_OK and not any(t in b for t in
                ["warehouse", "industrial", "logistics", "distribution",
                 "manufacture", "storage", "hall"]):
            continue
        if el["type"] == "way":
            a, lat, lon = way_area(el)
        elif el["type"] == "relation":
            a, lat, lon = relation_area(el)
        else:
            continue
        if a < min_m2 or lat is None:
            continue
        seen[key] = {
            "osm": key,
            "area_m2": round(a),
            "lat": round(lat, 6), "lon": round(lon, 6),
            "building": b,
            "name": tags.get("name") or tags.get("operator") or tags.get("brand") or "",
            "addr": " ".join(filter(None, [
                tags.get("addr:street", ""), tags.get("addr:housenumber", ""),
                tags.get("addr:postcode", ""), tags.get("addr:city", "")])).strip(),
        }
    res = sorted(seen.values(), key=lambda x: -x["area_m2"])
    print(json.dumps({"label": label, "relation": rel_id, "min_m2": min_m2,
                      "count": len(res), "results": res}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
