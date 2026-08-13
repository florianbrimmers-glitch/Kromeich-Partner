#!/usr/bin/env python3
"""
Prüft die Alt-Import-Mietfelder (`*_miete_m_von` / `_bis`) im Propstack-Bestand
und bereitet ihre Bereinigung vor.

Hintergrund: Diese Custom Fields existieren in der Propstack-MASKE nicht und
werden von niemandem gepflegt. Sie stammen aus einem Alt-Import und tragen
teils Müll ("Stettiner Straße 2, Neuss": 1,00 €/m², während Kaltmiete und
beide Intern-Mietpreis-Felder leer sind). Der Comparables-Report liest sie
deshalb nicht mehr.

Das Skript LÖSCHT NICHTS ohne --apply. Standardlauf:
  1. sichert alle aktuellen Werte als JSON (Wiederherstellung möglich),
  2. gliedert die Einheiten in Kategorien mit unterschiedlichem Risiko,
  3. schreibt eine CSV zum Durchgehen.

Kategorien:
  A  unplausibel + kein interner Mietpreis  -> Müll, gefahrlos löschbar
  B  plausibel   + interner Mietpreis da    -> redundant, der interne Wert
                                               gewinnt ohnehin
  C  plausibel   + KEIN interner Mietpreis  -> VORSICHT: einzige Mietangabe
                                               der Einheit. Nicht löschen,
                                               sondern fachlich prüfen.

Nutzung:
  PROPSTACK_API_KEY=xxx python3 scripts/propstack_altimport_pruefen.py
  PROPSTACK_API_KEY=xxx python3 scripts/propstack_altimport_pruefen.py --apply A
  PROPSTACK_API_KEY=xxx python3 scripts/propstack_altimport_pruefen.py --apply A,B
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comparables_handler import config, propstack_gateway as pg  # noqa: E402

BASE = "https://api.propstack.de/v1"

# Die zu prüfenden Alt-Felder, gruppiert nach zugehörigem Intern-Feld.
GRUPPEN = (
    ("Halle/Lager", ("lagerflache_miete_m_von", "lagerflache_miete_m_bis"),
     ("intern_mietpreis_hallenflache", "mietpreis_hallenflache")),
    ("Büro", ("buroflache_miete_m_von", "buroflache_miete_m_bis"),
     ("intern_mietpreis_buro", "mietpreis_buroflache")),
    ("Mezzanine", ("mezzanineflache_miete_m_von", "mezzanineflache_miete_m_bis"),
     ("intern_mietpreis_mezzanine", "mietpreis_mezzanine")),
    ("Service", ("serviceflache_miete_m_von", "serviceflache_miete_m_bis"), ()),
    ("Frei", ("freiflache_miete_m_von", "freiflache_miete_m_bis"), ()),
    ("Keller/Archiv", ("keller_archivflache_miete_m_von",), ()),
    ("Nebenkosten", ("lagerflache_nebenkosten_m_von", "lagerflache_nebenkosten_m_bis",
                     "buroflache_nebenkosten_m_von", "buroflache_nebenkosten_m_bis"), ()),
)


def _key() -> str:
    for name in ("PROPSTACK_KEY_OBJEKTE", "PROPSTACK_API_KEY"):
        if os.environ.get(name, "").strip():
            return os.environ[name].strip()
    sys.exit("FEHLER: PROPSTACK_API_KEY nicht gesetzt.")


def ist_plausibel(feld: str, wert: float) -> bool:
    """Nebenkosten an NK-Grenzen messen, Mieten an Mietgrenzen.

    Sonst gilt eine völlig normale Nebenkostenangabe von 0,65 €/m² als
    "unplausibel", nur weil sie unter der Kaltmieten-Untergrenze liegt.
    """
    if "nebenkosten" in feld:
        return config.NEBENKOSTEN_MIN_EUR_QM <= wert <= config.NEBENKOSTEN_MAX_EUR_QM
    return config.KALTMIETE_MIN_EUR_QM <= wert <= config.KALTMIETE_MAX_EUR_QM


def kategorie(feld: str, wert: float, intern_vorhanden: bool) -> str:
    if not ist_plausibel(feld, wert):
        return "A"
    return "B" if intern_vorhanden else "C"


def analysiere(units: list[dict]) -> tuple[list[dict], dict]:
    befunde: list[dict] = []
    backup: dict[str, dict] = {}

    for unit in units:
        cf = pg.custom_fields(unit)
        gesichert: dict[str, object] = {}
        for art, alt_felder, intern_felder in GRUPPEN:
            intern_vorhanden = any(
                (pg.zu_zahl(cf.get(f)) or 0) > 0 for f in intern_felder
            )
            for feld in alt_felder:
                if feld not in cf:
                    continue
                wert = pg.zu_zahl(cf.get(feld))
                if wert is None or wert <= 0:
                    continue
                gesichert[feld] = pg.skalar(cf.get(feld))
                befunde.append({
                    "unit_id": unit.get("id"),
                    "objekt": str(unit.get("name") or "")[:60],
                    "adresse": f"{unit.get('street') or ''} {unit.get('zip_code') or ''} "
                               f"{unit.get('city') or ''}".strip(),
                    "flaechenart": art,
                    "feld": feld,
                    "wert": wert,
                    "intern_vorhanden": "ja" if intern_vorhanden else "nein",
                    "intern_werte": "; ".join(
                        f"{f}={pg.zu_zahl(cf.get(f))}" for f in intern_felder
                        if (pg.zu_zahl(cf.get(f)) or 0) > 0
                    ),
                    "preisangabe": pg.skalar(cf.get(config.PREISANGABE_FELD)) or "",
                    "object_type": pg.skalar(unit.get("object_type")) or "",
                    "kategorie": kategorie(feld, wert, intern_vorhanden),
                    "link": f"https://app.propstack.de/properties/{unit.get('id')}",
                })
        if gesichert:
            backup[str(unit.get("id"))] = gesichert
    return befunde, backup


def loesche(key: str, unit_id: int, felder: list[str], trocken: bool) -> bool:
    """Custom Fields leeren – laut Exposé-Workflow-Skill per null in
    `partial_custom_fields`. Andere Felder bleiben unberührt."""
    payload = {"property": {"partial_custom_fields": {f: None for f in felder}}}
    if trocken:
        print(f"    [DRY-RUN] PUT /units/{unit_id} {sorted(felder)}")
        return True
    for versuch in range(4):
        try:
            r = httpx.put(f"{BASE}/units/{unit_id}",
                          headers={"X-API-KEY": key, "Content-Type": "application/json",
                                   "Accept": "application/json"},
                          json=payload, timeout=60.0)
            if r.status_code < 400:
                return True
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** versuch)
                continue
            print(f"    FEHLER unit {unit_id}: HTTP {r.status_code} {r.text[:200]}")
            return False
        except httpx.HTTPError as e:
            print(f"    Netzfehler unit {unit_id}: {e}")
            time.sleep(2 ** versuch)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", metavar="KATEGORIEN",
                        help="Kategorien wirklich leeren, z.B. 'A' oder 'A,B'. "
                             "Ohne diese Option passiert nichts.")
    parser.add_argument("--csv", default="altimport_befunde.csv")
    parser.add_argument("--backup", default="altimport_backup.json")
    args = parser.parse_args()

    key = _key()
    os.environ.setdefault("PROPSTACK_API_KEY", key)
    print("Lade alle Miet-Einheiten …")
    units = [u for u in pg.fetch_units() if pg.ist_mietobjekt(u)]
    befunde, backup = analysiere(units)

    with open(args.backup, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=1)
    with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(befunde[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(befunde)

    print(f"\n{len(befunde)} Werte in {len(backup)} Einheiten gefunden")
    print(f"  Sicherung: {args.backup}")
    print(f"  Liste:     {args.csv}")

    print("\n=== Kategorien ===")
    kats = Counter(b["kategorie"] for b in befunde)
    texte = {
        "A": "unplausibel, kein interner Mietpreis -> Müll, gefahrlos löschbar",
        "B": "plausibel, interner Mietpreis vorhanden -> redundant",
        "C": "plausibel, KEIN interner Mietpreis -> einzige Mietangabe, NICHT löschen",
    }
    for kat in ("A", "B", "C"):
        print(f"  {kat}: {kats.get(kat, 0):4d}  {texte[kat]}")

    print("\n=== Je Feld ===")
    for feld, anzahl in Counter(b["feld"] for b in befunde).most_common():
        print(f"  {feld:34s} {anzahl:4d}")

    print("\n=== Kategorie A (Auszug) ===")
    for b in [x for x in befunde if x["kategorie"] == "A"][:10]:
        print(f"  {b['wert']:>7} {b['feld']:30s} {b['objekt'][:34]:34s} {b['link']}")
    print("\n=== Kategorie C – hier steckt echte Information (Auszug) ===")
    for b in [x for x in befunde if x["kategorie"] == "C"][:10]:
        print(f"  {b['wert']:>7} {b['feld']:30s} {b['objekt'][:34]:34s} "
              f"preisangabe={b['preisangabe']}")

    if not args.apply:
        print("\nNichts geändert. Zum Leeren: --apply A   (bzw. --apply A,B)")
        return

    gewaehlt = {k.strip().upper() for k in args.apply.split(",") if k.strip()}
    if "C" in gewaehlt:
        print("\nABBRUCH: Kategorie C enthält die einzige Mietangabe der Einheit.")
        print("Diese Werte gehören fachlich geprüft, nicht per Skript geleert.")
        sys.exit(1)

    zu_leeren: dict[int, list[str]] = {}
    for b in befunde:
        if b["kategorie"] in gewaehlt:
            zu_leeren.setdefault(b["unit_id"], []).append(b["feld"])

    print(f"\n=== Leere {sum(len(v) for v in zu_leeren.values())} Werte "
          f"in {len(zu_leeren)} Einheiten (Kategorien {sorted(gewaehlt)}) ===")
    ok = fehler = 0
    for unit_id, felder in zu_leeren.items():
        if loesche(key, unit_id, felder, trocken=False):
            ok += 1
        else:
            fehler += 1
        time.sleep(0.2)
    print(f"\nFertig: {ok} Einheiten bereinigt, {fehler} Fehler.")
    print(f"Wiederherstellung: die Werte stehen in {args.backup}")


if __name__ == "__main__":
    main()
