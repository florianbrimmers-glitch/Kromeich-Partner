#!/usr/bin/env python3
"""
V3: Fasst benachbarte Gebäude zu Komplexen zusammen (statt Einzelhallen) und
filtert nach SUMME der Gebäude-Grundflächen 30.000-40.000 m².

Methode:
  - Hole alle Gebäude (a) mit Logistik-/Industrie-/Gewerbe-Typ und
    (b) innerhalb von landuse=industrial/commercial/logistics-Flächen im 40-km-Umkreis.
  - Clustere Gebäude, deren Außenkanten < CLUSTER_GAP_M (40 m) zueinander liegen
    (Vertex-Grid + Union-Find -> mehrteilige Komplexe eines Betreibers).
  - Summiere Footprints je Komplex, filtere 30.000-40.000 m² (Kontext 25.000-45.000).
"""
import json
import math
import sys
import time
import requests

CENTER_LAT = 52.0815780
CENTER_LON = 8.0033646
RADIUS_M = 40000
AREA_MIN, AREA_MAX = 30000, 40000
CONTEXT_MIN, CONTEXT_MAX = 25000, 45000
CLUSTER_GAP_M = 10.0          # max. Kantenabstand, damit zwei Gebäude zum selben Komplex zählen
# Nur logistik-relevante Gebäudetypen clustern (Einzelhandel/Supermarkt/Vordach/Gewächshaus etc. raus)
ALLOWED_TYPES = {"warehouse", "industrial", "logistics", "distribution",
                 "manufacture", "storage", "yes", "hangar", "shed"}

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

QUERY = f"""
[out:json][timeout:300];
(
  way["building"~"warehouse|industrial|logistics|distribution|manufacture|commercial|storage"](around:{RADIUS_M},{CENTER_LAT},{CENTER_LON});
);
out tags geom;
(
  way["landuse"~"industrial|commercial|logistics|port"](around:{RADIUS_M},{CENTER_LAT},{CENTER_LON});
  relation["landuse"~"industrial|commercial|logistics|port"](around:{RADIUS_M},{CENTER_LAT},{CENTER_LON});
);
map_to_area->.zones;
(
  way(area.zones)["building"];
);
out tags geom;
"""

R_EARTH = 6371000.0
COSLAT = math.cos(math.radians(CENTER_LAT))


def to_xy(lat, lon):
    x = math.radians(lon) * R_EARTH * COSLAT
    y = math.radians(lat) * R_EARTH
    return x, y


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(a))


def ring_area_m2(geom):
    if len(geom) < 3:
        return 0.0
    pts = [to_xy(c["lat"], c["lon"]) for c in geom]
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


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


class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def main():
    data = fetch()
    # Gebäude einsammeln (dedupe)
    blds = {}
    for el in data.get("elements", []):
        if el["type"] != "way" or "geometry" not in el:
            continue
        if el["id"] in blds:
            continue
        t = el.get("tags", {})
        if t.get("building", "") not in ALLOWED_TYPES:
            continue
        geom = el["geometry"]
        area = ring_area_m2(geom)
        if area <= 0:
            continue
        xs = [to_xy(c["lat"], c["lon"]) for c in geom]
        cx = sum(p[0] for p in xs) / len(xs)
        cy = sum(p[1] for p in xs) / len(xs)
        clat = sum(c["lat"] for c in geom) / len(geom)
        clon = sum(c["lon"] for c in geom) / len(geom)
        t = el.get("tags", {})
        blds[el["id"]] = {
            "id": el["id"], "area": area, "verts": xs,
            "cx": cx, "cy": cy, "clat": clat, "clon": clon,
            "building": t.get("building", ""),
            "name": t.get("name") or t.get("operator") or t.get("brand") or "",
        }
    items = list(blds.values())
    n = len(items)
    print(f"Gebäude gesamt: {n}", file=sys.stderr)

    # Vertex-Grid -> benachbarte Gebäude (Kantenabstand < GAP) unionen
    uf = UF(n)
    cell = CLUSTER_GAP_M
    grid = {}
    for idx, b in enumerate(items):
        for (x, y) in b["verts"]:
            grid.setdefault((int(x // cell), int(y // cell)), []).append((idx, x, y))
    gap2 = CLUSTER_GAP_M ** 2
    for (gx, gy), pts in grid.items():
        neigh = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                neigh.extend(grid.get((gx + dx, gy + dy), ()))
        for (i, xi, yi) in pts:
            ri = uf.find(i)
            for (j, xj, yj) in neigh:
                if j <= i:
                    continue
                if uf.find(j) == ri:
                    continue
                if (xi - xj) ** 2 + (yi - yj) ** 2 <= gap2:
                    uf.union(i, j)

    # Cluster aggregieren
    clusters = {}
    for idx, b in enumerate(items):
        root = uf.find(idx)
        c = clusters.setdefault(root, {"area": 0.0, "members": [], "names": set(), "types": {}})
        c["area"] += b["area"]
        c["members"].append(b)
        if b["name"]:
            c["names"].add(b["name"])
        c["types"][b["building"]] = c["types"].get(b["building"], 0) + 1

    results = []
    for c in clusters.values():
        area = c["area"]
        if not (CONTEXT_MIN <= area <= CONTEXT_MAX):
            continue
        clat = sum(m["clat"] for m in c["members"]) / len(c["members"])
        clon = sum(m["clon"] for m in c["members"]) / len(c["members"])
        dist = haversine(CENTER_LAT, CENTER_LON, clat, clon)
        if dist > RADIUS_M:
            continue
        dom_type = max(c["types"].items(), key=lambda kv: kv[1])[0]
        results.append({
            "total_area_m2": round(area),
            "n_buildings": len(c["members"]),
            "dist_km": round(dist / 1000, 1),
            "lat": round(clat, 6), "lon": round(clon, 6),
            "dom_type": dom_type,
            "names": sorted(c["names"]),
            "in_band": AREA_MIN <= area <= AREA_MAX,
            "member_ids": [m["id"] for m in c["members"]],
        })
    results.sort(key=lambda x: (not x["in_band"], x["dist_km"]))
    out = {
        "center": {"lat": CENTER_LAT, "lon": CENTER_LON, "name": "Glandorf"},
        "radius_km": RADIUS_M / 1000, "cluster_gap_m": CLUSTER_GAP_M,
        "band_m2": [AREA_MIN, AREA_MAX],
        "count_in_band": sum(1 for r in results if r["in_band"]),
        "count_multi_in_band": sum(1 for r in results if r["in_band"] and r["n_buildings"] > 1),
        "count_context": len(results),
        "results": results,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
