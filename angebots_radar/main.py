"""Angebots-Radar ausführen. Liest nur – kein Schreiben in Propstack, kein Slack, keine KI.

  python -m angebots_radar.main                       # alle aktiven Hallengesuche
  python -m angebots_radar.main --gesuch 13969555     # nur dieses Suchprofil
  python -m angebots_radar.main --betreuer Marek      # nur die Gesuche dieses Betreuers
  python -m angebots_radar.main --nur-neu --tage 7    # nur, was seit sieben Tagen neu ist (Fläche oder Gesuch)
  python -m angebots_radar.main --json lauf.json      # Ergebnis zusätzlich als Datei
  python -m angebots_radar.main --merken angebots_radar/laeufe/2026-11-26.json   # Vorschläge ohne Namen ablegen
  python -m angebots_radar.main --vergleich angebots_radar/laeufe/2026-11-26.json   # was wurde daraus?

Die Einheiten zu laden dauert rund vier Minuten. `--daten ORDNER` liest stattdessen gespeicherte
Antworten (einheiten.json, suchprofile.json, deals.json, kontakte.json, makler.json) und legt sie
dort ab, wenn sie fehlen – zum Entwickeln und für wiederholte Auswertungen am selben Stand.

Umgebung: PROPSTACK_API_KEY oder PROPSTACK_API_V1 (wird nie ausgegeben).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from .abgleich import Abgleich, Angebote
from .bericht import als_daten, als_text, fuer_vergleich, vergleich
from .bestand import lade_bestand
from .gesuch import aus_suchprofil, ist_hallengesuch
from .propstack import Propstack


class Quelle:
    """Schnittstelle oder Ordner mit gespeicherten Antworten."""

    def __init__(self, ordner: str | None):
        self.ordner = Path(ordner) if ordner else None
        self._ps: Propstack | None = None

    def _propstack(self) -> Propstack:
        if self._ps is None:
            key = os.environ.get("PROPSTACK_API_KEY") or os.environ.get("PROPSTACK_API_V1")
            if not key:
                raise SystemExit("PROPSTACK_API_KEY bzw. PROPSTACK_API_V1 fehlt.")
            self._ps = Propstack(key)
        return self._ps

    def hole(self, name: str, laden):
        datei = self.ordner / f"{name}.json" if self.ordner else None
        if datei and datei.exists():
            return json.loads(datei.read_text(encoding="utf-8"))
        daten = laden(self._propstack())
        if datei:
            self.ordner.mkdir(parents=True, exist_ok=True)
            datei.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
        return daten


def lauf(quelle: Quelle, heute: date, gesuch_ids: set[int] | None = None, betreuer: str | None = None,
         nur_neu: bool = False, tage: int = 7, je_gesuch: int = 5) -> tuple[dict, list[dict]]:
    """(Berichtsdaten, Deals)."""
    einheiten = quelle.hole("einheiten", lambda ps: ps.einheiten())
    profile = quelle.hole("suchprofile", lambda ps: ps.suchprofile())
    deals = quelle.hole("deals", lambda ps: ps.deals())
    makler = {int(k): v for k, v in quelle.hole("makler", lambda ps: ps.makler()).items()}

    flaechen, ohne_lage = lade_bestand(einheiten, heute)
    gesuche = [aus_suchprofil(p) for p in profile]
    aktive = [g for g in gesuche if g.aktiv]
    if gesuch_ids:
        aktive = [g for g in gesuche if g.id in gesuch_ids]          # ausdrücklich genannt: auch inaktive
    if betreuer:
        aktive = [g for g in aktive if betreuer.casefold() in (makler.get(g.betreuer_id or 0) or "").casefold()]
    ids = sorted({g.kontakt_id for g in aktive})
    kontakte = {int(k): v for k, v in quelle.hole("kontakte", lambda ps: ps.kontakte(ids)).items()}
    # Testprofile hängen an „Max Mustermann“/„Test Test“; andere Profile hängen an einem Kollegen statt
    # am Kunden (26.11.2026: zusammen 11 aktive). Beides läuft nicht in den Abgleich, steht aber im Bericht.
    eigene = {name.casefold() for name in makler.values() if name}
    for g in aktive:
        name = (kontakte.get(g.kontakt_id, {}).get("name") or "").casefold()
        if g.kein_hallengesuch is None and re.search(r"mustermann|^test\b", name):
            g.kein_hallengesuch = "Testprofil"
        elif g.kein_hallengesuch is None and name in eigene:
            g.kein_hallengesuch = "hängt an einem Kollegen"

    zu_pruefen = [g for g in aktive if ist_hallengesuch(g) and not g.erledigt_hinweis]
    uebrige = [g for g in aktive if g not in zu_pruefen]

    abgleich = Abgleich(flaechen, Angebote.aus_deals(deals), heute, neu_tage=tage, je_gesuch=je_gesuch)
    ergebnisse = [abgleich.pruefe(g) for g in zu_pruefen]

    gezeigt = lambda e: [v for v in e.vorschlaege if v.neu] if nur_neu else e.vorschlaege   # noqa: E731
    kopf = {
        "suchprofile": len(profile),
        "aktive_profile": sum(1 for g in gesuche if g.aktiv),
        "gesuche_geprueft": len(ergebnisse),
        "gesuche_mit_vorschlag": sum(1 for e in ergebnisse if gezeigt(e)),
        "vorschlaege_gesamt": sum(len(gezeigt(e)) for e in ergebnisse),
        "vorschlaege_gezeigt": sum(min(je_gesuch, len(gezeigt(e))) for e in ergebnisse),
        "schon_angeboten": sum(e.schon_angeboten for e in ergebnisse),
        "je_gesuch": je_gesuch,
        "flaechen": len(flaechen),
        "flaechen_geschaetzt": sum(1 for f in flaechen if f.lage_geschaetzt),
        "flaechen_ohne_lage": ohne_lage,
        "nur_neu": nur_neu,
        "tage": tage,
        "kein_hallengesuch": sum(1 for g in uebrige if g.kein_hallengesuch),
    }
    return als_daten(ergebnisse, uebrige, kontakte, makler, heute, kopf, je_gesuch, nur_neu), deals


def main() -> int:
    ap = argparse.ArgumentParser(description="Angebots-Radar: passende, noch nicht angebotene Flächen je Gesuch (nur lesend)")
    ap.add_argument("--gesuch", type=int, action="append", help="Suchprofil-ID (mehrfach möglich)")
    ap.add_argument("--betreuer", help="nur Gesuche dieses Betreuers (Teil des Namens)")
    ap.add_argument("--nur-neu", action="store_true", help="nur Vorschläge mit neuer Fläche oder neuem Gesuch")
    ap.add_argument("--tage", type=int, default=7, help="was als neu gilt (Standard 7 Tage)")
    ap.add_argument("--je-gesuch", type=int, default=5, help="höchstens so viele Vorschläge je Gesuch (Standard 5)")
    ap.add_argument("--json", metavar="DATEI", help="Ergebnis als JSON schreiben")
    ap.add_argument("--merken", metavar="DATEI", help="Vorschläge ohne Namen ablegen – für --vergleich in ein paar Wochen")
    ap.add_argument("--vergleich", metavar="DATEI", help="JSON eines früheren Laufs: was wurde daraus?")
    ap.add_argument("--daten", metavar="ORDNER", help="gespeicherte Antworten lesen bzw. dort ablegen")
    ap.add_argument("--stand", metavar="JJJJ-MM-TT", help="Stichtag (Standard heute) – für gespeicherte Daten")
    args = ap.parse_args()

    heute = date.fromisoformat(args.stand) if args.stand else date.today()
    quelle = Quelle(args.daten)
    if args.vergleich:
        alt = json.loads(Path(args.vergleich).read_text(encoding="utf-8"))
        ergebnis = vergleich(alt, quelle.hole("deals", lambda ps: ps.deals()))
        print(f"Lauf vom {date.fromisoformat(ergebnis['seit']):%d.%m.%Y}: {ergebnis['vorschlaege']} Vorschläge, "
              f"davon seither {ergebnis['angeboten']} als Deal angelegt.")
        for t in ergebnis["treffer"]:
            print(f"  {t['kontakt']} – {t['bezeichnung']} ({t['ort']})")
        return 0

    daten, _ = lauf(quelle, heute, set(args.gesuch) if args.gesuch else None, args.betreuer,
                    args.nur_neu, args.tage, args.je_gesuch)
    print(als_text(daten))
    if args.json:
        Path(args.json).write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Geschrieben: {args.json}")
    if args.merken:
        Path(args.merken).write_text(json.dumps(fuer_vergleich(daten), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"Gemerkt: {args.merken}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
