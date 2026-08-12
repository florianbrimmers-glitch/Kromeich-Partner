#!/usr/bin/env python3
"""
Beantwortet: Wie viele Miet-Einheiten stehen in Propstack, wie viele tragen
eine Miete – und in WELCHEM Feld?

Hintergrund: Die Asana-Aufgabe hält fest "nur 1 von 20 abrufbaren
Miet-Einheiten mit Preis; Juni-Analyse: 944/1018 ohne Preis" und daneben den
offenen Nebenbefund "/units-Listenendpoint liefert nur 20 Einheiten –
Key-Scope prüfen".

Dieses Skript prüft beides getrennt:
  1. PAGINIERUNG: `per_page` vs. `per` vs. ohne Parameter – liefert der
     Endpoint tatsächlich nur 20 Einheiten, oder war nur der Parametername
     falsch? (Der bestehende objekte_handler schickt `per`, der
     propstack-pipeline-report-Skill `per_page`.)
  2. FELDBELEGUNG: über ALLE Einheiten, welche Felder überhaupt Beträge
     tragen – Standardfelder und Custom Fields. So wird sichtbar, ob die
     Mieten fehlen oder nur woanders stehen als gesucht.

Nutzung:
    PROPSTACK_API_KEY=xxx python3 scripts/propstack_miet_audit.py
    PROPSTACK_API_KEY=xxx python3 scripts/propstack_miet_audit.py --json bericht.json

Nur lesende Aufrufe (GET), keine Schreibzugriffe.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

import httpx

BASE = "https://api.propstack.de/v1"

# Feldnamen, die nach einem Mietbetrag klingen
MIETE_MUSTER = re.compile(
    r"rent|miete|price|preis|kaltmiete|nettomiete|nebenkosten|betriebskosten|service_charge",
    re.IGNORECASE,
)
FLAECHE_MUSTER = re.compile(r"space|area|flaeche|fläche|qm", re.IGNORECASE)


def _key() -> str:
    for name in ("PROPSTACK_KEY_OBJEKTE", "PROPSTACK_API_KEY"):
        wert = os.environ.get(name, "").strip()
        if wert:
            return wert
    sys.exit("FEHLER: PROPSTACK_API_KEY (oder PROPSTACK_KEY_OBJEKTE) nicht gesetzt.")


def _get(key: str, path: str, params: dict) -> httpx.Response:
    return httpx.get(
        f"{BASE}{path}",
        headers={"X-API-KEY": key, "Accept": "application/json"},
        params=params, timeout=60.0,
    )


def _entpacke(data) -> list[dict]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for schluessel in ("data", "units", "properties"):
            if isinstance(data.get(schluessel), list):
                return [x for x in data[schluessel] if isinstance(x, dict)]
    return []


def teste_paginierung(key: str) -> dict:
    """Klärt, ob '/units liefert nur 20' am Parameternamen liegt."""
    print("=" * 70)
    print("1. PAGINIERUNG")
    print("=" * 70)

    varianten = {
        "ohne Parameter": {},
        "per=100": {"per": 100},
        "per_page=100": {"per_page": 100},
        "per_page=100 + page=1": {"per_page": 100, "page": 1},
        "limit=100": {"limit": 100},
    }
    ergebnis = {}
    for label, params in varianten.items():
        try:
            response = _get(key, "/units", {**params, "expand": 1})
            if response.status_code >= 400:
                print(f"  {label:28} HTTP {response.status_code}: {response.text[:120]}")
                ergebnis[label] = f"HTTP {response.status_code}"
                continue
            anzahl = len(_entpacke(response.json()))
            gesamt = response.headers.get("X-Total-Count") or response.headers.get("Total")
            print(f"  {label:28} {anzahl:4d} Einheiten"
                  + (f"   (X-Total-Count: {gesamt})" if gesamt else ""))
            ergebnis[label] = anzahl
        except httpx.HTTPError as e:
            print(f"  {label:28} Fehler: {e}")
            ergebnis[label] = f"Fehler: {e}"

    beste = max((v for v in ergebnis.values() if isinstance(v, int)), default=0)
    if beste > 20:
        print(f"\n  -> Der Endpoint liefert mehr als 20 Einheiten ({beste}). Der Befund")
        print("     '/units liefert nur 20' lag am Parameternamen, nicht am Key-Scope.")
    elif beste == 20:
        print("\n  -> Alle Varianten liefern genau 20. Entweder gibt es wirklich nur 20")
        print("     Einheiten, oder der Key ist eingeschränkt. Nächster Schritt:")
        print("     Anzahl in der Propstack-UI gegenprüfen.")
    return ergebnis


def lade_alle(key: str) -> list[dict]:
    """Alle Einheiten paginiert (per_page + per, damit es sicher greift)."""
    units: list[dict] = []
    gesehen: set = set()
    for page in range(1, 201):
        response = _get(key, "/units", {
            "page": page, "per_page": 100, "per": 100, "expand": 1,
        })
        if response.status_code >= 400:
            print(f"  Seite {page}: HTTP {response.status_code} – Abbruch")
            break
        seite = _entpacke(response.json())
        if not seite:
            break
        neu = [u for u in seite if u.get("id") not in gesehen]
        for u in neu:
            gesehen.add(u.get("id"))
        units.extend(neu)
        print(f"  Seite {page:3d}: {len(seite):3d} Einträge, {len(neu):3d} neu "
              f"(gesamt {len(units)})")
        if not neu or len(seite) < 100:
            break
    return units


def _ist_miete(unit: dict) -> bool:
    if unit.get("for_rent") is True:
        return True
    marketing = str(unit.get("marketing_type") or "").upper()
    return marketing in ("RENT", "RENT_AND_BUY", "MIETE")


def _wert(rohwert):
    """Custom-Field-Objekte entpacken und in eine Zahl überführen."""
    if isinstance(rohwert, dict) and "value" in rohwert:
        rohwert = rohwert["value"]
    if rohwert is None or isinstance(rohwert, bool):
        return None
    if isinstance(rohwert, (int, float)):
        return float(rohwert)
    treffer = re.search(r"-?\d{1,3}(?:[.\s]\d{3})*(?:,\d+)?|-?\d+(?:\.\d+)?", str(rohwert))
    if not treffer:
        return None
    zahl = treffer.group(0).replace(" ", "")
    if "," in zahl:
        zahl = zahl.replace(".", "").replace(",", ".")
    elif zahl.count(".") > 1:
        zahl = zahl.replace(".", "")
    try:
        return float(zahl)
    except ValueError:
        return None


def analysiere_felder(units: list[dict]) -> dict:
    print("\n" + "=" * 70)
    print("2. FELDBELEGUNG")
    print("=" * 70)

    miet_units = [u for u in units if _ist_miete(u)]
    print(f"\n  Einheiten gesamt:        {len(units)}")
    print(f"  davon Mietobjekte:       {len(miet_units)}")

    gefuellt: Counter = Counter()
    beispiele: dict[str, list] = {}
    auf_anfrage = 0

    for unit in miet_units:
        moebel = unit.get("furnishings") if isinstance(unit.get("furnishings"), dict) else {}
        if unit.get("price_on_inquiry") is True or moebel.get("price_on_inquiry") is True:
            auf_anfrage += 1

        kandidaten = {k: v for k, v in unit.items() if MIETE_MUSTER.search(k)}
        custom = unit.get("custom_fields")
        if isinstance(custom, dict):
            kandidaten.update({
                f"custom_fields.{k}": v for k, v in custom.items() if MIETE_MUSTER.search(str(k))
            })
        for feld, rohwert in kandidaten.items():
            wert = _wert(rohwert)
            if wert is not None and wert > 0:
                gefuellt[feld] += 1
                beispiele.setdefault(feld, [])
                if len(beispiele[feld]) < 3:
                    beispiele[feld].append(rohwert)

    print(f"  „Preis auf Anfrage“:     {auf_anfrage}")
    print("\n  Mietrelevante Felder mit Werten > 0 (über alle Mietobjekte):")
    if not gefuellt:
        print("    KEINES. Entweder sind die Mieten wirklich nicht erfasst,")
        print("    oder sie stehen in Feldern, die nicht nach Miete klingen.")
        alle_felder = Counter(k for u in miet_units for k in u.keys())
        print(f"\n    Vorhandene Felder ({len(alle_felder)}): "
              f"{', '.join(sorted(alle_felder))}")
    else:
        for feld, anzahl in gefuellt.most_common():
            anteil = anzahl / len(miet_units) * 100 if miet_units else 0
            print(f"    {feld:42} {anzahl:5d} ({anteil:5.1f} %)  z.B. {beispiele[feld]}")

    flaechen: Counter = Counter()
    for unit in miet_units:
        for feld, rohwert in unit.items():
            if FLAECHE_MUSTER.search(feld) and (_wert(rohwert) or 0) > 0:
                flaechen[feld] += 1
    print("\n  Flächenfelder mit Werten > 0 (für die €/m²-Umrechnung):")
    for feld, anzahl in flaechen.most_common(10):
        print(f"    {feld:42} {anzahl:5d} ({anzahl / max(len(miet_units), 1) * 100:5.1f} %)")

    bestes = gefuellt.most_common(1)
    print("\n" + "=" * 70)
    print("FAZIT")
    print("=" * 70)
    if bestes:
        feld, anzahl = bestes[0]
        anteil = anzahl / len(miet_units) * 100
        print(f"  {anzahl} von {len(miet_units)} Mietobjekten ({anteil:.0f} %) tragen eine")
        print(f"  Miete – am häufigsten im Feld '{feld}'.")
        if anteil >= 50:
            print("  -> Propstack ist als Datenbasis tragfähig. Feld in")
            print("     comparables_handler/config.py KALTMIETE_FELDER nach vorn setzen.")
        else:
            print("  -> Abdeckung unter 50 %. Für regionale Mediane vermutlich zu dünn;")
            print("     Drive-Angebote als zweite Quelle behalten (QUELLE=beide).")
    else:
        print("  Keine Mieten gefunden. Vor dem Weiterbauen in der Propstack-UI")
        print("  eine Einheit mit bekannter Miete öffnen und prüfen, wie das Feld heißt.")

    return {
        "units_gesamt": len(units),
        "mietobjekte": len(miet_units),
        "preis_auf_anfrage": auf_anfrage,
        "miete_felder": dict(gefuellt),
        "flaechen_felder": dict(flaechen),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", metavar="DATEI", help="Bericht zusätzlich als JSON ablegen")
    args = parser.parse_args()

    key = _key()
    bericht = {"paginierung": teste_paginierung(key)}

    print("\nLade alle Einheiten …")
    units = lade_alle(key)
    bericht.update(analysiere_felder(units))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(bericht, f, ensure_ascii=False, indent=2)
        print(f"\nBericht geschrieben: {args.json}")


if __name__ == "__main__":
    main()
