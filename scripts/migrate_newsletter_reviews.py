"""LESE-Probe: welches Feld einer /activities-Zeile ist die ID für /tasks/:id?"""
import json, os, httpx
BASE = "https://api.propstack.de/v1"
H = {"X-API-KEY": os.environ["PROPSTACK_API_KEY"], "Accept": "application/json"}
r = httpx.get(f"{BASE}/activities", headers=H, timeout=30, params={
    "item_type": "reminder", "broker_id": 387451, "sort_by": "created_at", "order": "desc", "per": 1})
p = r.json(); row = (p if isinstance(p, list) else p.get("data", []))[0]
print("KEYS:", sorted(row.keys()))
print(json.dumps({k: v for k, v in row.items() if not isinstance(v, (list, dict)) or k in ("task", "item")},
                 ensure_ascii=False, indent=1, default=str)[:3000])
for k, v in row.items():
    if isinstance(v, int) and v > 1000:
        g = httpx.get(f"{BASE}/tasks/{v}", headers=H, timeout=30)
        print(f"GET /tasks/{v} (Feld {k}): HTTP {g.status_code}")
