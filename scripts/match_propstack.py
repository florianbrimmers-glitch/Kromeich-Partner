#!/usr/bin/env python3
"""
Gleicht die via OSM gefundenen Logistik-/Lagerhallen (logistik_glandorf_40km.csv)
gegen den Propstack-Objektbestand (GET /v1/units) ab.

Match-Logik:
  1. Geografisch: Propstack-Objekt liegt < MATCH_RADIUS_M (Default 400 m) am OSM-Footprint.
  2. Adresse:    gleiche PLZ + Straßenname-Teilstring (Fallback, falls keine Koordinaten).

Benötigt: Umgebungsvariable PROPSTACK_API_KEY
Nutzung:  PROPSTACK_API_KEY=xxx python3 scripts/match_propstack.py
"""
import csv
import math
import os
import re
import sys
import time
import requests

BASE = "https://api.propstack.de/v1"
MATCH_RADIUS_M = 400
HERE = os.path.dirname(__file__)
# Beide OSM-Listen: (Datei, Flächenspalte, Quelle)
OSM_SOURCES = [
    (os.path.join(HERE, "..", "logistik_glandorf_40km.csv"), "Flaeche_m2", "Einzelhalle"),
    (os.path.join(HERE, "..", "logistik_glandorf_40km_komplexe.csv"), "Gesamtflaeche_m2", "Komplex"),
]


def api_key():
    k = os.environ.get("PROPSTACK_API_KEY")
    if not k:
        sys.exit("FEHLER: PROPSTACK_API_KEY nicht gesetzt.")
    return k


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def norm_street(s):
    if not s:
        return ""
    s = s.lower().replace("straße", "str").replace("strasse", "str").replace("str.", "str")
    return re.sub(r"[^a-z0-9]", "", s)


def fetch_units(key):
    """Holt alle Objekte seitenweise. Gibt Liste von Dicts zurück."""
    units = []
    page = 1
    while True:
        for attempt in range(4):
            try:
                r = requests.get(
                    f"{BASE}/units",
                    params={"api_key": key, "page": page, "per": 200, "expand": 1},
                    headers={"Accept": "application/json"},
                    timeout=60,
                )
                r.raise_for_status()
                break
            except requests.RequestException as e:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        data = r.json()
        # Propstack liefert je nach Account entweder Liste oder {"data": [...]}
        batch = data if isinstance(data, list) else data.get("data", [])
        if not batch:
            break
        units.extend(batch)
        print(f"  Seite {page}: {len(batch)} Objekte (gesamt {len(units)})", file=sys.stderr)
        if len(batch) < 200:
            break
        page += 1
        time.sleep(0.3)
    return units


def load_osm():
    """Liest beide Listen und normalisiert auf gemeinsame Felder."""
    rows = []
    for path, area_col, source in OSM_SOURCES:
        if not os.path.exists(path):
            print(f"WARN: {path} fehlt, übersprungen.", file=sys.stderr)
            continue
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter=";"):
                rows.append({
                    "source": source,
                    "area": r.get(area_col, ""),
                    "dist_km": r.get("Entfernung_km", ""),
                    "name": r.get("Name_Betreiber", ""),
                    "place": r.get("Standort", ""),
                    "Lat": float(r["Lat"]),
                    "Lon": float(r["Lon"]),
                })
    return rows


def gfloat(u, *keys):
    for k in keys:
        v = u.get(k)
        if v not in (None, "", 0):
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def main():
    key = api_key()
    print("Lade Propstack-Objekte ...", file=sys.stderr)
    units = fetch_units(key)
    print(f"Propstack-Objekte gesamt: {len(units)}", file=sys.stderr)
    if units:
        print(f"Beispiel-Felder: {sorted(units[0].keys())}", file=sys.stderr)

    osm = load_osm()
    report = []
    for o in osm:
        cands = []
        for u in units:
            lat, lng = u.get("lat"), u.get("lng")
            dist = None
            if lat and lng:
                try:
                    dist = haversine(o["Lat"], o["Lon"], float(lat), float(lng))
                except (TypeError, ValueError):
                    dist = None
            geo_hit = dist is not None and dist <= MATCH_RADIUS_M
            # Adress-Fallback
            addr_hit = False
            ozip = "".join(filter(str.isdigit, o["place"]))[:5]
            if ozip and u.get("zip_code") and str(u["zip_code"]).strip() == ozip:
                osm_str = norm_street(o["place"])
                ps_str = norm_street(u.get("street", ""))
                if ps_str and (ps_str in osm_str or osm_str.find(ps_str[:6]) >= 0):
                    addr_hit = True
            if geo_hit or addr_hit:
                cands.append({
                    "id": u.get("id"),
                    "name": u.get("name") or u.get("title") or "",
                    "address": " ".join(filter(None, [
                        u.get("street", ""), str(u.get("house_number") or ""),
                        str(u.get("zip_code") or ""), u.get("city", "")])).strip(),
                    "plot_area": gfloat(u, "plot_area"),
                    "floor_space": gfloat(u, "total_floor_space", "property_space_value", "living_space"),
                    "marketing_type": u.get("marketing_type"),
                    "status": (u.get("property_status") or {}).get("name") if isinstance(u.get("property_status"), dict) else u.get("status"),
                    "dist_m": round(dist) if dist is not None else None,
                    "match": "geo" if geo_hit else "adresse",
                })
        report.append({"osm": o, "matches": cands})

    # Ausgabe – nach Quelle gruppiert
    for source in ("Einzelhalle", "Komplex"):
        group = [r for r in report if r["osm"]["source"] == source]
        if not group:
            continue
        print("\n" + "=" * 72)
        print(f"ABGLEICH ({source}n)  ↔  Propstack-Bestand")
        print("=" * 72)
        hits = 0
        for r in group:
            o = r["osm"]
            head = f"{o['area']} m² | {o['dist_km']} km | {o['name'] or '—'} | {o['place']}"
            if r["matches"]:
                hits += 1
                print(f"\n✅ IN PROPSTACK: {head}")
                for m in r["matches"]:
                    print(f"     → #{m['id']} '{m['name']}' | {m['address']} | "
                          f"Grundst.={m['plot_area']} Fläche={m['floor_space']} | "
                          f"{m['marketing_type']}/{m['status']} | Match={m['match']} ({m['dist_m']} m)")
            else:
                print(f"\n❌ nicht in Propstack: {head}")
        print(f"\n→ {hits} von {len(group)} {source}n mit Propstack-Treffer.")


if __name__ == "__main__":
    main()
