"""Auswertung: manuell vs. KI-angelegte Propstack-Kontakte + Mailchimp-Interessen.

Aufruf:  PROPSTACK_API_KEY=... python analyze_contacts.py

Wichtig:
- Der Listen-Endpoint /contacts liefert NICHT die Felder `description` und
  `mailchimp_interest_ids` – dafür muss je Kontakt der Detail-Endpoint
  /contacts/{id} abgefragt werden.
- Pagination nutzt den Parameter `per` (NICHT `per_page`, das wird ignoriert).
"""
from __future__ import annotations

import concurrent.futures as cf
import os
import sys

import httpx

BASE_URL = "https://api.propstack.de/v1"
PER_PAGE = 200
MAX_WORKERS = 8

# Marker, die im description-Feld stehen, je nach erzeugendem Tool:
KI_GITHUB = "KI-Scan (GitHub Actions)"  # diese Pipeline = "Claude"
KI_COWORK = "KI-Scan (Cowork)"          # anderes KI-Tool


def fetch_all_ids(api_key: str) -> list[int]:
    ids: list[int] = []
    page = 1
    while True:
        resp = httpx.get(
            f"{BASE_URL}/contacts",
            params={"api_key": api_key, "page": page, "per": PER_PAGE},
            timeout=120.0,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not isinstance(batch, list) or not batch:
            break
        ids.extend(c["id"] for c in batch)
        if len(batch) < PER_PAGE:
            break
        page += 1
    return ids


def fetch_detail(api_key: str, cid: int) -> dict:
    for attempt in range(3):
        try:
            resp = httpx.get(
                f"{BASE_URL}/contacts/{cid}",
                params={"api_key": api_key},
                timeout=60.0,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            if attempt == 2:
                return {"id": cid, "_error": True}
    return {"id": cid, "_error": True}


def desc(c: dict) -> str:
    return c.get("description") or ""


def is_claude(c: dict) -> bool:
    return KI_GITHUB in desc(c)


def is_cowork(c: dict) -> bool:
    return KI_COWORK in desc(c)


def has_mailchimp(c: dict) -> bool:
    return bool(c.get("mailchimp_interest_ids"))


def main() -> int:
    api_key = os.environ.get("PROPSTACK_API_KEY")
    if not api_key:
        print("FEHLER: PROPSTACK_API_KEY nicht gesetzt.", file=sys.stderr)
        return 1

    ids = fetch_all_ids(api_key)
    print(f"IDs gesamt: {len(ids)}")

    details: list[dict] = []
    with cf.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for d in ex.map(lambda cid: fetch_detail(api_key, cid), ids):
            details.append(d)

    errors = [d for d in details if d.get("_error")]
    persons = [c for c in details if not c.get("is_company")]
    companies = [c for c in details if c.get("is_company")]

    claude_p = [c for c in persons if is_claude(c)]
    cowork_p = [c for c in persons if is_cowork(c)]
    manual_p = [c for c in persons if not is_claude(c) and not is_cowork(c)]

    print("=" * 64)
    print("PROPSTACK GESAMT-AUSWERTUNG")
    print("=" * 64)
    print(f"Datensätze gesamt: {len(details)}  |  Firmen: {len(companies)}  |  Personen: {len(persons)}")
    if errors:
        print(f"WARNUNG: {len(errors)} Detail-Abrufe fehlgeschlagen")
    print("-" * 64)
    print(f"Personen – echt manuell (kein KI-Marker):        {len(manual_p)}")
    print(f"Personen – von Claude (KI-Scan GitHub Actions):  {len(claude_p)}")
    print(f"Personen – von Cowork (anderes KI-Tool):         {len(cowork_p)}")
    print("-" * 64)
    print(f"Personen mit Mailchimp-Interessen gesamt: {len([c for c in persons if has_mailchimp(c)])}")
    print(f"   davon manuell:      {len([c for c in manual_p if has_mailchimp(c)])}")
    print(f"   davon von Claude:   {len([c for c in claude_p if has_mailchimp(c)])}")
    print(f"   davon von Cowork:   {len([c for c in cowork_p if has_mailchimp(c)])}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
