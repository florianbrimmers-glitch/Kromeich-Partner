"""Misst die Zuordnung des Newsletter-Handlers an den geprüften Urteilen. Liest nur Dateien.

Am 19./20.11.2026 wurden alle 129 offenen Aufgaben „Newsletter-Vermietung prüfen“ einzeln
gelesen; scripts/radar_pruefsatz_2026-11-20.json hält je Aufgabe fest, um welche Einheiten es
wirklich ging. Dieses Skript legt einen Lese-Lauf des Handlers über dieselben Digests daneben:

  1. Lauf starten (GitHub → Actions → Newsletter Handler → Run workflow):
     no_write=true, ignore_checkmark=true, scan_from_hours so groß wie das Fenster.
     Der Lauf schreibt nichts – keine Aufgabe, keine Reaktion in Slack.
  2. Das Protokoll des Laufs als Textdatei speichern.
  3. python scripts/radar_zuordnung_messen.py <protokoll.txt>

Gewertet wird, was der Handler HEUTE mit der Meldung täte. Die gemeinten Einheiten sind
inzwischen alle geschlossen – richtig ist bei „erledigt“, „eintragen“ und „fremd“ also: keine
Aufgabe. Bei „teil“, „schwach“ und „unbestimmt“ gibt es kein Richtig oder Falsch; dort wird
nur gezählt.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

PRUEFSATZ = Path(__file__).resolve().parent / "radar_pruefsatz_2026-11-20.json"
OHNE_AUFGABE_RICHTIG = {"erledigt", "eintragen", "fremd"}
DEDUP_TAGE = 30   # wie newsletter_handler.config.REVIEW_DEDUP_TAGE


def lies_lauf(text: str) -> list[dict]:
    """Die AUSWERTUNG-Zeilen eines Lese-Laufs (newsletter_handler.main._auswertungszeile)."""
    zeilen = []
    for zeile in text.splitlines():
        stelle = zeile.find("AUSWERTUNG {")
        if stelle < 0:
            continue
        try:
            zeilen.append(json.loads(zeile[stelle + len("AUSWERTUNG "):]))
        except json.JSONDecodeError:
            continue
    return zeilen


def ausgang(zeile: dict) -> str:
    """Wohin die Vermietung im Lauf gegangen ist – eine von sechs Schubladen."""
    if zeile.get("stufe") != "none":
        return "Aufgabe"
    if zeile.get("verlaengerung"):
        return "keine Aufgabe: Verlängerung"
    if zeile.get("bereits_abgeschlossen"):
        return "keine Aufgabe: Einheit geschlossen"
    if zeile.get("anderer_eigentuemer"):
        return "keine Aufgabe: anderer Eigentümer"
    if "Keine Kandidaten" in str(zeile.get("grund") or ""):
        return "keine Aufgabe: nichts im Bestand gefunden"
    return "keine Aufgabe: kein Treffer"


def neue_aufgaben(lauf: list[dict]) -> list[dict]:
    """Die Zeilen, aus denen wirklich eine Aufgabe würde. Der Handler legt keine zweite an,
    solange zu JEDER der Einheiten eine Aufgabe aus den letzten 30 Tagen offen ist; hier
    gerechnet, als bliebe jede Aufgabe offen. (Der Lese-Lauf selbst merkt sich Aufgaben
    ohne Verfallsdatum und zählt deshalb über lange Fenster etwas zu wenig.)"""
    zuletzt: dict[int, float] = {}
    neu = []
    for zeile in sorted(lauf, key=lambda z: (float(z.get("ts") or 0), z.get("idx") or 0)):
        if zeile.get("stufe") == "none":
            continue
        jetzt = float(zeile.get("ts") or 0)
        units = zeile.get("units") or []
        if units and all(jetzt - zuletzt.get(u, float("-inf")) <= DEDUP_TAGE * 86400 for u in units):
            continue
        for unit in units:
            zuletzt.setdefault(unit, jetzt)
            if jetzt - zuletzt[unit] > DEDUP_TAGE * 86400:
                zuletzt[unit] = jetzt
        neu.append(zeile)
    return neu


def _woerter(*texte: str | None) -> set[str]:
    return {w for t in texte for w in re.findall(r"[a-zäöüß0-9]{3,}", (t or "").lower())}


def ordne_zu(urteile: list[dict], lauf: list[dict]) -> list[tuple[dict, dict | None]]:
    """Je geprüfter Aufgabe die Zeile des Laufs zur selben Meldung: gleicher Digest, meiste
    gemeinsame Wörter in Mieter, Vermieter und Objekt. Jede Zeile des Laufs zählt einmal."""
    je_digest: dict[str, list[dict]] = collections.defaultdict(list)
    for zeile in lauf:
        je_digest[str(zeile.get("ts"))].append(zeile)
    vergeben: set[int] = set()
    paare = []
    for urteil in urteile:
        soll = _woerter(urteil.get("mieter"), urteil.get("vermieter"), urteil.get("objekt"))
        beste, punkte = None, 0
        for zeile in je_digest.get(urteil["digest_ts"], []):
            if id(zeile) in vergeben:
                continue
            gemeinsam = len(soll & _woerter(zeile.get("mieter"), zeile.get("vermieter"), zeile.get("objekt")))
            if gemeinsam > punkte:
                beste, punkte = zeile, gemeinsam
        if beste is not None:
            vergeben.add(id(beste))
        paare.append((urteil, beste))
    return paare


def ergebnis(urteil: dict, zeile: dict | None) -> str:
    """Was der Lauf mit der Meldung getan hätte – in Worten."""
    if zeile is None:
        return "im Lauf nicht wiedergefunden"
    if zeile.get("stufe") == "none":
        if zeile.get("verlaengerung"):
            return "keine Aufgabe: Verlängerung"
        if zeile.get("bereits_abgeschlossen"):
            return "keine Aufgabe: Einheit geschlossen"
        if zeile.get("anderer_eigentuemer"):
            return "keine Aufgabe: anderer Eigentümer"
        return "keine Aufgabe: kein Treffer"
    units = set(zeile.get("units") or [])
    if not units:
        return "Aufgabe ohne Einheit"
    if units & set(urteil.get("gemeint") or []):
        return "Aufgabe an der gemeinten Einheit"
    if units & set(urteil.get("offen") or []):
        return "Aufgabe an fraglicher oder freier Einheit"
    if units & set(urteil.get("nicht_gemeint") or []):
        return "Aufgabe an derselben falschen Einheit wie damals"
    return "Aufgabe an anderer Einheit"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("protokoll", help="Textdatei mit dem Protokoll eines Lese-Laufs")
    ap.add_argument("--pruefsatz", default=str(PRUEFSATZ))
    args = ap.parse_args()

    lauf = lies_lauf(Path(args.protokoll).read_text(encoding="utf-8", errors="replace"))
    if not lauf:
        print("Keine AUSWERTUNG-Zeilen im Protokoll – war es ein Lauf mit no_write=true?", file=sys.stderr)
        return 2
    digests = {str(z.get("ts")) for z in lauf}
    alle = json.loads(Path(args.pruefsatz).read_text(encoding="utf-8"))["zeilen"]
    urteile = [u for u in alle if u["digest_ts"] in digests]
    paare = ordne_zu(urteile, lauf)

    print(f"Lauf: {len(lauf)} Vermietungen aus {len(digests)} Digests. "
          f"Geprüfte Aufgaben zu diesen Digests: {len(urteile)} von {len(alle)}.")
    print("\nWohin die Vermietungen gehen:")
    for text, zahl in collections.Counter(ausgang(z) for z in lauf).most_common():
        print(f"  {zahl:3}  {text}")
    angelegt = neue_aufgaben(lauf)
    print(f"Nach Dublettenschutz ({DEDUP_TAGE} Tage je Einheit) entstehen {len(angelegt)} Aufgaben.")
    tabelle: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for urteil, zeile in paare:
        tabelle[urteil["urteil"]][ergebnis(urteil, zeile)] += 1
    for gruppe in ("erledigt", "eintragen", "fremd", "teil", "unbestimmt", "schwach"):
        if gruppe not in tabelle:
            continue
        print(f"\n{gruppe} ({sum(tabelle[gruppe].values())} Aufgaben damals):")
        for text, zahl in tabelle[gruppe].most_common():
            print(f"  {zahl:3}  {text}")

    damals = len(urteile)
    heute = sum(1 for u, z in paare if ergebnis(u, z).startswith("Aufgabe"))
    falsch = [(u, z) for u, z in paare if u["urteil"] in OHNE_AUFGABE_RICHTIG and ergebnis(u, z).startswith("Aufgabe")]
    print(f"\nAufgaben damals: {damals}. Heute entstünden daraus (vor Dublettenschutz): {heute}.")
    print(f"Davon unnötig (Urteil erledigt, eintragen oder fremd): {len(falsch)}")
    for urteil, zeile in falsch:
        print(f"  - {urteil['ort']} | {urteil.get('mieter') or '–'} / {urteil.get('vermieter') or '–'} | {ergebnis(urteil, zeile)} "
              f"{zeile.get('units')} | {str(zeile.get('grund'))[:150]}")

    belegt = {id(z) for _, z in paare if z is not None}
    neu = [z for z in lauf if id(z) not in belegt and z.get("stufe") != "none"]
    print(f"\nAufgaben im Lauf ohne geprüftes Gegenstück: {len(neu)} "
          "(Meldungen, zu denen es damals keine Aufgabe gab oder deren Aufgabe als Dublette geschlossen wurde)")
    for zeile in neu:
        print(f"  - {zeile.get('ts')} | {zeile.get('objekt') or '–'} | {zeile.get('mieter') or '–'} / {zeile.get('vermieter') or '–'} "
              f"| {zeile.get('units')} | {str(zeile.get('grund'))[:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
