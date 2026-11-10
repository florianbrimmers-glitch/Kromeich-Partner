"""Straßen-Kilometer für die Lagetexte: Ziele aus OpenStreetMap (Overpass), Entfernungen per OSRM-Routing.

Nichts wird geschätzt: Jede Zahl ist eine berechnete Fahrstrecke vom Standort zum Ziel.
Aufruf: python3 -I lage.py <projekt-id> [<projekt-id> ...]   (ohne Argument: alle 15)
"""
import json, math, os, subprocess, sys, time, urllib.parse

UA = "propstack-mcp/1.0 (CRM-Connector; Geokodierung)"
OVERPASS = "https://overpass.openstreetmap.fr/api/interpreter"
OSRM = "https://router.project-osrm.org"
BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "cache")
os.makedirs(CACHE, exist_ok=True)


def curl(url, params=None, timeout=90):
    cmd = ["curl", "-sS", "-m", str(timeout), "-G", "-A", UA]
    for k, v in (params or {}).items():
        cmd += ["--data-urlencode", f"{k}={v}"]
    cmd.append(url)
    for attempt in range(3):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip().startswith("{"):
            return json.loads(r.stdout)
        time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"Abruf fehlgeschlagen: {url} → {r.stderr[:200] or r.stdout[:200]}")


def cached(name, fn):
    path = os.path.join(CACHE, name + ".json")
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    data = fn()
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    time.sleep(1.5)
    return data


def overpass(name, query):
    return cached(name, lambda: curl(OVERPASS, {"data": query}, timeout=120))["elements"]


def air(a, b):
    (lat1, lon1), (lat2, lon2) = a, b
    p = math.pi / 180
    h = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def road_km(name, origin, points):
    """Fahrstrecke vom Standort zu jedem Punkt (km); None, wenn nicht erreichbar."""
    if not points:
        return []
    out = []
    for start in range(0, len(points), 80):
        chunk = points[start:start + 80]
        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in [origin] + chunk)
        data = cached(f"{name}_{start}", lambda: curl(f"{OSRM}/table/v1/driving/{coords}", {"sources": "0", "annotations": "distance"}))
        row = data["distances"][0][1:]
        out += [None if d is None else d / 1000 for d in row]
    return out


def fmt(km):
    if km < 10:
        return f"ca. {km:.1f} km".replace(".", ",")
    return f"ca. {round(km):d} km"


def site_targets(pid, lat, lon):
    o = (lat, lon)
    res = {}

    # 1) Autobahn-Anschlussstellen: Knoten mit Namen, dazu die Autobahn (Weg durch den Knoten)
    q = f"""[out:json][timeout:90];
node(around:30000,{lat},{lon})[highway=motorway_junction][name]->.j;
.j out body;
way(bn.j)[highway~"^(motorway|trunk)$"][ref];
out body;"""
    els = overpass(f"{pid}_junctions", q)
    nodes = {e["id"]: e for e in els if e["type"] == "node"}
    ref_of = {}
    for w in (e for e in els if e["type"] == "way"):
        ref = w["tags"]["ref"].split(";")[0].strip()
        for n in w.get("nodes", []):
            if n in nodes:
                ref_of.setdefault(n, ref)
    junctions = {}
    for n in nodes.values():
        ref = ref_of.get(n["id"])
        if not ref or not ref.replace(" ", "").upper().startswith("A"):
            continue
        key = (ref, n["tags"]["name"])
        d = air(o, (n["lat"], n["lon"]))
        if key not in junctions or d < junctions[key]["air"]:
            junctions[key] = {"air": d, "lat": n["lat"], "lon": n["lon"], "ref": ref, "name": n["tags"]["name"], "nr": n["tags"].get("ref")}
    near = sorted(junctions.values(), key=lambda j: j["air"])[:8]

    # Auffahrten der nächsten Anschlussstellen: Endpunkte der Verbindungsrampen (dort erreicht man die Anschlussstelle)
    parts = "".join(f"way(around:900,{j['lat']},{j['lon']})[highway=motorway_link];" for j in near)
    links = overpass(f"{pid}_links", f"[out:json][timeout:90];({parts});out geom;") if near else []
    pts, owner = [], []
    for w in links:
        g = w.get("geometry") or []
        for p in (g[0], g[-1]) if g else []:
            pt = (p["lat"], p["lon"])
            j = min(near, key=lambda j: air(pt, (j["lat"], j["lon"])))
            if air(pt, (j["lat"], j["lon"])) <= 1.2:
                pts.append(pt)
                owner.append((j["ref"], j["name"]))
    km = road_km(f"{pid}_osrm_links", o, pts)
    best = {}
    for k, d in zip(owner, km):
        if d is not None and (k not in best or d < best[k]):
            best[k] = d
    res["autobahn"] = sorted(({"ref": k[0], "name": k[1], "km": d, "nr": junctions[k].get("nr")} for k, d in best.items()), key=lambda x: x["km"])

    # 2) Bundesstraßen im Umkreis: nächster Punkt je Bundesstraße
    q = f"""[out:json][timeout:90];
way(around:9000,{lat},{lon})[highway~"^(primary|trunk|secondary)$"][ref~"^B ?[0-9]+"];
out geom;"""
    ways = overpass(f"{pid}_bundes", q)
    cand = {}
    for w in ways:
        for ref in (r.strip() for r in w["tags"]["ref"].split(";")):
            if not ref.upper().startswith("B") or not ref[1:].strip().split(" ")[0].rstrip("abn").isdigit():
                continue
            ref = "B " + ref[1:].strip()
            for p in w.get("geometry", []):
                d = air(o, (p["lat"], p["lon"]))
                cand.setdefault(ref, []).append((d, p["lat"], p["lon"]))
    pts, owner = [], []
    for ref, lst in cand.items():
        for d, la, lo in sorted(lst)[:4]:
            pts.append((la, lo))
            owner.append(ref)
    km = road_km(f"{pid}_osrm_bundes", o, pts)
    best = {}
    for k, d in zip(owner, km):
        if d is not None and (k not in best or d < best[k]):
            best[k] = d
    res["bundesstrasse"] = sorted(({"ref": k, "km": d} for k, d in best.items()), key=lambda x: x["km"])

    # 3) ÖPNV: Bahnhöfe/Haltepunkte und Bushaltestellen
    q = f"""[out:json][timeout:90];
(node(around:9000,{lat},{lon})[railway~"^(station|halt)$"][name];
 node(around:1500,{lat},{lon})[highway=bus_stop][name];
 node(around:1500,{lat},{lon})[railway=tram_stop][name];);
out body;"""
    els = overpass(f"{pid}_oepnv", q)
    rail = [e for e in els if e["tags"].get("railway") in ("station", "halt") and e["tags"].get("station") not in ("subway", "light_rail_disused") and e["tags"].get("usage") != "tourism" and "disused" not in e["tags"]]
    stops = [e for e in els if e["tags"].get("highway") == "bus_stop" or e["tags"].get("railway") == "tram_stop"]
    rail = sorted(rail, key=lambda e: air(o, (e["lat"], e["lon"])))[:5]
    stops = sorted(stops, key=lambda e: air(o, (e["lat"], e["lon"])))[:6]
    km = road_km(f"{pid}_osrm_oepnv", o, [(e["lat"], e["lon"]) for e in rail + stops])
    rr = [{"name": e["tags"]["name"], "art": e["tags"].get("railway"), "station": e["tags"].get("station"), "km": d} for e, d in zip(rail, km[:len(rail)]) if d is not None]
    ss = [{"name": e["tags"]["name"], "art": "tram" if e["tags"].get("railway") == "tram_stop" else "bus", "km": d} for e, d in zip(stops, km[len(rail):]) if d is not None]
    res["bahn"] = sorted(rr, key=lambda x: x["km"])
    res["bus"] = sorted(ss, key=lambda x: x["km"])
    return res


def fixed_targets(pid, lat, lon, catalog, kind):
    o = (lat, lon)
    near = sorted(catalog, key=lambda c: air(o, (c["lat"], c["lon"])))[:6]
    km = road_km(f"{pid}_osrm_{kind}", o, [(c["lat"], c["lon"]) for c in near])
    return sorted(({**c, "km": d} for c, d in zip(near, km) if d is not None), key=lambda x: x["km"])


if __name__ == "__main__":
    projects = {int(k): v for k, v in json.load(open(os.path.join(BASE, "..", "mileway", "after_projects.json"), encoding="utf-8")).items()}
    ids = [int(a) for a in sys.argv[1:]] or sorted(projects)
    catalogs = {}
    for kind in ("flughafen", "hafen"):
        path = os.path.join(BASE, f"{kind}.json")
        catalogs[kind] = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    out_path = os.path.join(BASE, "lage_ergebnis.json")
    result = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
    for pid in ids:
        p = projects[pid]
        r = site_targets(pid, p["lat"], p["lng"])
        for kind in catalogs:
            r[kind] = fixed_targets(pid, p["lat"], p["lng"], catalogs[kind], kind) if catalogs[kind] else []
        result[str(pid)] = {"city": p["city"], "street": p["street"], **r}
        print(f"== {pid} {p['city']}")
        print("  Autobahn:", [(a["ref"], a["name"], a.get("nr"), round(a["km"], 2)) for a in r["autobahn"][:5]])
        print("  Bundesstr.:", [(b["ref"], round(b["km"], 2)) for b in r["bundesstrasse"][:4]])
        print("  Bahn:", [(b["name"], b["art"], round(b["km"], 2)) for b in r["bahn"][:3]])
        print("  Bus:", [(b["name"], b["art"], round(b["km"], 2)) for b in r["bus"][:3]])
        for kind in catalogs:
            print(f"  {kind}:", [(c["name"], round(c["km"], 1)) for c in r[kind][:3]])
        json.dump(result, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
