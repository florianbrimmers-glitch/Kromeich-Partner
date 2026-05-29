"""Einmalige Auswertung: manuell vs. KI-angelegte Propstack-Kontakte + Mailchimp-Interessen.

Aufruf:  PROPSTACK_API_KEY=... python analyze_contacts.py
"""
from __future__ import annotations

import os
import sys
import httpx

BASE_URL = "https://api.propstack.de/v1"
# Marker, den die Pipeline in das description-Feld schreibt (siehe propstack_client.py)
KI_MARKER = "KI-Scan (GitHub Actions)"


def fetch_all_contacts(api_key: str) -> list[dict]:
    contacts: list[dict] = []
    page = 1
    while True:
        resp = httpx.get(
            f"{BASE_URL}/contacts",
            params={"api_key": api_key, "page": page, "per_page": 100},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        # API liefert entweder eine Liste oder ein Objekt mit "data"/"clients"
        if isinstance(data, dict):
            batch = data.get("data") or data.get("clients") or []
        else:
            batch = data
        if not batch:
            break
        contacts.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return contacts


def is_ki_created(contact: dict) -> bool:
    desc = (contact.get("description") or "")
    return KI_MARKER in desc


def has_mailchimp_interests(contact: dict) -> bool:
    val = contact.get("mailchimp_interest_ids")
    return bool(val)


def main() -> int:
    api_key = os.environ.get("PROPSTACK_API_KEY")
    if not api_key:
        print("FEHLER: PROPSTACK_API_KEY nicht gesetzt.", file=sys.stderr)
        return 1

    contacts = fetch_all_contacts(api_key)

    persons = [c for c in contacts if not c.get("is_company")]
    companies = [c for c in contacts if c.get("is_company")]

    ki_persons = [c for c in persons if is_ki_created(c)]
    manual_persons = [c for c in persons if not is_ki_created(c)]

    ki_with_mc = [c for c in ki_persons if has_mailchimp_interests(c)]
    manual_with_mc = [c for c in manual_persons if has_mailchimp_interests(c)]
    total_with_mc = [c for c in persons if has_mailchimp_interests(c)]

    print("=" * 60)
    print("PROPSTACK KONTAKT-AUSWERTUNG")
    print("=" * 60)
    print(f"Datensätze gesamt (inkl. Firmen): {len(contacts)}")
    print(f"  davon Firmen (is_company):      {len(companies)}")
    print(f"  davon Personen-Kontakte:        {len(persons)}")
    print("-" * 60)
    print(f"Manuell angelegt (kein KI-Marker): {len(manual_persons)}")
    print(f"Von Claude/KI angelegt:            {len(ki_persons)}")
    print("-" * 60)
    print("Mit Mailchimp-Interessen:")
    print(f"  gesamt:                {len(total_with_mc)}")
    print(f"  davon manuell:         {len(manual_with_mc)}")
    print(f"  davon von Claude/KI:   {len(ki_with_mc)}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
