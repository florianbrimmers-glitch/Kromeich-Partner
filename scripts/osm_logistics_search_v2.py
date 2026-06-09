#!/usr/bin/env python3
"""
V2: Breitere Suche nach Logistik-/Lagerhallen um Glandorf.
Erweitert ggü. V1:
  - mehr Gebäudetypen (warehouse, industrial, logistics, distribution, manufacture, commercial, storage)
  - PLUS generische building=yes-Gebäude, die innerhalb von landuse=industrial/commercial/logistics liegen
Filtert nach Gebäude-Footprint 30.000-40.000 m² (Kontextband 25.000-45.000).
"""
import json
import math
import time
import sys
import requests

CENTER_LAT = 52.0815780
CENTER_LON = 8.0033646
RADIUS_M = 40000
AREA_MIN, AREA_MAX = 30000, 40000
CONTEXT_MIN, CONTEXT_MAX = 25000, 45000

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Teil A: explizit getaggte Gebäude.  Teil B: building=yes/* in Industrie-/Gewerbe-/Logistikflächen.
QUERY = f"""
[out:json][timeout:300];
// --- Teil A: explizit getaggte Hallen ---
(
  way["building"~"warehouse|industrial|logistics|distribution|manufacture|commercial|storage"](around:{RADIUS_M},{CENTER_LAT},{CENTER_LON});
  relation["building"~"warehouse|industrial|logistics|distribution|manufacture|commercial|storage"](around:{RADIUS_M},{CENTER_LAT},{CENTER_LON});
);
out tags geom;
// --- Teil B: Gebäude innerhalb von Industrie-/Gewerbe-/Logistikflächen ---
(
  way["landuse"~"industrial|commercial|logistics|port"](around:{RADIUS_M},{CENTER_LAT},{CENTER_LON});
  relation["landuse"~"industrial|commercial|logistics|port"](around:{RADIUS_M},{CENTER_LAT},{CENTER_LON});
);
map_to_area->.zones;
(
  way(area.zones)["building"];
  relation(area.zones)["building"];
);
out tags geom;
"""


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def ring_area_m2(coords, ref_lat):
    if len(coords) < 3:
        return 0.0
    R = 6371000.0
    coslat = math.cos(math.radians(ref_lat))
    pts = [(math.radians(c["lon"]) * R * coslat, math.radians(c["lat"]) * R) for c in coords]
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def way_area(el):
    geom = el.get("geometry")
    if not geom:
        return 0.0, None, None
    lat = sum(p["lat"] for p in geom) / len(geom)
    lon = sum(p["lon"] for p in geom) / len(geom)
    return ring_area_m2(geom, lat), lat, lon


def relation_area(el):
    outer = inner = 0.0
    all_lat = all_lon = 0.0
    cnt = 0
    for m in el.get("members", []):
        g = m.get("geometry")
        if not g:
            continue
        for p in g:
            all_lat += p["lat"]; all_lon += p["lon"]; cnt += 1
    if cnt == 0:
        return 0.0, None, None
    ref_lat = all_lat / cnt
    for m in el.get("members", []):
        g = m.get("geometry")
        if not g or len(g) < 3:
            continue
        a = ring_area_m2(g, ref_lat)
        if m.get("role") == "inner":
            inner += a
        else:
            outer += a
    return max(outer - inner, 0.0), ref_lat, all_lon / cnt


def fetch():
    last_err = None
    for url in OVERPASS_URLS:
        for attempt in range(3):
            try:
                print(f"Overpass-Abfrage an {url} (Versuch {attempt+1}) ...", file=sys.stderr)
                r = requests.post(url, data={"data": QUERY}, timeout=320,
                                  headers={"User-Agent": "KromeichPartner-Research/1.0"})
                if r.status_code == 200:
                    return r.json()
                last_err = f"HTTP {r.status_code}: {r.text[:300]}"
            except Exception as e:
                last_err = str(e)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Overpass fehlgeschlagen: {last_err}")


def main():
    data = fetch()
    seen = {}
    for el in data.get("elements", []):
        key = f'{el["type"]}/{el["id"]}'
        if key in seen:
            continue
        if el["type"] == "way":
            area, lat, lon = way_area(el)
        elif el["type"] == "relation":
            area, lat, lon = relation_area(el)
        else:
            continue
        if area <= 0 or lat is None:
            continue
        if not (CONTEXT_MIN <= area <= CONTEXT_MAX):
            continue
        dist = haversine(CENTER_LAT, CENTER_LON, lat, lon)
        if dist > RADIUS_M:
            continue
        tags = el.get("tags", {})
        seen[key] = {
            "osm": key,
            "area_m2": round(area),
            "dist_km": round(dist / 1000, 1),
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "building": tags.get("building", ""),
            "name": tags.get("name") or tags.get("operator") or tags.get("brand") or "",
            "addr": " ".join(filter(None, [
                tags.get("addr:street", ""), tags.get("addr:housenumber", ""),
                tags.get("addr:postcode", ""), tags.get("addr:city", "")])).strip(),
            "in_band": AREA_MIN <= area <= AREA_MAX,
        }
    results = sorted(seen.values(), key=lambda x: (not x["in_band"], x["dist_km"]))
    out = {
        "center": {"lat": CENTER_LAT, "lon": CENTER_LON, "name": "Glandorf"},
        "radius_km": RADIUS_M / 1000,
        "band_m2": [AREA_MIN, AREA_MAX],
        "count_in_band": sum(1 for r in results if r["in_band"]),
        "count_context": len(results),
        "results": results,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
